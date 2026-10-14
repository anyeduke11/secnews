"""Maintenance API 子模块 — 保留策略 / 备份链 (拆自 maintenance.py)。

端点: /backup-verify · /quality-log-tiers · /cleanup-quality-logs · /backups · /backups/compact
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.post("/backup-verify")
async def maintenance_backup_verify():
    """v0.8.2 Y-A4 (§2.4): 最新 full 备份完整性校验 (integrity + 行数 + 抽样)。

    周一 02:00 由 ``backup_verify_job`` 自动触发; 本端点供运维按需手跑。
    永不抛 — 失败以 ``ok=False + errors`` 返回 (audit_log 已留痕)。
    """
    from backend.services.backup_verify_service import verify_latest_backup

    return await asyncio.to_thread(verify_latest_backup)


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


@router.get("/backups")
async def maintenance_backups_inventory():
    """DEV-0323: 备份现状盘点 (1 full + ≤3 增量不变量 / 链档 / zip / 占用)。

    纯 stat + 少量 header 读, 毫秒级同步即可。
    """
    from backend.services.backup_service import backup_inventory
    return backup_inventory()


@router.post("/backups/compact")
async def maintenance_backups_compact(
    keep_incrementals: int = Query(3, ge=1, le=6, description="增量链保留档数 (默认 3)"),
):
    """DEV-0323: 手动触发滚动保留整理 (roll-forward 合成 + 旧 full/残档/超额 zip 清理)。

    apply 链到大库 full 副本 + 新 full 落盘是秒~分级长 IO, to_thread。
    """
    from backend.services.backup_service import compact_backup_chain
    return await asyncio.to_thread(compact_backup_chain, keep_incrementals)


__all__ = ["router"]