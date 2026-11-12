"""Maintenance API 子模块 — 保留策略 (拆自 maintenance.py)。

端点: /quality-log-tiers · /cleanup-quality-logs

v0.8.8 P2.5 C2.1: 备份链退役, 原 /backup-verify · /backups · /backups/compact
三端点随 backup_service / backup_verify_service 一并删除。备份语义由
「可拷贝」改为「可重建」—— 冷层 (llm-wiki-2.0/feed/) → 热层重建走
``scripts/rebuild_hot_index.py``。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/quality-log-tiers")
async def maintenance_quality_log_tiers(
    days: int | None = Query(None, ge=1, le=120,
                            description="档宽 (天); 缺省 = 台账 retention/tiers"),
    tiers: int = Query(3, ge=1, le=6, description="展示档数 (默认 3 档)"),
):
    """DEV-0322: 质量日志分档统计 (近 N 档行数/估算体积 + 超窗口档)。

    超窗口档 (in_window=false) 的 rows = 此刻执行清理将真实归档的量 —
    展示与 archive_quality_logs 同一 isoformat cutoff 口径, 不会两套数字。
    """
    from backend.services.maintenance_service import quality_log_tiers
    # 全表 SUM(LENGTH) + 分段 COUNT, 26 万行稳态 ~百 ms 级 → to_thread
    return await asyncio.to_thread(quality_log_tiers, days, tiers)


@router.post("/cleanup-quality-logs")
async def maintenance_cleanup_quality_logs(
    days: int | None = Query(None, ge=1, le=365,
                            description="保留天数; 缺省 = 台账 retention (DEV-0322 三档 = 档宽×3)"),
    dry_run: bool = Query(True, description="True=仅预览, False=实际删除"),
):
    """Purge old quality_check_logs entries (main DB bloat culprit ~3M rows)."""
    from backend.services.maintenance_service import cleanup_quality_logs
    # DEV-0318: 53 万行归档 DELETE 是长事务, 必须移出事件线程
    if days is None:
        from backend.services.maintenance_service import _qcl_retention_days
        days = _qcl_retention_days()
    return await asyncio.to_thread(cleanup_quality_logs, days=days, dry_run=dry_run)


__all__ = ["router"]