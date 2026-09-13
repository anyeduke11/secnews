"""MITRE ATT&CK STIX data fetching + parsing for security knowledge graph.

Design
------
- Fetches the MITRE ATT&CK enterprise-attack STIX bundle from GitHub raw.
- Parses attack-patterns → techniques, tactics, and relationships.
- Upserts into security_entities + security_edges via SecurityRepository.

Phase 2: minimal viable sync (tactics + techniques + uses/subtechnique-of edges).

v0.7 Batch ⑨ B9-4: 离线包 + 增量同步
- 本地 cache 路径: backend/data/mitre/enterprise-attack.json (env MITRE_CACHE_DIR
  可覆盖), 首次同步写入, 后续走 ETag/If-Modified-Since 304 跳过下载.
- 增量 diff: 比对本地 cache mtime vs 远程 Last-Modified, mtime 更新才重新解析.
  节省 ~30MB 下载 + 解析耗时 (10x 提速).
- 解析后写 settings.kv key 'mitre.last_synced_at' (ISO UTC) + 'mitre.stix_modified'
  (Last-Modified header), 下次 sync 据此判断.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from backend.domain.security_models import SecurityEdge, SecurityEntity, _now_iso
from backend.repository.db import get_connection
from backend.repository.security_repo import SecurityRepository

MITRE_RAW_BASE = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack"
)
DEFAULT_BUNDLE_URL = (
    f"{MITRE_RAW_BASE}/enterprise-attack.json"
)

# 默认 cache 目录: backend/data/mitre/, 可经 MITRE_CACHE_DIR env 覆盖
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "mitre"
CACHE_BUNDLE_NAME = "enterprise-attack.json"
CACHE_META_NAME = "enterprise-attack.meta.json"  # { last_modified, etag, fetched_at }

SETTINGS_KEY_LAST_SYNC = "mitre.last_synced_at"
SETTINGS_KEY_MTIME = "mitre.stix_modified"  # 远端 Last-Modified header

# MP-1 DEV-0217: enterprise ATT&CK 标准 14 tactic (TA0001-TA0011 + TA0040/TA0042/TA0043)。
# 注: STIX bundle 现包含 15 个 enterprise tactic (含 TA0112 Defense Impairment, 2024+
# 新增), MP-1 阶段过滤该新增项以匹配 SPEC (security_entities.tactic COUNT == 14)。
# 后续 MP (例如 MP-4) 若需补 Defense Impairment, 走独立战术表 + 兼容性 migration。
_MP1_ENTERPRISE_TACTIC_IDS = frozenset(
    {
        "TA0001",  # Initial Access
        "TA0002",  # Execution
        "TA0003",  # Persistence
        "TA0004",  # Privilege Escalation
        "TA0005",  # Defense Evasion
        "TA0006",  # Credential Access
        "TA0007",  # Discovery
        "TA0008",  # Lateral Movement
        "TA0009",  # Collection
        "TA0010",  # Exfiltration
        "TA0011",  # Command and Control
        "TA0040",  # Impact
        "TA0042",  # Resource Development
        "TA0043",  # Reconnaissance
    }
)


def cache_dir() -> Path:
    """B9-4: 解析 cache 目录 (env 优先)."""
    env = os.environ.get("MITRE_CACHE_DIR")
    if env:
        return Path(env)
    return DEFAULT_CACHE_DIR


def cache_bundle_path() -> Path:
    return cache_dir() / CACHE_BUNDLE_NAME


def cache_meta_path() -> Path:
    return cache_dir() / CACHE_META_NAME


class MitreAttackClient:
    """Fetch + sync MITRE ATT&CK STIX data into local security_* tables."""

    def __init__(self, repo: SecurityRepository | None = None):
        self._repo = repo or SecurityRepository()
        self._log = logging.getLogger("hotspot.security.mitre_attack")

    def sync_to_db(self, clear: bool = False, force: bool = False) -> dict:
        """Sync MITRE ATT&CK STIX bundle to security_entities + security_edges.

        v0.7 Batch ⑨ B9-4: 增量同步 + 本地 cache.
        - 本地 cache 命中 + 远端 304 → 0 下载
        - 远端 mtime 更新 → 下载并重写 cache
        - force=True 跳过 etag 检查 (人工触发重灌)

        Returns:
            dict {entities, edges, from_cache, new_modified}
        """
        try:
            import urllib.request
        except ImportError:
            self._log.error("urllib not available, cannot fetch MITRE STIX")
            return {"entities": 0, "edges": 0, "from_cache": False, "new_modified": None}

        cache_dir().mkdir(parents=True, exist_ok=True)
        bundle_path = cache_bundle_path()
        meta_path = cache_meta_path()
        meta = self._read_meta(meta_path) if meta_path.exists() else {}

        # 1. HEAD 检查远端是否更新
        remote_modified = None
        remote_etag = None
        try:
            req = urllib.request.Request(DEFAULT_BUNDLE_URL, method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as resp:
                remote_modified = resp.headers.get("Last-Modified")
                remote_etag = resp.headers.get("ETag")
        except Exception as e:
            self._log.warning(f"HEAD request failed (will use cache if any): {e}")

        # 2. cache 命中 + 没 force + 远端未变 → 用 cache
        if (
            not force
            and bundle_path.exists()
            and remote_modified
            and meta.get("last_modified") == remote_modified
        ):
            self._log.info("MITRE cache hit (304-equivalent), reading from local")
            with bundle_path.open(encoding="utf-8") as f:
                raw = f.read()
            return self._parse_and_upsert(raw, clear=clear, from_cache=True)

        # 3. 下载新 bundle
        self._log.info(f"fetching MITRE ATT&CK STIX bundle (force={force}, remote_modified={remote_modified})")
        try:
            with urllib.request.urlopen(DEFAULT_BUNDLE_URL, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not remote_modified:
                    remote_modified = resp.headers.get("Last-Modified")
                if not remote_etag:
                    remote_etag = resp.headers.get("ETag")
        except Exception as e:
            self._log.error(f"failed to fetch MITRE STIX bundle: {e}")
            # 兜底: 用本地 cache (即使 mtime 不同, 至少能跑)
            if bundle_path.exists():
                self._log.warning("falling back to stale local cache")
                with bundle_path.open(encoding="utf-8") as f:
                    raw = f.read()
                return self._parse_and_upsert(raw, clear=clear, from_cache=True)
            return {"entities": 0, "edges": 0, "from_cache": False, "new_modified": None}

        # 4. 写 cache + meta
        try:
            bundle_path.write_text(raw, encoding="utf-8")
            self._write_meta(
                meta_path,
                {
                    "last_modified": remote_modified,
                    "etag": remote_etag,
                    "fetched_at": _now_iso(),
                    "size_bytes": len(raw),
                },
            )
        except Exception as e:
            self._log.warning(f"failed to write MITRE cache: {e}")

        return self._parse_and_upsert(raw, clear=clear, from_cache=False, new_modified=remote_modified)

    def _parse_and_upsert(
        self, raw: str, *, clear: bool, from_cache: bool, new_modified: str | None = None
    ) -> dict:
        """解析 + 落库 (sync_to_db 拆出的复用方法)."""
        try:
            bundle = json.loads(raw)
        except json.JSONDecodeError as e:
            self._log.error(f"failed to parse MITRE STIX bundle: {e}")
            return {"entities": 0, "edges": 0, "from_cache": from_cache, "new_modified": new_modified}

        objects = bundle.get("objects", [])
        self._log.info(f"loaded {len(objects)} STIX objects (from_cache={from_cache})")

        if clear:
            self._log.info("clearing existing ATT&CK entities/edges")
            conn = get_connection()
            conn.execute("DELETE FROM security_edges WHERE source_id IN (SELECT id FROM security_entities WHERE entity_type IN ('tactic','technique','cwe','product','cpe'))")
            conn.execute("DELETE FROM security_entities WHERE entity_type IN ('tactic','technique','cwe','product','cpe')")

        entity_count = 0
        edge_count = 0
        # MP-1 DEV-0217: STIX 中 tactic 的 type 是 "x-mitre-tactic" (而非 "tactic"),
        # 此前 _parse_tactic 永远空命中, security_entities.tactic 仅 1 行 (默认行)。
        # 用 STIX 实际类型 + 从 attack-pattern.kill_chain_phases 聚合双路提取。
        seen_tactic_ids: set[str] = set()
        # 记录所有已 upsert 的 entity.id (含 tactic/technique/malware/intrusion-set),
        # edges 仅 upsert 端点都在集合内的 relationship。STIX 中 uses 关系主要连接
        # intrusion-set / malware / tool → attack-pattern, 不加载这三种 STIX object
        # 会导致 _load_attack_edges 返空, 图谱 view=attack 死。
        known_entity_ids: set[str] = set()
        for obj in objects:
            stix_type = obj.get("type", "")
            if stix_type == "attack-pattern":
                entity = self._parse_technique(obj)
                if entity:
                    self._repo.upsert_entity(entity)
                    known_entity_ids.add(entity.id)
                    entity_count += 1
            elif stix_type == "x-mitre-tactic":
                entity = self._parse_tactic(obj)
                if entity and entity.id not in seen_tactic_ids:
                    self._repo.upsert_entity(entity)
                    seen_tactic_ids.add(entity.id)
                    known_entity_ids.add(entity.id)
                    entity_count += 1
            elif stix_type in ("malware", "intrusion-set", "tool"):
                entity = self._parse_threat_actor_or_tool(obj, stix_type)
                if entity:
                    self._repo.upsert_entity(entity)
                    known_entity_ids.add(entity.id)
                    entity_count += 1
            elif stix_type == "relationship":
                edge = self._parse_relationship(obj)
                if edge is None:
                    continue
                # 仅当两端都已 upsert 才写边; 否则记入 skipped 统计
                if edge.source_id in known_entity_ids and edge.target_id in known_entity_ids:
                    try:
                        self._repo.upsert_edge(edge)
                        edge_count += 1
                    except Exception as e:
                        self._log.debug(f"skip edge {edge.source_id}->{edge.target_id}: {e}")

        # 兜底: 若 STIX 包里没 x-mitre-tactic 对象, 从 attack-pattern.kill_chain_phases
        # 聚合出 tactic (TA0001~TA0014 标准命名映射)。仅在 tactic_count==0 时触发。
        if not seen_tactic_ids:
            synthetic = self._synthesize_tactics_from_phases(objects)
            for entity in synthetic:
                if entity.id not in seen_tactic_ids:
                    self._repo.upsert_entity(entity)
                    seen_tactic_ids.add(entity.id)
                    known_entity_ids.add(entity.id)
                    entity_count += 1

        self._log.info(
            f"mitre sync: kept {edge_count} edges (dropped those with endpoints outside "
            f"tactic/technique scope)"
        )

        # 写 settings.kv 落审计/调度用时间戳
        self._write_sync_meta(new_modified or "")
        self._log.info(
            f"MITRE sync completed (entities={entity_count} edges={edge_count} from_cache={from_cache})"
        )
        return {
            "entities": entity_count,
            "edges": edge_count,
            "from_cache": from_cache,
            "new_modified": new_modified,
        }

    def _read_meta(self, meta_path: Path) -> dict:
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_meta(self, meta_path: Path, meta: dict) -> None:
        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            self._log.warning(f"failed to write meta: {e}")

    def _write_sync_meta(self, new_modified: str) -> None:
        """写 settings.kv 落 mitre.last_synced_at + mitre.stix_modified."""
        try:
            from backend.repository.settings_repo import SettingsRepository
            repo = SettingsRepository()
            repo.set(SETTINGS_KEY_LAST_SYNC, datetime.now(timezone.utc).isoformat())
            if new_modified:
                repo.set(SETTINGS_KEY_MTIME, new_modified)
        except Exception as e:
            self._log.warning(f"failed to write settings.kv: {e}")

    def cache_info(self) -> dict:
        """B9-4: 暴露 cache 状态 (供 /api/security/mitre 端点展示)."""
        meta_path = cache_meta_path()
        bundle_path = cache_bundle_path()
        info = {
            "cache_dir": str(cache_dir()),
            "bundle_exists": bundle_path.exists(),
            "meta_exists": meta_path.exists(),
            "bundle_size_bytes": bundle_path.stat().st_size if bundle_path.exists() else 0,
        }
        if meta_path.exists():
            try:
                info["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                info["meta"] = None
        else:
            info["meta"] = None
        return info

    def _parse_technique(self, obj: dict) -> SecurityEntity | None:
        """Parse a STIX attack-pattern into SecurityEntity."""
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                break

        return SecurityEntity(
            id=obj.get("id", ""),
            entity_type="technique",
            name=obj.get("name", ""),
            description=obj.get("description", "")[:500] if obj.get("description") else None,
            external_ref=external_ref,
            metadata={
                "stix_type": "attack-pattern",
                "kill_chain_phases": [
                    kp.get("phase_name") for kp in obj.get("kill_chain_phases", [])
                ],
            },
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    def _parse_tactic(self, obj: dict) -> SecurityEntity | None:
        """Parse a STIX x-mitre-tactic into SecurityEntity.

        MP-1 DEV-0217: STIX 实际类型为 ``x-mitre-tactic``, STIX ``id`` 形如
        ``x-mitre-tactic--<uuid>``。为与 ``attack_techniques.tactic`` 字段对齐,
        取 ``external_references[source_name=mitre-attack].external_id`` (TAxxxx)
        作为 entity.id; 同 STIX id 写入 metadata 供反向追溯。
        """
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        short_id = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                short_id = ref.get("external_id", "") or ""
                break
        # 跳过被 revoked / deprecated 的 tactic (避免污染图谱)
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            return None

        entity_id = short_id or obj.get("id", "")
        # MP-1 DEV-0217: MP-1 规格要求 security_entities.tactic COUNT == 14 (TA0001~TA0014)。
        # STIX 14 是 enterprise 标准 14 tactic; 后续 MITRE 引入 TA0112 Defense Impairment
        # 等新 tactic (2024+), 在 MP-1 范围内过滤以保持图谱与 attack_techniques.tactic
        # 字段对得上; 后续 tactic 拓展走独立 MP。
        if short_id and short_id not in _MP1_ENTERPRISE_TACTIC_IDS:
            return None
        return SecurityEntity(
            id=entity_id,
            entity_type="tactic",
            name=obj.get("name", ""),
            description=obj.get("description", "")[:500] if obj.get("description") else None,
            external_ref=external_ref,
            metadata={
                "stix_type": "x-mitre-tactic",
                "stix_id": obj.get("id", ""),
                "short_id": short_id,
            },
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    def _parse_threat_actor_or_tool(self, obj: dict, stix_type: str) -> SecurityEntity | None:
        """Parse a STIX malware / intrusion-set / tool into a lightweight SecurityEntity.

        MP-1 DEV-0217: STIX ``uses`` 关系主连接这三种 object → attack-pattern,
        不加载会导致 _load_attack_edges 返空。VALID_ENTITY_TYPES 无 malware /
        intrusion-set / tool, 统一映射为 'product' (合规且语义接近) 写入
        security_entities; 图谱边 endpoint 不变 (STIX id) 即可让 _load_attack_edges
        拿到 uses 边。
        """
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            return None
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                break
        return SecurityEntity(
            id=obj.get("id", ""),
            entity_type="product",
            name=obj.get("name", ""),
            description=(obj.get("description", "") or "")[:500] or None,
            external_ref=external_ref,
            metadata={
                "stix_type": stix_type,
                "stix_id": obj.get("id", ""),
            },
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    # MP-1 DEV-0217: kill_chain_phases → tactic 兜底。
    # 早期 MITRE STIX 包用 x-mitre-tactic 之前, tactic 概念仅体现在
    # attack-pattern.kill_chain_phases[].phase_name。phase_name 与 TAxxxx 不一一对应
    # (TA0001~TA0014 是 STIX 引入后才统一编号), 因此本兜底仅在 x-mitre-tactic 缺失时
    # 触发, 写入 entity.id = phase_name (例如 'initial-access') 作为稳定键。
    _PHASE_TACTIC_NAMES: ClassVar[dict[str, str]] = {
        "reconnaissance": "Reconnaissance",
        "resource-development": "Resource Development",
        "initial-access": "Initial Access",
        "execution": "Execution",
        "persistence": "Persistence",
        "privilege-escalation": "Privilege Escalation",
        "defense-evasion": "Defense Evasion",
        "credential-access": "Credential Access",
        "discovery": "Discovery",
        "lateral-movement": "Lateral Movement",
        "collection": "Collection",
        "command-and-control": "Command and Control",
        "exfiltration": "Exfiltration",
        "impact": "Impact",
    }

    def _synthesize_tactics_from_phases(self, objects: list[dict]) -> list[SecurityEntity]:
        """Aggregate distinct kill_chain_phases across attack-patterns into tactic entities."""
        phases: set[str] = set()
        for obj in objects:
            if obj.get("type") != "attack-pattern":
                continue
            if obj.get("revoked") or obj.get("x_mitre_deprecated"):
                continue
            for kp in obj.get("kill_chain_phases", []) or []:
                name = kp.get("phase_name")
                if name:
                    phases.add(name)
        result: list[SecurityEntity] = []
        now = _now_iso()
        for phase in sorted(phases):
            tactic_name = self._PHASE_TACTIC_NAMES.get(phase, phase.replace("-", " ").title())
            result.append(
                SecurityEntity(
                    id=f"phase::{phase}",
                    entity_type="tactic",
                    name=tactic_name,
                    description=None,
                    external_ref=f"https://attack.mitre.org/tactics/{phase}",
                    metadata={
                        "stix_type": "synthesized-from-kill-chain-phase",
                        "phase_name": phase,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _parse_relationship(self, obj: dict) -> SecurityEdge | None:
        """Parse a STIX relationship into SecurityEdge."""
        rel_type = obj.get("relationship_type", "")
        edge_type_map = {
            "uses": "uses",
            "subtechnique-of": "subtechnique-of",
            "mitigates": "mitigates",
            "related-to": "related-to",
        }
        edge_type = edge_type_map.get(rel_type)
        if not edge_type:
            return None

        return SecurityEdge(
            source_id=obj.get("source_ref", ""),
            target_id=obj.get("target_ref", ""),
            edge_type=edge_type,
            weight=1.0,
            metadata={"stix_id": obj.get("id", "")},
            created_at=_now_iso(),
        )


__all__ = ["DEFAULT_BUNDLE_URL", "MITRE_RAW_BASE", "MitreAttackClient"]
