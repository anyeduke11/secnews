"""kl 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio

import backend.scheduler.jobs as _jobs_pkg
from backend.logging_config import logger

_logger = logger.bind(component="jobs")


async def kl_trigger_t1_job() -> None:
    """Phase 10: 每 60s 跑一次 T1 (kl:raw → kl:refine).

    失败只 log.error, 不抛异常 (与既有 job 模式一致).
    """
    from backend.services.triggers.t1_raw_to_refine import T1Trigger
    try:
        t1 = T1Trigger()
        report = await asyncio.to_thread(t1.run_once)
        logger.info(
            f"kl_trigger_t1_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"skipped_duplicate={report['skipped_duplicate']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t1_job crashed: {e}")


async def kl_trigger_t2_job() -> None:
    """Phase 10: 每 120s 跑一次 T2 (kl:refine → kl:link).

    失败只 log.error, 不抛异常.
    """
    from backend.services.triggers.t2_refine_to_link import T2Trigger
    try:
        t2 = T2Trigger()
        report = await asyncio.to_thread(t2.run_once)
        logger.info(
            f"kl_trigger_t2_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"low_link={report['low_link']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t2_job crashed: {e}")


async def kl_dead_letter_retry_job() -> None:
    """Phase 10: 每 10min 监控死信队列.

    当前阶段仅做阈值告警: 活跃死信 > 50 条时记 warn (供运维巡检).
    真正的重试/重跑逻辑在 Phase 12 引入 (与 T3-T5 一起设计).
    """
    from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository
    try:
        repo = KLDeadLetterRepository()
        # 同步 DB 操作放 thread pool
        counts = await asyncio.to_thread(
            lambda: {
                t: repo.list_active_count(trigger_name=t)
                for t in ("t1", "t2")
            }
        )
        total = sum(counts.values())
        if total > 50:
            logger.warning(
                f"kl_dead_letter_retry_job: {total} active dead letters "
                f"(per-trigger: {counts}) — manual review recommended"
            )
        else:
            logger.debug(
                f"kl_dead_letter_retry_job: {total} active dead letters"
            )
    except Exception as e:
        logger.error(f"kl_dead_letter_retry_job crashed: {e}")


async def kl_trigger_t3_job() -> None:
    """Phase 12: 每 600s 跑一次 T3 (kl:link → kl:structure)."""
    from backend.services.triggers.t3_link_to_structure import T3Trigger
    try:
        t3 = T3Trigger()
        report = await asyncio.to_thread(t3.run_once)
        logger.info(
            f"kl_trigger_t3_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"low_link={report['low_link']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t3_job crashed: {e}")


async def kl_trigger_t4_job() -> None:
    """Phase 12: 每 1800s 跑一次 T4 (kl:structure → kl:publish)."""
    from backend.services.triggers.t4_structure_to_publish import T4Trigger
    try:
        t4 = T4Trigger()
        report = await asyncio.to_thread(t4.run_once)
        logger.info(
            f"kl_trigger_t4_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"skipped_low_score={report['skipped_low_score']} "
            f"skipped_unstable={report['skipped_unstable']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t4_job crashed: {e}")


async def kl_pipeline_heartbeat_job() -> None:
    """每 60s 消费到期 kl_queue 任务; 每 10 拍附带 sweep 兜底。

    drain/sweep 是同步 DB+FS 操作 → asyncio.to_thread; 失败只 log.error
    不抛异常 (与既有 job 模式一致)。
    """
    from backend.kl_pipeline.runtime import get_production_pipeline

    try:
        def _drain() -> dict:
            return get_production_pipeline().drain_due(limit=50)

        result = await asyncio.to_thread(_drain)
        if result.get("done") or result.get("failed"):
            logger.info(f"kl_pipeline_heartbeat_job: drained {result}")

        _beats = _jobs_pkg._kl_heartbeat_beats
        _beats["n"] += 1
        if _beats["n"] % _KL_SWEEP_EVERY_N_BEATS == 0:
            def _sweep() -> int:
                return get_production_pipeline().sweep()

            swept = await asyncio.to_thread(_sweep)
            if swept:
                logger.info(
                    f"kl_pipeline_heartbeat_job: sweep re-enqueued {swept} items"
                )
    except Exception as e:
        logger.error(f"kl_pipeline_heartbeat_job crashed: {e}")


async def secnews_liveness_sweep_job() -> None:
    """每周日 02:00 UTC 书签存活三态批扫 (S1-3, 整合方案 §7.1)。

    对 bookmark-import 来源 item 的 url 做 HEAD(+GET 兜底) 探测, 三态写回
    frontmatter: alive = alive/dead/unknown。纯 FS+网络操作 → asyncio.to_thread。
    """
    from backend.kl_pipeline.runtime import get_production_wiki_fs
    from backend.wiki_fs.liveness import sweep_liveness

    try:
        def _sweep() -> dict:
            return sweep_liveness(get_production_wiki_fs())

        stats = await asyncio.to_thread(_sweep)
        logger.info(f"secnews_liveness_sweep_job: {stats}")
    except Exception as e:
        logger.error(f"secnews_liveness_sweep_job crashed: {e}")


_KL_SWEEP_EVERY_N_BEATS = 10  # 60s × 10 = 每 10 分钟 sweep 兜底一次


_kl_heartbeat_beats = {"n": 0}
