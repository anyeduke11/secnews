"""v1.0 T16 旧数据迁移服务 (legacy_migrate_service) — 旧 15 knowledge + 旧 20 SK deprecated.

C13 重构: 知识迁移逻辑委托给 LegacyMigrateServiceV1 (3 源统一), 本文件保留:
  - 旧 20 SK deprecated 标注 (skill_registry builtin, T14/T16 留)
  - 薄壳委派 v1 (T16 旧 15 knowledge 走 migrate_seed)
  - 顶层 run() 入口 (向后兼容: 旧 API / 旧 CLI / 旧黄金案例继续可用)

设计:
  - migrate_legacy_knowledge(apply, batch_id) 走 LegacyMigrateServiceV1.migrate_seed
  - 旧 20 SK deprecated 走 builtin.py `_skill.__dict__["status"] = "deprecated"`
  - 写 audit_log 复用 observability_records.record_audit
  - 幂等: 已 deprecated 跳过; mapping UNIQUE(legacy_source, legacy_id, legacy_revision) 防重复
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.logging_config import logger

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_PATH = REPO_ROOT / "dev_data" / "seed.json"


@dataclass
class LegacyMigrateResult:
    """T16 旧数据迁移结果 (借 T09 LegacyHoldResult 风格: candidates/skipped/errors 三计数).

    C13 扩展: knowledge_applied + knowledge_awaiting_review 区分
    (T16 旧 4 态不分, C13 5 态 + 后台 promote 分账).
    """

    knowledge_candidates: int = 0
    knowledge_applied: int = 0
    knowledge_skipped: int = 0
    knowledge_awaiting_review: int = 0
    legacy_sks_marked: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_candidates": self.knowledge_candidates,
            "knowledge_applied": self.knowledge_applied,
            "knowledge_skipped": self.knowledge_skipped,
            "knowledge_awaiting_review": self.knowledge_awaiting_review,
            "legacy_sks_marked": self.legacy_sks_marked,
            "errors": self.errors,
        }


class LegacyMigrateService:
    """T16 旧数据迁移服务 — 薄壳委派 C13 LegacyMigrateServiceV1.

    向后兼容: 保留 mark_legacy_20_deprecated + migrate_legacy_knowledge + run 接口
    (旧 API / 旧 CLI / 旧黄金案例继续可用).
    """

    def __init__(self, seed_path: Path | None = None) -> None:
        self._seed_path = seed_path or SEED_PATH

    # ------------------------------------------------------------------
    # 旧 20 SK → deprecated (T14/T16 留)
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
    # 旧 15 knowledge → v1_knowledge (C13 委派 v1 migrate_seed)
    # ------------------------------------------------------------------
    def migrate_legacy_knowledge(
        self, apply: bool = False, batch_id: str | None = None,
    ) -> tuple[LegacyMigrateResult, str]:
        """薄壳委派 LegacyMigrateServiceV1.migrate_seed (T16 旧 15 knowledge).

        Returns
        -------
        (result, message): result 4 账分列; message 描述 dry-run vs apply.
        """
        from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
        v1 = LegacyMigrateServiceV1(seed_path=self._seed_path)
        if batch_id is None:
            batch_id = f"t16-seed-{self._seed_path.name}"
        # seed.json 缺失 → T16 旧行为 silent 降级 (errors=[]), 与 v1 行为差异
        # (v1 把缺失写 errors, T16 走 legacy API 静默). 兜底保持向后兼容.
        if not self._seed_path.exists():
            return LegacyMigrateResult(), f"seed.json not found: {self._seed_path}"
        batch = v1.migrate_seed(apply=apply, batch_id=batch_id)
        result = LegacyMigrateResult(
            knowledge_candidates=batch.candidates,
            knowledge_applied=batch.applied,
            knowledge_skipped=batch.skipped,
            knowledge_awaiting_review=batch.awaiting_review,
            errors=list(batch.errors),
        )
        msg = (
            f"applied: {batch.applied} inserted, {batch.awaiting_review} awaiting_review, "
            f"{batch.quarantined} quarantined, {batch.skipped} skipped, {batch.failed} failed"
        ) if apply else f"dry-run: {batch.candidates} knowledge candidates"
        return result, msg

    # ------------------------------------------------------------------
    # audit_log (T08 通用表)
    # ------------------------------------------------------------------
    def _audit(self, action: str, subject_id: str, details: dict[str, Any]) -> None:
        """写 audit_log (复用 observability_records.record_audit 的 schema)."""
        try:
            from backend.observability_records import record_audit
            record_audit(actor="t16_legacy_migrate", action=action, target=subject_id, detail=details)
        except Exception as e:
            logger.warning(f"audit_log write failed (action={action}): {e}")

    # ------------------------------------------------------------------
    # 顶层入口
    # ------------------------------------------------------------------
    def run(self, apply: bool = False, batch_id: str | None = None) -> LegacyMigrateResult:
        """T16 一次跑两类迁移 (knowledge + skill deprecated).

        dry-run 模式 (apply=False) 仅计数不落库; apply=True 落库 + 写 audit_log.
        幂等: 重复 apply 不重复标.
        """
        result = LegacyMigrateResult()

        # 1) 旧 20 SK deprecated (T16 留)
        marked, errors = self.mark_legacy_20_deprecated(apply=apply)
        result.legacy_sks_marked = marked
        result.errors.extend(errors)

        # 2) 旧 15 knowledge → v1_knowledge (C13 委派 v1)
        kr, _ = self.migrate_legacy_knowledge(apply=apply, batch_id=batch_id)
        result.knowledge_candidates = kr.knowledge_candidates
        result.knowledge_applied = kr.knowledge_applied
        result.knowledge_skipped = kr.knowledge_skipped
        result.knowledge_awaiting_review = kr.knowledge_awaiting_review
        result.errors.extend(kr.errors)
        return result


__all__ = ["LegacyMigrateResult", "LegacyMigrateService"]
