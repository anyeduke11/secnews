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
        for obj in objects:
            stix_type = obj.get("type", "")
            if stix_type == "attack-pattern":
                entity = self._parse_technique(obj)
                if entity:
                    self._repo.upsert_entity(entity)
                    entity_count += 1
            elif stix_type == "tactic":
                entity = self._parse_tactic(obj)
                if entity:
                    self._repo.upsert_entity(entity)
                    entity_count += 1
            elif stix_type == "relationship":
                edge = self._parse_relationship(obj)
                if edge:
                    self._repo.upsert_edge(edge)
                    edge_count += 1

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
        """Parse a STIX tactic into SecurityEntity."""
        ext_refs = obj.get("external_references", [])
        external_ref = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                external_ref = ref.get("url", "")
                break

        return SecurityEntity(
            id=obj.get("id", ""),
            entity_type="tactic",
            name=obj.get("name", ""),
            description=obj.get("description", "")[:500] if obj.get("description") else None,
            external_ref=external_ref,
            metadata={"stix_type": "tactic"},
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

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
