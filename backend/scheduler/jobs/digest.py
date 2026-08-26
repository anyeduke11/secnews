"""digest 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""

import asyncio

from backend.logging_config import logger

_logger = logger.bind(component="jobs")


async def sm2_daily_push_job() -> None:
    """复利驱动器②: 每天 08:00 推送待复习条目到前端通知栏 (SSE review_due)。"""
    try:
        from backend.api.events import publish_event
        from backend.services.review_service import list_due

        due = list_due(limit=20)
        if not due:
            _logger.info("sm2_daily_push: no due items today")
            return

        await publish_event("review_due", {
            "count": len(due),
            "items": [{"id": d["entity_id"], "title": d.get("title", "")} for d in due],
        })
        _logger.info(f"sm2_daily_push: {len(due)} items pushed")
    except Exception as e:
        _logger.error(f"sm2_daily_push crashed: {e}")


async def daily_snapshot_job() -> None:
    """v1.3.0 Phase 4: 日级趋势快照（每天 00:30 UTC）。"""
    try:
        from backend.services.weekly_report_service import WeeklyReportService

        svc = WeeklyReportService()
        count = await asyncio.to_thread(svc.take_daily_snapshot)
        _logger.info(f"daily_snapshot_job: {count} categories snapshotted")
    except Exception as e:
        _logger.error(f"daily_snapshot_job crashed: {e}")


async def weekly_report_job() -> None:
    """v1.3.0 Phase 4: 周报自动生成（每周一 02:00 UTC）。"""
    try:
        from backend.services.weekly_report_service import WeeklyReportService

        svc = WeeklyReportService()
        report = await asyncio.to_thread(svc.generate_report)
        _logger.info(f"weekly_report_job: generated for {report.get('week_start', '?')}")
    except Exception as e:
        _logger.error(f"weekly_report_job crashed: {e}")


async def scheduled_compile_job() -> None:
    """Phase 1d: 定时编译任务 — 检测 stale items 并创建编译任务。

    每日 02:00 (Asia/Shanghai) + 每周日 03:00 (Asia/Shanghai) 触发。
    P0 修复: detect_stale_items 带每日配额 (STALE_ITEM_DAILY_QUOTA=50,
    按 updated_at 最旧优先), create_compile_task 对 pending 队列去重,
    避免历史积压 (1980+ 任务) 一次性全量入队。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.compiler import (
            STALE_ITEM_DAILY_QUOTA,
            create_compile_task,
            detect_stale_items,
        )

        result = await asyncio.to_thread(detect_stale_items, STALE_ITEM_DAILY_QUOTA)
        stale_items = result.get("stale_items", [])
        if stale_items:
            compile_result = await asyncio.to_thread(create_compile_task, stale_items)
            skipped = compile_result.get("skipped_duplicates", 0)
            if compile_result.get("status") == "no_items":
                # 去重后无可创建条目 (全部已在 pending 队列中)
                _logger.info(
                    f"scheduled_compile_job: stale={len(stale_items)} "
                    f"created=0 skipped_duplicates={skipped}"
                )
            else:
                # 兼容两种返回形态: 单任务 {task_id} / 多任务 {tasks: [...]}
                created = compile_result.get("tasks") or [
                    {"task_id": compile_result.get("task_id")}
                ]
                _logger.info(
                    f"scheduled_compile_job: stale={len(stale_items)} "
                    f"created={len(created)} skipped_duplicates={skipped}"
                )
        else:
            _logger.info("scheduled_compile_job: no stale items")
    except Exception as e:
        _logger.error(f"scheduled_compile_job crashed: {e}")


