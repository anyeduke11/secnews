"""v1.0 C13 全量保真迁移统一服务 (R11/R20 收口) — 替换 T16+T18 散落实现.

三源 (legacy_source enum):
  - 'dev_seed'             — dev_data/seed.json 15 条 (测试样本, 不进生产)
  - 'warm.knowledge_items' — 生产 warm.db 3800 行 (T18 旧表 18 字段无 body)
  - 'wiki_items'           — llm-wiki-2.0/items/knowledge_*.md 孤儿 (frontmatter.id)

设计要点 (C13 vs T16/T18 缺陷):
  - 单一真相源 v1_legacy_mapping (UNIQUE(legacy_source, legacy_id, legacy_revision))
  - 旧数据全落 status='legacy' (5 态, 业务禁止跳 publish→legacy)
  - 后台 promote job 据规则批 promote 'legacy' → 'published' (专用 _promote_legacy 守卫)
  - content_hash = sha256(legacy_id + title + source_url + body) 防 T18 撞库
  - 分页: ORDER BY ingested_at ASC + LIMIT/OFFSET 游标稳定
  - 4 账分列: applied / awaiting_review / quarantined / skipped / failed
  - Mimosa 红线: 禁 header-only 蒙混 / 禁 kl:publish 直落 published / 禁 mock 替真数据

R11 (T18 body 蒙混 + kl:publish→published 污染 C12 reuse 池) / R20 (T16 无 mapping 表) 收口.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_PATH = REPO_ROOT / "dev_data" / "seed.json"

# legacy_source enum (C13 单一真相源 v1_legacy_mapping)
LEGACY_SOURCE_SEED = "dev_seed"
LEGACY_SOURCE_WARM = "warm.knowledge_items"
LEGACY_SOURCE_WIKI = "wiki_items"

# mapping.status 4 账 (+ failed)
MAPPING_APPLIED = "applied"
MAPPING_AWAITING = "awaiting_review"
MAPPING_QUARANTINED = "quarantined"
MAPPING_SKIPPED = "skipped"
MAPPING_FAILED = "failed"

# v1_knowledge status 5 态 (C13 加 'legacy')
STATUS_LEGACY = "legacy"

# kind/domain 映射 (T18 已落, 沿用 + 扩展 wiki source 识别)
DOMAIN_TO_KIND: dict[str, str] = {
    "ai": "reference",
    "security": "playbook",
    "dev": "pattern",
    "startup": "reference",
    "finance": "reference",
    "": "reference",
}

# wiki md frontmatter ID 提取 (兼容 T11 fix wiki_path 格式 items/knowledge_{id}.md)
WIKI_FILENAME_RE = re.compile(r"^knowledge_(?P<id>[A-Za-z0-9_-]+)\.md$")
WIKI_FRONTMATTER_ID_RE = re.compile(r"^\s*id:\s*['\"]?(?P<id>[A-Za-z0-9_-]+)['\"]?\s*$", re.MULTILINE)

# body 字节门槛 (T18 header-only 蒙混 < 200 必被 quarantine)
MIN_BODY_BYTES_FOR_PROMOTE = 200


def _ulid26() -> str:
    """26 字符 ULID (random.choice, T11 fix 避免 UNIQUE 撞库)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(legacy_id: str, title: str, source_url: str, body: str) -> str:
    """C13 防 T18 撞库: 加 legacy_id 入 hash (同 title/source_url/body 但不同 old_id 区分)."""
    payload = json.dumps(
        {"legacy_id": legacy_id, "title": title, "source_url": source_url, "body": body},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class MigrateBatch:
    """C13 单源 batch 结果 (走 v1_legacy_mapping 持久)."""

    legacy_source: str
    batch_id: str
    candidates: int = 0
    applied: int = 0
    awaiting_review: int = 0
    quarantined: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    sample_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacy_source": self.legacy_source,
            "batch_id": self.batch_id,
            "candidates": self.candidates,
            "applied": self.applied,
            "awaiting_review": self.awaiting_review,
            "quarantined": self.quarantined,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
            "sample_ids": self.sample_ids,
        }


@dataclass
class PromoteBatch:
    """C13 后台 promote job 结果."""

    candidates: int = 0
    promoted: int = 0
    kept_legacy: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "promoted": self.promoted,
            "kept_legacy": self.kept_legacy,
            "errors": self.errors,
        }


