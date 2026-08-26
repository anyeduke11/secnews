"""codegarden 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio

from backend.logging_config import logger

_logger = logger.bind(component="jobs")


async def cg_upstream_sync_job() -> None:
    """Phase 2a CodeGarden: 每日 09:00 (Asia/Shanghai) 触发 fork 类型项目的上游同步。

    遍历所有 source_type=fork 且有 upstream_url 的 cg_projects,
    为每个项目创建一个 project_sync 任务到 knowledge_tasks 队列。
    实际同步由 watchdog 或 TaskExecutor 执行, 这里只负责调度。

    失败只 log.error, 不抛异常 (与既有 job 模式一致)。
    """
    try:
        from backend.repository.codegarden_repo import CodegardenProjectRepository
        from backend.services.codegarden_project_service import CodegardenProjectService

        repo = CodegardenProjectRepository()
        svc = CodegardenProjectService()
        # 列出所有 fork 项目 (不含 archived/deprecated)
        projects, total = await asyncio.to_thread(
            repo.list, source_type="fork", limit=500
        )
        created = 0
        for p in projects:
            if not p.get("upstream_url"):
                continue
            try:
                await asyncio.to_thread(svc.request_upstream_sync, p["id"])
                created += 1
            except Exception as e:
                _logger.warning(
                    f"cg_upstream_sync_job: project {p['id']} sync request failed: {e}"
                )
        _logger.info(f"cg_upstream_sync_job: scanned {total} fork projects, created {created} sync tasks")
    except Exception as e:
        _logger.error(f"cg_upstream_sync_job crashed: {e}")


async def cg_service_scan_job() -> None:
    """Phase 2b CodeGarden: 每 5 分钟扫描本机服务 (lsof + docker + pm2) upsert 到 cg_services."""
    try:
        from backend.services.codegarden_service_service import CodegardenServiceService
        svc = CodegardenServiceService()
        result = await asyncio.to_thread(svc.scan_local_services)
        _logger.info(
            f"cg_service_scan_job: scanned={result['scanned']} "
            f"created={result['created']} updated={result['updated']}"
        )
    except Exception as e:
        _logger.error(f"cg_service_scan_job crashed: {e}")


async def cg_event_process_job() -> None:
    """Phase 2b CodeGarden: 每 60 秒处理 pending 事件.

    当前处理逻辑 (Phase 2b MVP):
    - port_conflict: 检查端口是否仍冲突, 标记 processed
    - 其他事件类型: 直接标记 processed (无 handler)
    - 异常: 标记 failed + error_message
    """
    try:
        from backend.repository.codegarden_orchestration_repo import (
            CodegardenEventRepository,
        )
        repo = CodegardenEventRepository()
        pending = await asyncio.to_thread(repo.list_pending, 50)
        if not pending:
            return

        processed = 0
        failed = 0
        for event in pending:
            try:
                # MVP: 所有事件类型直接标记成功 (实际 handler 后续 Phase 实现)
                # TODO Phase 2c+: 按 event_type 分发到具体 handler
                await asyncio.to_thread(repo.mark_processed, event["id"], success=True)
                processed += 1
            except Exception as e:
                await asyncio.to_thread(
                    repo.mark_processed, event["id"],
                    success=False, error_message=str(e),
                )
                failed += 1
                _logger.warning(
                    f"cg_event_process_job: event {event['id']} failed: {e}"
                )
        _logger.info(
            f"cg_event_process_job: pending={len(pending)} "
            f"processed={processed} failed={failed}"
        )
    except Exception as e:
        _logger.error(f"cg_event_process_job crashed: {e}")


async def cg_drift_assess_job() -> None:
    """Phase 14: 每小时评估一次 tech_stack drift."""
    try:
        from backend.services.codegarden_drift import assess_drift
        report = await asyncio.to_thread(assess_drift)
        logger.info(
            f"cg_drift_assess_job: {report['matched_count']} new assessments, "
            f"{len(report['new_techs'])} techs, "
            f"{len(report['affected_projects'])} projects"
        )
    except Exception as e:
        logger.error(f"cg_drift_assess_job crashed: {e}")
