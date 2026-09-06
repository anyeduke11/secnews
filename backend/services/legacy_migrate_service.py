"""v1.0 T16 旧数据迁移服务 (legacy_migrate_service) — 旧 15 knowledge + 旧 20 SK deprecated.

EXECUTION_GUIDE §T16 + contracts §10.3 "已引用对象不删, 只能 archive/retract/supersede".
T14 留 hook: SkillDef 改 status 绕过 frozen dataclass; T16 复用并扩展到旧 15 knowledge 迁移.

设计:
  - LegacyMigrateService.migrate_knowledge (apply / dry-run) — 走 dev_data/seed.json 15 条
  - 旧 20 SK deprecated 走 builtin.py `_skill.__dict__["status"] = "deprecated"` (T14 模式)
  - 写 audit_log (action / subject_id / details_json) 记录每次变更
  - 幂等: 已 deprecated 跳过; 重复 apply 不重复标

不实现 (scope 大, 留 T17):
  - 旧 knowledge_items 表 853 行数据迁移
  - 旧 4 域 → 6 SK 显式映射表 (T14 已收口, T16 只标 deprecated 状态)
  - wiki 单根迁移
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_PATH = REPO_ROOT / "dev_data" / "seed.json"


def _ulid26() -> str:
    """26 字符 ULID (random.choice, T11 fix 避免 UNIQUE 撞库)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LegacyMigrateResult:
    """T16 旧数据迁移结果 (借 T09 LegacyHoldResult 风格: candidates/skipped/errors 三计数)."""

    knowledge_candidates: int = 0
    knowledge_applied: int = 0
    knowledge_skipped: int = 0
    legacy_sks_marked: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_candidates": self.knowledge_candidates,
            "knowledge_applied": self.knowledge_applied,
            "knowledge_skipped": self.knowledge_skipped,
            "legacy_sks_marked": self.legacy_sks_marked,
            "errors": self.errors,
        }