class LegacyMigrateServiceV1:
    """C13 统一迁移服务 (T16 15 seed + T18 3800 warm + wiki 旧 md 整合).

    单一真相源 v1_legacy_mapping.
    旧数据全落 status='legacy' (5 态), 后台 job 据规则批 promote.
    """

    def __init__(self, *, seed_path: Path | None = None, wiki_root: Path | None = None) -> None:
        self._seed_path = seed_path or SEED_PATH
        # wiki_root 走 env HOTSPOT_WIKI_ROOT; 测试 fixture 可传 tmp
        if wiki_root is None:
            try:
                from backend.wiki_fs.root import resolve_wiki_root
                wiki_root = resolve_wiki_root()
            except Exception:
                env_root = os.environ.get("HOTSPOT_WIKI_ROOT")
                wiki_root = Path(env_root) if env_root else REPO_ROOT / "wiki"
        self._wiki_root = Path(wiki_root)
        self._wiki_items_dir = self._wiki_root / "items"

    # ------------------------------------------------------------------
    # 1) dev_seed (T16) — dev_data/seed.json 15 条
    # ------------------------------------------------------------------
    def migrate_seed(self, apply: bool, batch_id: str) -> MigrateBatch:
        """T16: dev_data/seed.json 15 knowledge (测试样本, 含 body).

        全部入 v1_knowledge.status='legacy' (同 T18 一致, 避免业务状态污染).
        """
        result = MigrateBatch(legacy_source=LEGACY_SOURCE_SEED, batch_id=batch_id)
        if not self._seed_path.exists():
            result.errors.append(f"seed.json not found: {self._seed_path}")
            return result

        try:
            data = json.loads(self._seed_path.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(f"read seed.json failed: {e}")
            return result

        items = data.get("knowledge", [])
        result.candidates = len(items)
        if not apply:
            return result

        conn = get_connection()
        for item in items:
            old_id = item.get("id", "")
            if not old_id:
                result.failed += 1
                result.errors.append("seed item missing id")
                continue
            title = (item.get("title", "") or "")[:200]
            body = item.get("body", "") or ""
            kind = item.get("kind", "reference")
            source_url = item.get("source_url", "") or ""
            content_hash = _content_hash(old_id, title, source_url, body)
            # 幂等: 同 (legacy_source, legacy_id) 已 mapping → skipped
            existing = conn.execute(
                "SELECT id, status FROM v1_legacy_mapping "
                "WHERE legacy_source = ? AND legacy_id = ?",
                (LEGACY_SOURCE_SEED, old_id),
            ).fetchone()
            if existing:
                result.skipped += 1
                self._audit("knowledge.legacy_migrated.skip", old_id, {
                    "from": old_id, "reason": "mapping_exists",
                    "existing_mapping_id": existing[0], "status": existing[1],
                })
                continue
            # content_hash 命中 v1_knowledge 已有 → skipped
            if self._existing_knowledge_by_hash(conn, content_hash):
                result.skipped += 1
                self._audit("knowledge.legacy_migrated.skip", old_id, {
                    "from": old_id, "reason": "content_hash_exists",
                })
                continue
            new_id = _ulid26()
            try:
                self._insert_legacy_knowledge(
                    conn, new_id=new_id, kind=kind, title=title, body=body,
                    content_hash=content_hash, source_url=source_url,
                )
                mapping_status = MAPPING_AWAITING if len(body.encode("utf-8")) >= MIN_BODY_BYTES_FOR_PROMOTE else MAPPING_APPLIED
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_SEED, legacy_id=old_id,
                    legacy_revision=None, new_id=new_id, content_hash=content_hash,
                    status=mapping_status, batch_id=batch_id,
                )
                if mapping_status == MAPPING_AWAITING:
                    result.awaiting_review += 1
                else:
                    result.applied += 1
                self._audit("knowledge.legacy_migrated", new_id, {
                    "from": old_id, "kind": kind, "source": LEGACY_SOURCE_SEED,
                    "mapping_status": mapping_status, "batch_id": batch_id,
                })
            except sqlite3.IntegrityError as e:
                # UNIQUE 撞库 (同 batch 内同 legacy_id): 视作 skipped
                result.skipped += 1
                self._audit("knowledge.legacy_migrated.skip", old_id, {
                    "from": old_id, "reason": "integrity_collision", "error": str(e),
                })
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{old_id}: {e}")
                self._insert_failed_mapping(
                    conn, legacy_source=LEGACY_SOURCE_SEED, legacy_id=old_id,
                    new_id=new_id, content_hash=content_hash, error=str(e),
                    batch_id=batch_id,
                )
        conn.commit()
        return result

    # ------------------------------------------------------------------
    # 2) warm.knowledge_items (T18 重写) — 真实 warm.db 3800 行
    # ------------------------------------------------------------------
    def migrate_warm(
        self, apply: bool, batch_id: str, *, offset: int = 0, limit: int = 500,
    ) -> MigrateBatch:
        """T18 重写: warm.knowledge_items (3800 行) → v1_knowledge.status='legacy'.

        关键修复 (vs T18 缺陷):
          1) kl:publish 走 'legacy' (非 'published') — 避免污染 C12 R16.5 reuse 池
          2) body lookup: 先 row.body (空), 否则扫 wiki_root/items/knowledge_{old_id}.md
          3) content_hash 加 legacy_id 防 T18 撞库
          4) 4 账分列: applied / awaiting_review / quarantined / skipped / failed
          5) 分页游标: ORDER BY ingested_at ASC + LIMIT/OFFSET (稳定, 不漏不重)

        Mimosa 红线: warm body 全空 + wiki 没命中 → quarantined (不入 v1_knowledge).
        """
        result = MigrateBatch(legacy_source=LEGACY_SOURCE_WARM, batch_id=batch_id)
        try:
            conn = get_connection()
        except Exception as e:
            result.errors.append(f"db connection failed: {e}")
            return result

        try:
            rows = conn.execute(
                "SELECT id, title, source, source_url, domain, topic, type, "
                "tags, concepts, compiled, ingested_at, updated_at, lifecycle "
                "FROM warm.knowledge_items "
                "WHERE (lifecycle IS NULL OR lifecycle != 'kl:deduped') "
                "ORDER BY ingested_at ASC, id ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        except sqlite3.OperationalError as e:
            result.errors.append(f"warm_db SELECT failed: {e}")
            return result

        result.candidates = len(rows)
        result.sample_ids = [r[0] for r in rows[:3]]
        if not apply:
            return result

        for r in rows:
            old_id = r[0]
            title = r[1] or ""
            source = r[2] or ""
            source_url = r[3] or ""
            domain = r[4] or ""
            topic = r[5] or ""
            type_ = r[6] or ""
            tags_json = r[7]
            concepts_json = r[8]
            compiled = r[9]
            ingested_at = r[10]
            updated_at = r[11]
            lifecycle = r[12]

            # 字段映射
            kind = DOMAIN_TO_KIND.get(domain, "reference")
            title_t = title[:200]

            # body lookup: 先 wiki 命中 (真实 body), 再 row 拼接 (兜底 header-only)
            wiki_body = self._lookup_wiki_body(old_id)
            if wiki_body:
                body = wiki_body
            else:
                # Mimosa 红线: T18 header-only 蒙混 → C13 走 quarantined
                body = self._build_header_body(type_, tags_json, concepts_json, source_url, topic, source)
            body_bytes = len(body.encode("utf-8"))
            content_hash = _content_hash(old_id, title_t, source_url, body)

            # 幂等: mapping 已有 → skipped
            existing_map = conn.execute(
                "SELECT id, status FROM v1_legacy_mapping "
                "WHERE legacy_source = ? AND legacy_id = ?",
                (LEGACY_SOURCE_WARM, old_id),
            ).fetchone()
            if existing_map:
                result.skipped += 1
                continue
            # content_hash 命中 v1_knowledge 已有 → skipped
            if self._existing_knowledge_by_hash(conn, content_hash):
                result.skipped += 1
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WARM, legacy_id=old_id,
                    legacy_revision=None, new_id="SKIP", content_hash=content_hash,
                    status=MAPPING_SKIPPED, batch_id=batch_id,
                )
                continue
            new_id = _ulid26()
            # promote 候选: lifecycle=kl:publish + body ≥ 200 字节 + wiki 命中
            is_promote_candidate = (
                lifecycle == "kl:publish"
                and wiki_body is not None
                and body_bytes >= MIN_BODY_BYTES_FOR_PROMOTE
            )
            if not wiki_body and body_bytes < MIN_BODY_BYTES_FOR_PROMOTE:
                # Mimosa 红线: 真 body 没找到 + header-only < 200 → quarantined (不入 v1_knowledge)
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WARM, legacy_id=old_id,
                    legacy_revision=None, new_id="QUARANTINE", content_hash=content_hash,
                    status=MAPPING_QUARANTINED, batch_id=batch_id,
                    error="wiki_body_not_found + header_only_below_threshold",
                )
                result.quarantined += 1
                self._audit("knowledge.legacy_quarantined", old_id, {
                    "from": old_id, "reason": "no_body_no_wiki",
                    "lifecycle": lifecycle, "domain": domain, "batch_id": batch_id,
                })
                continue
            try:
                self._insert_legacy_knowledge(
                    conn, new_id=new_id, kind=kind, title=title_t, body=body,
                    content_hash=content_hash, source_url=source_url,
                    lifecycle=lifecycle, compiled_at=ingested_at if compiled else None,
                    wiki_path=f"items/knowledge_{old_id}.md" if wiki_body else None,
                )
                mapping_status = MAPPING_AWAITING if is_promote_candidate else MAPPING_APPLIED
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WARM, legacy_id=old_id,
                    legacy_revision=None, new_id=new_id, content_hash=content_hash,
                    status=mapping_status, batch_id=batch_id,
                )
                if mapping_status == MAPPING_AWAITING:
                    result.awaiting_review += 1
                else:
                    result.applied += 1
                self._audit("knowledge.legacy_migrated", new_id, {
                    "from": old_id, "kind": kind, "source": LEGACY_SOURCE_WARM,
                    "lifecycle": lifecycle, "domain": domain,
                    "mapping_status": mapping_status, "batch_id": batch_id,
                })
            except sqlite3.IntegrityError as e:
                result.skipped += 1
                self._audit("knowledge.legacy_migrated.skip", old_id, {
                    "from": old_id, "reason": "integrity_collision", "error": str(e),
                })
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{old_id}: {e}")
                self._insert_failed_mapping(
                    conn, legacy_source=LEGACY_SOURCE_WARM, legacy_id=old_id,
                    new_id=new_id, content_hash=content_hash, error=str(e),
                    batch_id=batch_id,
                )
        conn.commit()
        return result

    # ------------------------------------------------------------------
    # 3) wiki md 孤儿 (走不到 warm 的旧 md 走 v1_knowledge)
    # ------------------------------------------------------------------
    def migrate_wiki(self, apply: bool, batch_id: str) -> MigrateBatch:
        """扫 wiki_root/items/knowledge_*.md, frontmatter.id 匹配.

        走不到 warm 的孤儿 md 也走 v1_knowledge.status='legacy'
        (如: 旧 wiki 目录残留, 维护人员手动加过但 warm 没记录).
        """
        result = MigrateBatch(legacy_source=LEGACY_SOURCE_WIKI, batch_id=batch_id)
        if not self._wiki_items_dir.exists():
            result.errors.append(f"wiki items dir not found: {self._wiki_items_dir}")
            return result

        files = sorted(self._wiki_items_dir.glob("knowledge_*.md"))
        result.candidates = len(files)
        if not apply or not files:
            return result

        conn = get_connection()
        for fpath in files:
            m = WIKI_FILENAME_RE.match(fpath.name)
            if not m:
                result.failed += 1
                result.errors.append(f"unrecognized filename: {fpath.name}")
                continue
            legacy_id = m.group("id")
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"read {fpath.name}: {e}")
                continue
            fm_match = WIKI_FRONTMATTER_ID_RE.search(text[:500])
            fm_id = fm_match.group("id") if fm_match else legacy_id
            # body: frontmatter 之外
            body = self._extract_wiki_body(text)
            if not body:
                result.quarantined += 1
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WIKI, legacy_id=fm_id,
                    legacy_revision=None, new_id="QUARANTINE", content_hash="",
                    status=MAPPING_QUARANTINED, batch_id=batch_id,
                    error="wiki_body_empty",
                )
                continue
            content_hash = _content_hash(fm_id, fpath.stem, "", body)
            existing_map = conn.execute(
                "SELECT 1 FROM v1_legacy_mapping WHERE legacy_source = ? AND legacy_id = ?",
                (LEGACY_SOURCE_WIKI, fm_id),
            ).fetchone()
            if existing_map:
                result.skipped += 1
                continue
            if self._existing_knowledge_by_hash(conn, content_hash):
                result.skipped += 1
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WIKI, legacy_id=fm_id,
                    legacy_revision=None, new_id="SKIP", content_hash=content_hash,
                    status=MAPPING_SKIPPED, batch_id=batch_id,
                )
                continue
            new_id = _ulid26()
            try:
                self._insert_legacy_knowledge(
                    conn, new_id=new_id, kind="reference", title=fpath.stem,
                    body=body, content_hash=content_hash, source_url="",
                    wiki_path=str(fpath.relative_to(self._wiki_root)),
                )
                body_bytes = len(body.encode("utf-8"))
                mapping_status = MAPPING_AWAITING if body_bytes >= MIN_BODY_BYTES_FOR_PROMOTE else MAPPING_APPLIED
                self._insert_mapping_row(
                    conn, legacy_source=LEGACY_SOURCE_WIKI, legacy_id=fm_id,
                    legacy_revision=None, new_id=new_id, content_hash=content_hash,
                    status=mapping_status, batch_id=batch_id,
                )
                if mapping_status == MAPPING_AWAITING:
                    result.awaiting_review += 1
                else:
                    result.applied += 1
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{fm_id}: {e}")
        conn.commit()
        return result

    # ------------------------------------------------------------------
    # 4) 后台 promote job (C13 job 56 legacy_promote_due)
    # ------------------------------------------------------------------
    def run_legacy_promote(self, *, now_iso: str | None = None) -> PromoteBatch:
        """C13 后台 promote: legacy + awaiting_review + body≥200 + wiki_path 命中 → published.

        走 _promote_legacy (knowledge_service 内部守卫) + v1_legacy_promote_log 持久.
        """
        result = PromoteBatch()
        conn = get_connection()
        rows = conn.execute(
            "SELECT m.new_id FROM v1_legacy_mapping m "
            "INNER JOIN v1_knowledge k ON k.id = m.new_id "
            "WHERE m.status = 'awaiting_review' AND k.status = 'legacy' "
            "AND k.body IS NOT NULL AND length(k.body) >= ? "
            "AND k.wiki_path IS NOT NULL",
            (MIN_BODY_BYTES_FOR_PROMOTE,),
        ).fetchall()
        result.candidates = len(rows)
        for r in rows:
            new_id = r[0]
            try:
                self._promote_legacy(new_id, reason="C13 awaiting_review + body_present + wiki_hit")
                # 改 mapping.status
                conn.execute(
                    "UPDATE v1_legacy_mapping SET status = ? WHERE new_id = ?",
                    (MAPPING_APPLIED, new_id),
                )
                result.promoted += 1
            except Exception as e:
                result.kept_legacy += 1
                result.errors.append(f"{new_id}: {e}")
        conn.commit()
        return result

    def _promote_legacy(self, knowledge_id: str, *, reason: str) -> None:
        """CAS: legacy → published (C13 专用守卫, 业务禁止跳 publish→legacy)."""
        conn = get_connection()
        # 取 revision
        row = conn.execute(
            "SELECT revision, status FROM v1_knowledge WHERE id = ?", (knowledge_id,),
        ).fetchone()
        if not row:
            raise LookupError(f"knowledge not found: {knowledge_id}")
        if row[1] != STATUS_LEGACY:
            raise ValueError(f"cannot promote non-legacy: {knowledge_id} status={row[1]}")
        expected_revision = row[0]
        # CAS UPDATE
        cur = conn.execute(
            "UPDATE v1_knowledge SET status = 'published', revision = revision + 1, "
            "allowed_actions_json = ?, promoted_at = ?, promotion_reason = ?, "
            "updated_at = datetime('now', 'localtime'), published_at = COALESCE(published_at, datetime('now', 'localtime')) "
            "WHERE id = ? AND revision = ? AND status = 'legacy'",
            (json.dumps(["create_revision", "deprecate", "retract"], ensure_ascii=False),
             _now_utc_iso(), reason, knowledge_id, expected_revision),
        )
        if cur.rowcount == 0:
            raise RuntimeError(f"promote CAS race: {knowledge_id}")
        # 写 promote_log (UNIQUE 防并发)
        try:
            conn.execute(
                "INSERT INTO v1_legacy_promote_log "
                "(new_id, from_status, to_status, reason, promoted_at, promoted_by) "
                "VALUES (?, 'legacy', 'published', ?, ?, 'system')",
                (knowledge_id, reason, _now_utc_iso()),
            )
        except sqlite3.IntegrityError:
            # 已 promote 过 (UNIQUE 撞库): 视作幂等成功
            pass
        self._audit("knowledge.legacy_promoted", knowledge_id, {
            "from": "legacy", "to": "published", "reason": reason,
        })

    # ------------------------------------------------------------------
    # 只读查询 (Batch 2 D: api 层 SQL 下沉落点)
    # ------------------------------------------------------------------
    def mapping_status(self, batch_id: str | None) -> dict[str, Any]:
        """GET /status 数据面 — v1_legacy_mapping 按 (legacy_source, status) 分组计数.

        Returns: ``{"mapping_total": int, "breakdown": {src: {status: n}},
        "v1_knowledge_legacy": int}`` (version/batch_id 由 api 层包装).
        """
        conn = get_connection()
        params: tuple = ()
        where = ""
        if batch_id:
            where = "WHERE batch_id = ?"
            params = (batch_id,)
        rows = conn.execute(
            f"SELECT legacy_source, status, COUNT(*) AS n "
            f"FROM v1_legacy_mapping {where} "
            f"GROUP BY legacy_source, status "
            f"ORDER BY legacy_source, status",
            params,
        ).fetchall()
        breakdown: dict[str, dict[str, int]] = {}
        total = 0
        for src, st, n in rows:
            breakdown.setdefault(src, {})[st] = n
            total += n
        # v1_knowledge status='legacy' 计数
        legacy_k = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge WHERE status = 'legacy'",
        ).fetchone()[0]
        return {
            "mapping_total": total,
            "breakdown": breakdown,
            "v1_knowledge_legacy": legacy_k,
        }

    def query_mapping(
        self,
        legacy_source: str | None,
        legacy_id: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """GET /mapping 数据面 — v1_legacy_mapping 条件查询 (按 migrated_at 倒序)."""
        conn = get_connection()
        where_parts: list[str] = []
        params: list[Any] = []
        if legacy_source:
            where_parts.append("legacy_source = ?")
            params.append(legacy_source)
        if legacy_id:
            where_parts.append("legacy_id = ?")
            params.append(legacy_id)
        if status:
            where_parts.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        rows = conn.execute(
            f"SELECT legacy_source, legacy_id, legacy_revision, new_id, "
            f"new_revision, status, error, batch_id, migrated_at "
            f"FROM v1_legacy_mapping {where} "
            f"ORDER BY migrated_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            {
                "legacy_source": r[0], "legacy_id": r[1], "legacy_revision": r[2],
                "new_id": r[3], "new_revision": r[4], "status": r[5],
                "error": r[6], "batch_id": r[7], "migrated_at": r[8],
            } for r in rows
        ]

    def promote_log(self, new_id: str | None, limit: int) -> list[dict[str, Any]]:
        """GET /promote/log 数据面 — v1_legacy_promote_log 查询 (按 promoted_at 倒序)."""
        conn = get_connection()
        where = ""
        params: tuple = ()
        if new_id:
            where = "WHERE new_id = ?"
            params = (new_id,)
        rows = conn.execute(
            f"SELECT new_id, from_status, to_status, reason, promoted_at, promoted_by "
            f"FROM v1_legacy_promote_log {where} "
            f"ORDER BY promoted_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            {
                "new_id": r[0], "from_status": r[1], "to_status": r[2],
                "reason": r[3], "promoted_at": r[4], "promoted_by": r[5],
            } for r in rows
        ]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _lookup_wiki_body(self, legacy_id: str) -> str | None:
        """扫 wiki_root/items/knowledge_{id}.md (frontmatter 之后 body)."""
        candidate = self._wiki_items_dir / f"knowledge_{legacy_id}.md"
        if not candidate.exists():
            return None
        try:
            text = candidate.read_text(encoding="utf-8")
        except Exception:
            return None
        body = self._extract_wiki_body(text)
        return body if body else None

    @staticmethod
    def _extract_wiki_body(text: str) -> str:
        """剥 frontmatter ---...--- 之后正文."""
        if not text.startswith("---"):
            return text.strip()
        end = text.find("\n---", 3)
        if end == -1:
            return text.strip()
        return text[end + 4:].strip()

    def _existing_knowledge_by_hash(self, conn: sqlite3.Connection, content_hash: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM v1_knowledge WHERE content_hash = ?", (content_hash,),
        ).fetchone() is not None

    def _insert_legacy_knowledge(
        self, conn: sqlite3.Connection, *, new_id: str, kind: str, title: str, body: str,
        content_hash: str, source_url: str = "", lifecycle: str | None = None,
        compiled_at: str | None = None, wiki_path: str | None = None,
    ) -> None:
        """落 v1_knowledge.status='legacy' (C13 5 态)."""
        now = _now_utc_iso()
        conn.execute(
            "INSERT INTO v1_knowledge "
            "(id, kind, title, body, status, revision, content_hash, "
            " published_at, wiki_path, allowed_actions_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'legacy', 1, ?, ?, ?, ?, ?, ?)",
            (
                new_id, kind, title, body, content_hash,
                compiled_at,  # legacy 入库时记录原 ingested_at 作 published_at 候补
                wiki_path,
                json.dumps(["promote", "retract"], ensure_ascii=False),
                now, now,
            ),
        )

    def _insert_mapping_row(
        self, conn: sqlite3.Connection, *, legacy_source: str, legacy_id: str,
        legacy_revision: str | None, new_id: str, content_hash: str, status: str,
        batch_id: str, error: str | None = None,
    ) -> None:
        try:
            conn.execute(
                "INSERT INTO v1_legacy_mapping "
                "(legacy_source, legacy_id, legacy_revision, new_id, new_revision, "
                " content_hash, status, error, batch_id, migrated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
                (legacy_source, legacy_id, legacy_revision, new_id,
                 content_hash, status, error, batch_id, _now_utc_iso()),
            )
        except sqlite3.IntegrityError:
            # 同一 batch 重复 → 跳过 (UNIQUE 防撞)
            logger.debug(f"mapping dup: {legacy_source}/{legacy_id}/{legacy_revision}")

    def _insert_failed_mapping(
        self, conn: sqlite3.Connection, *, legacy_source: str, legacy_id: str,
        new_id: str, content_hash: str, error: str, batch_id: str,
    ) -> None:
        try:
            self._insert_mapping_row(
                conn, legacy_source=legacy_source, legacy_id=legacy_id,
                legacy_revision=None, new_id=new_id, content_hash=content_hash,
                status=MAPPING_FAILED, batch_id=batch_id, error=error,
            )
        except Exception as e:
            logger.debug(f"failed mapping insert error: {e}")

    @staticmethod
    def _build_header_body(
        type_: str, tags_json: str | None, concepts_json: str | None,
        source_url: str, topic: str, source: str,
    ) -> str:
        """T18 风格 header-only body (C13 仍保留作 fallback, 但走 quarantined if < 200B)."""
        parts: list[str] = []
        if type_:
            parts.append(f"# 类型: {type_}")
        if topic:
            parts.append(f"# 主题: {topic}")
        if source:
            parts.append(f"# 来源: {source}")
        if source_url:
            parts.append(f"## Source: {source_url}")
        try:
            tags_list = json.loads(tags_json) if tags_json else []
        except (json.JSONDecodeError, TypeError):
            tags_list = []
        try:
            concepts_list = json.loads(concepts_json) if concepts_json else []
        except (json.JSONDecodeError, TypeError):
            concepts_list = []
        if tags_list:
            parts.append(f"## Tags: {', '.join(tags_list)}")
        if concepts_list:
            parts.append(f"## Concepts: {', '.join(concepts_list)}")
        return "\n".join(p for p in parts if p).strip()

    def _audit(self, action: str, target: str, detail: dict[str, Any]) -> None:
        try:
            from backend.observability_records import record_audit
            record_audit(actor="c13_legacy_migrate", action=action, target=target, detail=detail)
        except Exception as e:
            logger.debug(f"audit write failed: {e}")


__all__ = [
    "DOMAIN_TO_KIND",
    "LEGACY_SOURCE_SEED",
    "LEGACY_SOURCE_WARM",
    "LEGACY_SOURCE_WIKI",
    "MAPPING_APPLIED",
    "MAPPING_AWAITING",
    "MAPPING_FAILED",
    "MAPPING_QUARANTINED",
    "MAPPING_SKIPPED",
    "MIN_BODY_BYTES_FOR_PROMOTE",
    "STATUS_LEGACY",
    "LegacyMigrateServiceV1",
    "MigrateBatch",
    "PromoteBatch",
]
