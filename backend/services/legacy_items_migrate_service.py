"""v1.0 T18 旧 knowledge_items 853 行数据迁移服务 (走真实 warm.knowledge_items → v1_knowledge).

T16 旧 15 knowledge 走 dev_data/seed.json (T03 已落 v1.0 形状, 含 body);
T18 真落 853 行走 warm.knowledge_items (T00 备份演练已 attach, 18 字段无 body).

设计:
  - LegacyItemsMigrateService.migrate_legacy_items(apply) — SELECT warm.knowledge_items 走 WARM_DB
  - 排除 kl:deduped (无 v1_knowledge status 4 态对应)
  - 字段映射: title→title (≤200 截断) / domain→kind (6 域映射字典) / lifecycle→status / compiled=1 → published_at=ingested_at
  - 剥离 mastery/news_type/tech_stack/folder/attention_score 等不迁字段
  - tags/concepts/source_url 拼入 body header
  - audit_log 走 record_audit(actor="t18_legacy_items_migrate")
  - 派生 content_hash 走 sha256(body + sorted(prerequisites))
  - 幂等: 重复 apply 不重复 (content_hash 存在检测)

不实现 (留 T19): 旧 knowledge_concepts / knowledge_tasks 迁移; 真实 body 补全.
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection

# lifecycle → status 映射 (旧 5 态 → v1_knowledge 4 态)
LIFECYCLE_TO_STATUS: dict[str, str] = {
    "kl:publish": "published",
    "kl:structure": "draft",
    "kl:raw": "draft",
    "kl:refine": "draft",
    "kl:link": "draft",
    # "kl:deduped" 排除 (无 v1_knowledge status 对应)
}

# domain → kind 映射 (旧 5 域 + 1 空 → v1_knowledge 6 kind)
DOMAIN_TO_KIND: dict[str, str] = {
    "ai": "reference",
    "security": "playbook",
    "dev": "pattern",
    "startup": "reference",
    "finance": "reference",
    "": "reference",
    # 空 / unknown 走 reference fallback
}


def _ulid26() -> str:
    """26 字符 ULID (random.choice, T11 fix 避免 UNIQUE 撞库)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LegacyItemsMigrateResult:
    """T18 旧 knowledge_items → v1_knowledge 迁移结果 (借 T09 LegacyHoldResult 风格)."""

    items_candidates: int = 0
    items_applied: int = 0
    items_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    sample_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items_candidates": self.items_candidates,
            "items_applied": self.items_applied,
            "items_skipped": self.items_skipped,
            "errors": self.errors,
            "sample_ids": self.sample_ids,
        }


class LegacyItemsMigrateService:
    """T18 旧 knowledge_items 数据迁移服务 (走 WARM_DB → v1_knowledge)."""

    def __init__(self) -> None:
        self._warm_table = "knowledge_items"

    def _audit(self, action: str, subject_id: str, details: dict[str, Any]) -> None:
        """写 audit_log (复用 observability_records.record_audit 模式, T16 修复后)."""
        try:
            from backend.observability_records import record_audit
            record_audit(actor="t18_legacy_items_migrate", action=action, target=subject_id, detail=details)
        except Exception as e:
            logger.debug(f"audit_log write failed (action={action}): {e}")

    def migrate_legacy_items(self, apply: bool = False) -> LegacyItemsMigrateResult:
        """dry-run: counts + sample; apply: 真落 v1_knowledge (idempotent by content_hash).

        Returns
        -------
        LegacyItemsMigrateResult: counts + errors + sample_ids.

        T18 走 WARM_DB (get_connection 启动期 ATTACH warm, 同 conn 查询).
        """
        result = LegacyItemsMigrateResult()
        # 1) 读 WARM_DB.knowledge_items (get_connection 启动期已 attach)
        try:
            conn = get_connection()
        except Exception as e:
            result.errors.append(f"db connection failed: {e}")
            return result

        try:
            rows = conn.execute(
                "SELECT id, title, source, source_url, domain, topic, type, difficulty, "
                "tags, concepts, mastery, compiled, ingested_at, updated_at, "
                "lifecycle, news_type, tech_stack, attention_score "
                f"FROM warm.{self._warm_table} WHERE lifecycle != 'kl:deduped' "
                "ORDER BY ingested_at DESC LIMIT 4000"
            ).fetchall()
        except sqlite3.OperationalError as e:
            # warm.knowledge_items 表缺失 (fresh test warm db 未建表) — graceful 空集
            result.errors.append(f"warm_db SELECT failed (warm.knowledge_items missing?): {e}")
            return result

        result.items_candidates = len(rows)
        result.sample_ids = [r[0] for r in rows[:3]]

        if not apply:
            return result

        # 2) apply 模式: 真落 v1_knowledge (idempotent by content_hash)
        # 复用同一 conn: ATTACH warm + main hot 在同一连接, 走 hot 写 v1_knowledge
        for r in rows:
            (
                old_id, title, source, source_url, domain, topic, type_, difficulty,
                tags, concepts, mastery, compiled, ingested_at, updated_at,
                lifecycle, news_type, tech_stack, attention_score,
            ) = r
            new_id = _ulid26()
            # 字段映射
            kind = DOMAIN_TO_KIND.get(domain or "", "reference")
            status = LIFECYCLE_TO_STATUS.get(lifecycle or "kl:raw", "draft")
            title_t = (title or "")[:200]
            # body 拼接: header + (tags/concepts/source_url summary)
            body_parts = [f"# 类型: {type_}" if type_ else "",
                          f"# 难度: {difficulty}" if difficulty else ""]
            try:
                tags_list = json.loads(tags) if tags else []
            except (json.JSONDecodeError, TypeError):
                tags_list = []
            try:
                concepts_list = json.loads(concepts) if concepts else []
            except (json.JSONDecodeError, TypeError):
                concepts_list = []
            if tags_list:
                body_parts.append(f"## Tags: {', '.join(tags_list)}")
            if concepts_list:
                body_parts.append(f"## Concepts: {', '.join(concepts_list)}")
            if source_url:
                body_parts.append(f"## Source: {source_url}")
            body = "\n".join(p for p in body_parts if p).strip()
            # 派生 content_hash (T16 + T18 同算法)
            content_hash = hashlib.sha256(
                (body + str([])).encode("utf-8")
            ).hexdigest()
            # 幂等: 同 content_hash 已存在 → 跳过
            existing = conn.execute(
                "SELECT id FROM v1_knowledge WHERE content_hash = ?", (content_hash,),
            ).fetchone()
            if existing:
                result.items_skipped += 1
                self._audit("knowledge.legacy_items_migrated.skip", existing[0], {
                    "from": old_id, "reason": "content_hash_exists",
                })
                continue
            published_at = ingested_at if status == "published" else None
            try:
                conn.execute(
                    "INSERT INTO v1_knowledge "
                    "(id, kind, title, body, status, revision, content_hash, "
                    " published_at, allowed_actions_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?, ?, '[]', ?, ?)",
                    (
                        new_id, kind, title_t, body, status, content_hash, published_at,
                        ingested_at or _now_utc_iso(), updated_at or _now_utc_iso(),
                    ),
                )
                result.items_applied += 1
                self._audit("knowledge.legacy_items_migrated", new_id, {
                    "from": old_id, "kind": kind, "status": status,
                    "lifecycle": lifecycle, "domain": domain,
                })
            except Exception as e:
                result.errors.append(f"{old_id}: {e}")
        conn.commit()
        return result


__all__ = ["DOMAIN_TO_KIND", "LIFECYCLE_TO_STATUS", "LegacyItemsMigrateResult", "LegacyItemsMigrateService"]
