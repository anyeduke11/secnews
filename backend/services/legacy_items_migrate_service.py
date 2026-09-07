"""v1.0 T18 旧 knowledge_items (warm) 数据迁移服务 — 薄壳委派 C13 LegacyMigrateServiceV1.

C13 重构: 旧 knowledge_items 853+ 行的迁移逻辑 (含真实 body 补全 + 分页 + 5 态机 + mapping 4 账
+ content_hash 防撞 + 后台 promote) 全部委托给 LegacyMigrateServiceV1.migrate_warm, 本文件保留:
  - 顶层 LegacyItemsMigrateService.migrate_legacy_items 接口 (向后兼容, 旧 API 仍可用)
  - 公开常量 DOMAIN_TO_KIND / LIFECYCLE_TO_STATUS (其他模块引用, 不删)
  - LegacyItemsMigrateResult dataclass (黄金案例 t18 仍用)

设计:
  - migrate_legacy_items(apply, batch_id, offset, limit) → 委派 v1.migrate_warm
  - v1 走真实 WARM_DB (get_connection ATTACH) + 5 态 (kl:publish 不再直落 published)
  - v1 走分页 (offset+limit, ASC 游标稳定) + mapping UNIQUE 防重复
  - 写 audit_log 复用 observability_records.record_audit
  - 幂等: mapping UNIQUE(legacy_source, legacy_id, legacy_revision) 防重 + content_hash 命中 v1_knowledge 跳过

历史 note (T18 原版缺陷, 全部由 v1 修复):
  - kl:publish 直落 published → 污染 C12 R16.5 reuse 池 (C13 改 legacy 5 态)
  - body 蒙混 (header-only 拼接) → v1 改 wiki md 匹配 + body≥200 字节门槛
  - 无 mapping 表 → v1 加 v1_legacy_mapping 4 账分列
  - LIMIT 4000 无游标 → v1 改 ASC + offset/limit 分页
  - content_hash 不含 legacy_id → 撞库 (v1 加 legacy_id 字段)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.logging_config import logger

# 公开常量 (T18 时代, 其他模块或黄金案例可能仍引用, 不删)
LIFECYCLE_TO_STATUS: dict[str, str] = {
    "kl:publish": "published",
    "kl:structure": "draft",
    "kl:raw": "draft",
    "kl:refine": "draft",
    "kl:link": "draft",
    # "kl:deduped" 排除 (无 v1_knowledge status 对应)
}

DOMAIN_TO_KIND: dict[str, str] = {
    "ai": "reference",
    "security": "playbook",
    "dev": "pattern",
    "startup": "reference",
    "finance": "reference",
    "": "reference",
    # 空 / unknown 走 reference fallback
}


@dataclass
class LegacyItemsMigrateResult:
    """T18 旧 knowledge_items → v1_knowledge 迁移结果 (兼容旧黄金案例 t18).

    C13 扩展 (5 账分列): 旧 3 账 (candidates/applied/skipped) + 新 2 账
    (awaiting_review / quarantined) + failed. 旧字段保留以保向后兼容.
    """

    items_candidates: int = 0
    items_applied: int = 0
    items_skipped: int = 0
    items_awaiting_review: int = 0
    items_quarantined: int = 0
    items_failed: int = 0
    errors: list[str] = field(default_factory=list)
    sample_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items_candidates": self.items_candidates,
            "items_applied": self.items_applied,
            "items_skipped": self.items_skipped,
            "items_awaiting_review": self.items_awaiting_review,
            "items_quarantined": self.items_quarantined,
            "items_failed": self.items_failed,
            "errors": self.errors,
            "sample_ids": self.sample_ids,
        }


class LegacyItemsMigrateService:
    """T18 旧 knowledge_items 数据迁移服务 — 薄壳委派 C13 LegacyMigrateServiceV1.

    向后兼容: 保留 migrate_legacy_items(apply) 接口, 旧 API 端点
    /api/dsh/legacy/items/migrate 仍可用.
    """

    def __init__(self) -> None:
        # 历史字段保留 (黄金案例 t18_golden_legacy_items_migrate.py 仍读)
        self._warm_table = "knowledge_items"

    def _audit(self, action: str, subject_id: str, details: dict[str, Any]) -> None:
        """写 audit_log (复用 observability_records.record_audit 模式, T16 修复后)."""
        try:
            from backend.observability_records import record_audit
            record_audit(actor="t18_legacy_items_migrate", action=action, target=subject_id, detail=details)
        except Exception as e:
            logger.debug(f"audit_log write failed (action={action}): {e}")

    def migrate_legacy_items(
        self, apply: bool = False, batch_id: str | None = None,
        offset: int = 0, limit: int = 500,
    ) -> LegacyItemsMigrateResult:
        """薄壳委派 LegacyMigrateServiceV1.migrate_warm (C13 5 态 + mapping 4 账 + 分页).

        Parameters
        ----------
        apply : bool
            True 落库 + 写 audit_log; False 仅计数.
        batch_id : str | None
            幂等游标, 同 batch_id 重复 apply 不重复插入.
        offset, limit : int
            warm.knowledge_items 分页参数 (ASC by ingested_at, 游标稳定).
        """
        from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
        v1 = LegacyMigrateServiceV1()
        if batch_id is None:
            batch_id = "t18-warm"
        batch = v1.migrate_warm(apply=apply, batch_id=batch_id, offset=offset, limit=limit)
        result = LegacyItemsMigrateResult(
            items_candidates=batch.candidates,
            items_applied=batch.applied,
            items_skipped=batch.skipped,
            items_awaiting_review=batch.awaiting_review,
            items_quarantined=batch.quarantined,
            items_failed=batch.failed,
            errors=list(batch.errors),
            sample_ids=batch.sample_ids,
        )
        return result


__all__ = [
    "DOMAIN_TO_KIND",
    "LIFECYCLE_TO_STATUS",
    "LegacyItemsMigrateResult",
    "LegacyItemsMigrateService",
]
