"""v1.0 T13 SK-06 knowledge_review_due 每日 job (04:00 Asia/Shanghai).

扫 review_at <= now + status='published' 的 knowledge → 挂 case blocker
(v1_cases.tags_json 加 'knowledge_review_due:{knowledge_id}'). 不改 knowledge.status
(contracts §9.2 硬约束: 过期不改 status, 改 related case blocker).

注册入口: scheduler.py:_register_knowledge_jobs (T13 新增)
worker_pump 风格 job 55 (job 53=worker_queue_pump, job 54=legacy_hold_reap)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.knowledge_service import KnowledgeService

_logger = logger.bind(component="knowledge_review_job")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def knowledge_review_due_job() -> dict:
    """T13 SK-06 每日 04:00 扫 review_at 到期.

    Returns
    -------
    dict: {scanned, blocked_count, errors}
    """
    try:
        svc = KnowledgeService()
        now = _now_iso()
        due_items = svc.scan_review_due(now)
        if not due_items:
            return {"scanned": 0, "blocked_count": 0, "errors": []}
        blocked_count = 0
        errors: list[str] = []
        for k in due_items:
            # 找关联 case (经 v1_knowledge_refs → v1_actions → case_id)
            try:
                conn = get_connection()
                case_rows = conn.execute(
                    "SELECT DISTINCT a.case_id FROM v1_knowledge_refs kr "
                    "JOIN v1_actions a ON kr.source_type = 'action' AND a.id = kr.source_id "
                    "WHERE kr.knowledge_id = ?",
                    (k["id"],),
                ).fetchall()
                case_rows += conn.execute(
                    "SELECT DISTINCT j.case_id FROM v1_knowledge_refs kr "
                    "JOIN v1_judgments j ON kr.source_type = 'judgment' AND j.id = kr.source_id "
                    "WHERE kr.knowledge_id = ?",
                    (k["id"],),
                ).fetchall()
                for r in case_rows:
                    if svc.mark_case_blocker(r[0], k["id"]):
                        blocked_count += 1
            except sqlite3.Error as e:
                errors.append(f"{k['id']}: {e}")
        return {"scanned": len(due_items), "blocked_count": blocked_count, "errors": errors}
    except Exception as e:
        _logger.error(f"knowledge_review_due_job failed: {e}")
        return {"scanned": 0, "blocked_count": 0, "errors": [str(e)]}


__all__ = ["knowledge_review_due_job"]