async def consume_compile_tasks_job() -> None:
    """P0 消费策略: 自动消费者 — 批量执行 pending compile 任务 (规则式编译)。

    每日 02:30 (Asia/Shanghai) 在 scheduled_compile_job (02:00) 之后运行,
    两步:
      1. consume_compile_tasks: 按 item 配额 (CONSUME_DAILY_QUOTA=100)
         批量执行 pending compile 任务 — 分类 (auto_classifier) + 概念关联
         (concept_linker) + lifecycle 流转 (kl:link→kl:structure /
         legacy→generate) + md 回写 + done 文件 + _MAP 更新。
      2. archive_stale_compile_tasks: 归档超过 ARCHIVE_MAX_AGE_DAYS 天仍
         pending 的 compile 任务 (标记 failed + 移入 failed/), 防止队列
         在消费者失速时再次只增不减。
    失败只 log.error，不抛异常 (与既有 job 模式一致)。
    """
    try:
        from backend.services.compiler import (
            ARCHIVE_MAX_AGE_DAYS,
            CONSUME_DAILY_QUOTA,
            archive_stale_compile_tasks,
            consume_compile_tasks,
        )

        consumed = await asyncio.to_thread(
            consume_compile_tasks, CONSUME_DAILY_QUOTA
        )
        archived = await asyncio.to_thread(
            archive_stale_compile_tasks, ARCHIVE_MAX_AGE_DAYS
        )
        _logger.info(
            f"consume_compile_tasks_job: processed_tasks="
            f"{consumed.get('processed_tasks', 0)} "
            f"items={consumed.get('items_consumed', 0)} "
            f"archived={archived.get('archived', 0)}"
        )
    except Exception as e:
        _logger.error(f"consume_compile_tasks_job crashed: {e}")


async def scheduled_soul_job() -> None:
    """Phase 1f Task 6.8: 定时检查 SOUL.md 周期（>7天未更新则触发重新生成）。

    每周日 04:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from datetime import datetime, timedelta, timezone

        def _read_soul_updated_at():
            from backend.services.knowledge_sync import parse_frontmatter
            from backend.services.soul_service import SOUL_PATH

            if not SOUL_PATH.exists():
                return None
            fm = parse_frontmatter(SOUL_PATH)
            if fm is None:
                return None
            updated_at_str = fm.get("updated_at")
            if not updated_at_str:
                return None
            try:
                updated_at = datetime.fromisoformat(str(updated_at_str))
            except (ValueError, TypeError):
                return None
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            return updated_at

        updated_at = await asyncio.to_thread(_read_soul_updated_at)
        now = datetime.now(timezone.utc)

        if updated_at is None or (now - updated_at) > timedelta(days=7):
            from backend.services.soul_service import create_soul_task

            result = await asyncio.to_thread(create_soul_task)
            _logger.info(
                f"scheduled_soul_job: created soul task {result.get('task_id')}"
            )
        else:
            age_days = (now - updated_at).days
            _logger.info(
                f"scheduled_soul_job: SOUL.md fresh ({age_days} days), skipping"
            )
    except Exception as e:
        _logger.error(f"scheduled_soul_job crashed: {e}")


async def scheduled_summary_job() -> None:
    """Phase 1j Task 10.8: 每周日 06:00 (Asia/Shanghai) 生成本周知识回顾。

    链式触发于 SOUL cron (Sun 04:00) + migrate cron (Sun 05:00) 之后。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.summary_service import generate_weekly_summary

        result = await asyncio.to_thread(generate_weekly_summary, None)
        _logger.info(
            f"scheduled_summary_job: generated {result.get('year_week')} "
            f"(items={result.get('items_count')}, concepts={result.get('concepts_count')})"
        )
    except Exception as e:
        _logger.error(f"scheduled_summary_job crashed: {e}")


async def digest_generator_job() -> None:
    """v1.7 Phase 5: 每日 08:00 Shanghai 生成昨日简报."""
    try:
        from backend.services.digest_service import generate_daily_digest
        result = await asyncio.to_thread(generate_daily_digest, 3)
        _logger.info(
            f"digest_generator_job: digest_id={result.get('id')} count={result.get('count')}"
        )
    except Exception as e:
        _logger.error(f"digest_generator_job crashed: {e}")
