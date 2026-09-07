"""v1.0 C13 legacy_promote_due + legacy_migrate_resume job (job 56 + 57).

C13 plan §3.2: 后台 promote 扫 v1_legacy_mapping.status='awaiting_review' +
v1_knowledge.status='legacy' + body≥200B + wiki_path 命中 → 落 published
(走 LegacyMigrateServiceV1._promote_legacy CAS + v1_legacy_promote_log 持久).

migrate_resume: 扫 v1_legacy_mapping.status='awaiting_review' (apply 中断 resume)
+ 走 promote 路径; 同步清 v1_legacy_mapping.status='failed' 重试 1 次.

注册入口: scheduler.py:_register_knowledge_jobs (T13 已建, C13 扩展)
worker_pump 风格 job 56/57 (job 53=worker_queue_pump, 54=legacy_hold_reap, 55=knowledge_review_due)
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1

_logger = logger.bind(component="legacy_promote_job")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def legacy_promote_due_job() -> dict:
    """C13 job 56: legacy 5 态 → published promote (每小时扫一次).

    规则 (同 LegacyMigrateServiceV1.run_legacy_promote):
      - v1_legacy_mapping.status='awaiting_review'
      - v1_knowledge.status='legacy'
      - body≥200B (wiki 命中)
      - 落 published + v1_legacy_promote_log UNIQUE 防重

    Returns
    -------
    dict: {candidates, promoted, kept_legacy, errors}
    """
    try:
        svc = LegacyMigrateServiceV1()
        batch = svc.run_legacy_promote()
        result = {
            "candidates": batch.candidates,
            "promoted": batch.promoted,
            "kept_legacy": batch.kept_legacy,
            "errors": list(batch.errors),
        }
        if batch.promoted > 0:
            _logger.info(f"legacy_promote_due_job promoted {batch.promoted}/{batch.candidates}")
        return result
    except Exception as e:
        _logger.error(f"legacy_promote_due_job failed: {e}")
        return {"candidates": 0, "promoted": 0, "kept_legacy": 0, "errors": [str(e)]}


def legacy_migrate_resume_job() -> dict:
    """C13 job 57: 中断 resume (扫 failed 状态 + 重试 1 次; 默认 dry-run).

    规则:
      - v1_legacy_mapping.status='failed' 列出 → 重试 1 次 (apply=False 仅报错诊断)
      - v1_legacy_mapping.status='awaiting_review' (apply 中断) → 走 promote job
      - 默认不动 v1_knowledge, 留 promote job 处理
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT legacy_source, legacy_id, legacy_revision, error, batch_id "
            "FROM v1_legacy_mapping WHERE status = 'failed' ORDER BY migrated_at DESC LIMIT 100",
        ).fetchall()
        failed = [dict(legacy_source=r[0], legacy_id=r[1], legacy_revision=r[2],
                       error=r[3], batch_id=r[4]) for r in rows]
        # 同步触发 promote (a 中断的 await 会由 promote job 收口)
        svc = LegacyMigrateServiceV1()
        promote_batch = svc.run_legacy_promote()
        return {
            "failed_recent": failed,
            "failed_count": len(failed),
            "promoted_this_run": promote_batch.promoted,
            "errors": list(promote_batch.errors),
        }
    except Exception as e:
        _logger.error(f"legacy_migrate_resume_job failed: {e}")
        return {"failed_recent": [], "failed_count": 0, "promoted_this_run": 0, "errors": [str(e)]}


__all__ = ["legacy_migrate_resume_job", "legacy_promote_due_job"]