class LegacyMigrateService:
    """T16 旧数据迁移服务 — 旧 15 knowledge + 旧 20 SK deprecated.

    dry-run 与 apply 共用同流程, apply=True 落库 + 写 audit_log; dry-run 仅计数.
    """

    def __init__(self, seed_path: Path | None = None) -> None:
        self._seed_path = seed_path or SEED_PATH

    # ------------------------------------------------------------------
    # 旧 20 SK → deprecated
    # ------------------------------------------------------------------
    def mark_legacy_20_deprecated(self, apply: bool = False) -> tuple[int, list[str]]:
        """把 builtin.py 旧 20 SK (status='legacy_v0') 全标 status='deprecated' (T14 留 hook, T16 启用).

        Returns
        -------
        (marked_count, errors): apply=True 写 audit_log; apply=False 仅计数.
        """
        try:
            from backend.services.skill_registry.builtin import BUILTIN
        except Exception as e:
            return (0, [f"import builtin failed: {e}"])

        candidates: list[Any] = []
        for skill in BUILTIN.list():
            current = getattr(skill, "status", "legacy_v0")
            if current == "deprecated":
                continue  # 幂等: 已 deprecated 跳过
            if current != "legacy_v0":
                continue  # 跳过 v1_active (T14 6 SK), 避免误标
            candidates.append(skill)
        if not apply:
            return (len(candidates), [])

        marked = 0
        errors: list[str] = []
        for skill in candidates:
            try:
                skill.__dict__["status"] = "deprecated"
                marked += 1
                self._audit("skill.deprecated", skill.id, {"from": "legacy_v0", "to": "deprecated"})
            except Exception as e:
                errors.append(f"{skill.id}: {e}")
        return (marked, errors)

    # ------------------------------------------------------------------
    # 旧 15 knowledge → v1_knowledge (dev_data/seed.json 源)
    # ------------------------------------------------------------------
    def migrate_legacy_knowledge(self, apply: bool = False) -> tuple[LegacyMigrateResult, str]:
        """读 dev_data/seed.json 15 knowledge → 走 v1_knowledge (T03 v1.0 形状).

        Returns
        -------
        (result, message): result 含 candidates/applied/skipped/errors; message 描述 dry-run vs apply.

        幂等 (T11 fix 派生):
          - 旧 ID (KNOW001) 映射 content_hash (sha256(body + prerequisites))
          - 第二次 apply 检测同 content_hash 已存在 → skipped
        """
        result = LegacyMigrateResult()
        if not self._seed_path.exists():
            return result, f"seed.json not found: {self._seed_path}"

        try:
            data = json.loads(self._seed_path.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(f"read seed.json failed: {e}")
            return result, "read failed"

        items = data.get("knowledge", [])
        result.knowledge_candidates = len(items)
        if not apply:
            return result, f"dry-run: {len(items)} knowledge candidates"

        conn = get_connection()
        for item in items:
            old_id = item.get("id", "")
            if not old_id:
                continue
            title = item.get("title", "")[:200]
            body = item.get("body", "")
            kind = item.get("kind", "reference")
            status = item.get("status", "draft")
            published_at = item.get("published_at") if status == "published" else None
            review_at = item.get("review_at")
            prerequisites = item.get("prerequisites", [])
            # content_hash 派生 (T11 service 模式): body + prerequisites (排除 reuse_count 等派生字段)
            content_hash = hashlib.sha256(
                (body + str(sorted(prerequisites))).encode("utf-8")
            ).hexdigest()
            # 幂等: 同 content_hash 已存在 → 跳过 (避免重复 insert)
            existing = conn.execute(
                "SELECT id FROM v1_knowledge WHERE content_hash = ?", (content_hash,),
            ).fetchone()
            if existing:
                result.knowledge_skipped += 1
                self._audit("knowledge.legacy_migrated.skip", existing[0], {
                    "from": old_id, "reason": "content_hash_exists",
                })
                continue
            new_id = _ulid26()
            try:
                conn.execute(
                    "INSERT INTO v1_knowledge "
                    "(id, kind, title, body, status, revision, content_hash, "
                    " published_at, review_at, allowed_actions_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, '[]', ?, ?)",
                    (
                        new_id, kind, title, body, status,
                        content_hash, published_at, review_at,
                        _now_utc_iso(), _now_utc_iso(),
                    ),
                )
                result.knowledge_applied += 1
                self._audit("knowledge.legacy_migrated", new_id, {
                    "from": old_id, "kind": kind, "status": status,
                })
            except Exception as e:
                result.errors.append(f"{old_id}: {e}")
        conn.commit()
        return result, f"applied: {result.knowledge_applied} inserted, {result.knowledge_skipped} skipped"

    # ------------------------------------------------------------------
    # audit_log (T08 通用表)
    # ------------------------------------------------------------------
    def _audit(self, action: str, subject_id: str, details: dict[str, Any]) -> None:
        """写 audit_log (复用 observability_records.record_audit 的 schema).

        T17 修复: T16 之前用错列名 (subject_id/details_json/created_at), 实际 schema 是
        actor/action/target/detail/trace_id/occurred_at. 直接调 observability_records.record_audit.
        """
        try:
            from backend.observability_records import record_audit
            record_audit(actor="t16_legacy_migrate", action=action, target=subject_id, detail=details)
        except Exception as e:
            logger.warning(f"audit_log write failed (action={action}): {e}")

    # ------------------------------------------------------------------
    # 顶层入口
    # ------------------------------------------------------------------
    def run(self, apply: bool = False) -> LegacyMigrateResult:
        """T16 一次跑两类迁移 (knowledge + skill deprecated).

        dry-run 模式 (apply=False) 仅计数不落库; apply=True 落库 + 写 audit_log.
        幂等: 重复 apply 不重复标.
        """
        result = LegacyMigrateResult()

        # 1) 旧 20 SK deprecated
        marked, errors = self.mark_legacy_20_deprecated(apply=apply)
        result.legacy_sks_marked = marked
        result.errors.extend(errors)

        # 2) 旧 15 knowledge → v1_knowledge
        kr, _ = self.migrate_legacy_knowledge(apply=apply)
        result.knowledge_candidates = kr.knowledge_candidates
        result.knowledge_applied = kr.knowledge_applied
        result.knowledge_skipped = kr.knowledge_skipped
        result.errors.extend(kr.errors)
        return result


__all__ = ["LegacyMigrateResult", "LegacyMigrateService"]
