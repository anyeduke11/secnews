"""maintenance 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backend.scheduler.jobs as _jobs_pkg
from backend.logging_config import logger
from backend.repository.trend_repo import TrendRepository
from backend.scheduler.jobs._runtime import instrument_job, job_done_event

_logger = logger.bind(component="jobs")


async def map_rebuild_daily_job() -> None:
    """复利驱动器③: 每天 02:00 重建知识地图 (_MAP.md + graph.json)。"""
    try:
        from backend.services.map_updater import update_map

        result = await asyncio.to_thread(update_map)
        _logger.info(
            f"map_rebuild_daily: {result.get('total_items', 0)} items, "
            f"{result.get('total_concepts', 0)} concepts"
        )
    except Exception as e:
        _logger.error(f"map_rebuild_daily crashed: {e}")


def _trend_rebuild_hours(default: int = 168) -> int:
    """读 settings.trend.rebuild_hours, 缺失或脏值回落到 default。"""
    try:
        from backend.repository.db import get_connection

        row = get_connection().execute(
            "SELECT value FROM settings WHERE key = ?", ("trend.rebuild_hours",)
        ).fetchone()
        if row and row["value"] is not None:
            return max(1, int(row["value"]))
    except Exception as e:  # settings 缺表/脏值都不该让重建停摆
        _logger.debug(f"_trend_rebuild_hours: {e}")
    return default


async def trend_rebuild_job() -> None:
    """周期性重建 trend（不跑采集）

    窗口默认 168h（原硬编码 24h）。``/api/trends?hours=N`` 对超出快照窗口的桶
    一律补 0 —— 24h 快照下实测 168 点仅 19 个非零, "没有数据"被显示成
    "零资讯"; 判断层「时段吞吐」点阵正是按 168h 取数。
    """
    try:
        trend = TrendRepository()
        hours = _trend_rebuild_hours()
        # Phase 9 修复：trend.rebuild 是同步 sqlite3 操作，放 thread pool 避免阻塞 event loop
        count = await asyncio.to_thread(trend.rebuild, hours)
        _logger.debug(f"trend_rebuild_job: {count} points ({hours}h window)")  # P0-10: 例行
    except Exception as e:
        _logger.error(f"trend_rebuild_job crashed: {e}")


async def source_reputation_rebuild_job() -> None:
    """Phase 3.5: 重算 source 信誉。"""
    try:
        from backend.quality.jobs import run_source_reputation_rebuild

        # Phase 9 修复：同步 DB 操作放 thread pool
        n = await asyncio.to_thread(run_source_reputation_rebuild)
        _logger.info(f"source_reputation_rebuild_job: {n} sources updated")
    except Exception as e:
        _logger.error(f"source_reputation_rebuild_job crashed: {e}")


async def export_rebuild_job() -> None:
    """Phase 4: 重建 export 缓存 HTML（每 30min 跑一次）。"""
    try:
        from backend.services.export_service import rebuild_export_cache

        # Phase 9 修复：同步 IO 放 thread pool
        etag = await asyncio.to_thread(rebuild_export_cache)
        _logger.info(f"export_rebuild_job: rebuilt etag={etag[:8]}...")
    except Exception as e:
        _logger.error(f"export_rebuild_job crashed: {e}")


_LEGITIMATE_SKIP_REASONS = frozenset({"no_retention_days"})


def _skip_is_legitimate(reason: str) -> bool:
    """单库起步 / 台账合法声明的 skip 不告警。

    DEV-0318 事故教训: skip 完全静默让 db_diet 跨 schema 误判空转六周且
    status ok。两类情形除外, 不构成漂移:
    - ``table_not_found`` 且 warm.db 文件不存在 — v0.5 分层迁移前的老库
      形态, 表物理上确实无处可寻; 判据 = warm 库文件本身
    - ``no_retention_days`` — retention.json 台账上 ``retention_days:
      null`` 的表 (favorites/alert_rules/sync_configs 等由 backup_service
      等外部系统管理), db_diet envelope 自身也计 skipped 而非 failed;
      实弹取证 2026-10-11: 生产全台账 dry-run 有数十项此类声明, 不豁免
      即每周刷屏
    """
    if reason in _LEGITIMATE_SKIP_REASONS:
        return True
    if reason == "table_not_found":
        from backend.config import config

        warm = getattr(config, "warm_db_path", None)
        return not (warm and Path(warm).exists())
    return False


async def _fire_alert(
    *,
    metric: str,
    level: str,
    value: float,
    detail: dict,
    source: str,
    threshold: float = 0.0,
    window_minutes: int = 10080,
    cooldown: timedelta = timedelta(days=1),
) -> None:
    """清理 job 告警统一发射 (DEV-0321 自 DEV-0319 _alert_telemetry_skips 抽出)。

    observability_alerts (cooldown 同 (metric, level) 防刷屏) + SSE breach
    (前端横幅/StatusBar) + alert_dispatcher 外部投递。本函数任何失败只
    log — 告警自身绝不拖垮被告警的清理链。
    """
    from datetime import datetime

    from backend.repository.db import get_connection

    now = datetime.now(timezone.utc)
    alert_id = None
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT cooldown_until FROM observability_alerts "
            "WHERE metric = ? AND level = ? AND acked = 0 "
            "ORDER BY fired_at DESC LIMIT 1",
            (metric, level),
        ).fetchone()
        if not (existing and existing["cooldown_until"] > now.isoformat()):
            conn.execute(
                "INSERT INTO observability_alerts "
                "(level, metric, value, threshold, window_minutes, detail, "
                "fired_at, cooldown_until, acked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    level, metric, value, threshold,
                    window_minutes, json.dumps(detail, ensure_ascii=False),
                    now.isoformat(),
                    (now + cooldown).isoformat(),
                ),
            )
            alert_id = conn.execute(
                "SELECT last_insert_rowid() AS id"
            ).fetchone()["id"]
    except Exception as e:
        _logger.error(f"{metric} alert write failed: {e}")

    if alert_id is not None:
        try:
            from backend.core.events import publish_event

            await publish_event("observability.breach", {
                "alert_id": alert_id,
                "level": level,
                "metric": metric,
                "value": value,
                "threshold": threshold,
            })
        except Exception as e:
            _logger.debug(f"publish_event {metric} failed: {e}")
        try:
            from backend.services.alert_channels import AlertPayload
            from backend.services.alert_dispatcher import dispatch

            await dispatch(
                AlertPayload(
                    metric=metric,
                    level=level,
                    value=value,
                    threshold=threshold,
                    window_minutes=window_minutes,
                    detail=detail,
                    fired_at=now.isoformat(),
                    source=source,
                ),
                alert_id=alert_id,
            )
        except Exception as e:
            _logger.debug(f"dispatch {metric} failed: {e}")


async def _alert_telemetry_skips(
    skipped: list[dict], result: dict, level: str
) -> None:
    """skip 可见化 (DEV-0319): observability_alerts + SSE + dispatcher。"""
    await _fire_alert(
        metric="telemetry_window.skip",
        level=level,
        value=float(len(skipped)),
        detail={
            "job": "telemetry_window",
            "tables": [r.get("table") for r in skipped],
            "reasons": {str(r.get("table")): str(r.get("skipped_reason")) for r in skipped},
            "all_skipped": level == "critical",
        },
        source="telemetry_window",
    )


@instrument_job("telemetry_window")
async def telemetry_window_job() -> None:
    """v0.5 SPEC §18: 7 天遥测窗口 — WARM 层遥测表滚动清理。

    按 retention.json 中 ``scheduled_in == "telemetry_window"`` 的声明
    执行: quality_check_logs 归档 (>7d, 吸收原 quality_logs_cleanup_job)、
    crawler_runs / raw_items truncate。台账是唯一事实源 — 新增遥测表
    只需在 retention.json 打标签, 无需改本 job。

    每周日 05:00 Asia/Shanghai 注册 (与原 quality_logs_cleanup 同时段,
    避免与 04:00 soul / 04:30 backup / 周日链冲突)。

    DEV-0319 fail-loud: skip 不再静默 — 事故中 table_not_found 误判使
    本 job 空转六周而 status 恒 ok。非合法 skip → observability 告警
    (全表 skip=critical, 部分=warn), 但不抛 — 周日链不被打断。
    """
    from backend.services.maintenance_service import run_telemetry_window

    result = await asyncio.to_thread(run_telemetry_window, False)
    skipped = [
        r for r in result["results"]
        if r.get("skipped_reason") and not _skip_is_legitimate(r["skipped_reason"])
    ]
    if skipped:
        all_skipped = len(skipped) == len(result["results"])
        level = "critical" if all_skipped else "warn"
        _logger.error(
            f"telemetry_window_job: {level} skip detected — "
            f"{[r.get('table') for r in skipped]} "
            f"reasons={[r.get('skipped_reason') for r in skipped]}"
        )
        await _alert_telemetry_skips(skipped, result, level)
    if result.get("failed"):
        raise RuntimeError(
            f"telemetry window partial failure: "
            f"{[r.get('table') for r in result['results'] if not r.get('ok')]}"
        )
    _logger.info(
        f"telemetry_window_job: tables={result['tables']} "
        f"deleted={result['rows_deleted']} archived={result['rows_archived']}"
    )


@instrument_job("db_diet")
async def db_diet_job() -> None:
    """v0.5 M2-Task4: weekly_maintenance 链末尾调 db_diet。

    调用 ``scripts/db_diet.py`` 作为子进程 (避免把 cleanup_table 逻辑
    复制进 services 层造成双份维护), dry_run 模式默认开, 失败只 log.error。

    v0.5 M2-Task5: 包了 @instrument_job 装饰器, 完成后自动推 job_done SSE。

    DEV-0321 fail-loud: --json envelope 不再只数行数 — 逐表 skip / 表级
    失败 / envelope 不可解析 (rc 异常或 JSON 坏) 三类盲区进告警链。
    envelope 不可解析按 critical: 预览失明 = 无法证明清理台账健康, 与
    DEV-0318 静默空转同族, 不静默容忍。
    """
    repo_root = Path(__file__).resolve().parents[3]
    # DEV-0321 路径修正: v0.6 拆分自 backend/scheduler/jobs.py (parents[2])
    # 进 jobs/maintenance.py 后层级 +1, 旧常量使 script 指向 backend/scripts/
    # (不存在) → 子进程 rc=2, 此前只 log info 静默至今; envelope 告警上线
    # 当轮即捕获。
    script = repo_root / "scripts" / "db_diet.py"
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    try:
        # ASYNC221 根治: 子进程最长可阻塞 60s, to_thread 丢线程池避免卡死调度器事件循环
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(script), "--dry-run", "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
    except Exception as e:
        _logger.error(f"db_diet_job crashed: {e}")
        await _fire_alert(
            metric="db_diet.failed", level="critical", value=1.0,
            detail={"job": "db_diet", "error": f"{type(e).__name__}: {e}"},
            source="db_diet",
        )
        raise  # 让 instrument_job 捕获并记 ok=False

    _logger.info(
        f"db_diet_job (dry-run): rc={proc.returncode} "
        f"stdout_lines={len(proc.stdout.splitlines())}"
    )

    envelope: dict | None = None
    try:
        envelope = json.loads(proc.stdout)
    except Exception:
        envelope = None
    if envelope is None or not isinstance(envelope.get("data"), dict):
        # envelope 不可解析 (EXIT_FATAL 也可能带 envelope; 解析不了就如实报失明)
        await _fire_alert(
            metric="db_diet.failed", level="critical", value=1.0,
            detail={
                "job": "db_diet", "error": "envelope_unparseable",
                "rc": proc.returncode, "stderr": proc.stderr[-300:],
            },
            source="db_diet",
        )
        return

    results = envelope["data"].get("results", [])
    skipped = [
        r for r in results
        if r.get("skipped_reason") and not _skip_is_legitimate(r["skipped_reason"])
    ]
    failed = [r for r in results if not r.get("ok") and not r.get("skipped_reason")]
    if skipped:
        level = "critical" if results and len(skipped) == len(results) else "warn"
        _logger.error(
            f"db_diet_job: {level} skip detected — "
            f"{[r.get('table') for r in skipped]} "
            f"reasons={[r.get('skipped_reason') for r in skipped]}"
        )
        await _fire_alert(
            metric="db_diet.skip", level=level, value=float(len(skipped)),
            detail={
                "job": "db_diet",
                "tables": [r.get("table") for r in skipped],
                "reasons": {str(r.get("table")): str(r.get("skipped_reason")) for r in skipped},
                "all_skipped": level == "critical",
            },
            source="db_diet",
        )
    if failed or proc.returncode >= 1:
        # rc=1 EXIT_PARTIAL: 表级硬错误或 fatal; envelope.failed 为权威清单
        level = "critical" if proc.returncode >= 2 else "warn"
        _logger.error(
            f"db_diet_job: {level} partial failure rc={proc.returncode} "
            f"failed={[r.get('table') for r in failed]}"
        )
        await _fire_alert(
            metric="db_diet.failed", level=level, value=float(len(failed) or 1),
            detail={
                "job": "db_diet", "rc": proc.returncode,
                "failed_tables": [
                    {"table": r.get("table"), "reason": r.get("skipped_reason")}
                    for r in failed
                ],
                "error": envelope["data"].get("error", ""),
            },
            source="db_diet",
        )


async def interest_signals_purge() -> None:
    """R2 (DEV-0183): interest_signals 90 天清理 (Interest PRD §3 挂 maintenance)。

    行为信号属可弃数据 (显式勾选在 settings.kv), 清理失败不影响维护链 —
    不抛。但 DEV-0321 起失败必须可见: 本 job 无 instrument, purge 静默死
    等于信号表永不清理且无任何痕迹 (与 DEV-0318 空转同族), 补告警。
    """
    try:
        from backend.services.interest_engine_service import InterestEngineService

        n = await asyncio.to_thread(InterestEngineService().purge_expired)
        if n:
            _logger.info(f"interest_signals_purge: removed {n} expired signals")
    except Exception as e:
        _logger.error(f"interest_signals_purge crashed: {e}")
        await _fire_alert(
            metric="interest_signals_purge.failure", level="warn", value=1.0,
            detail={"job": "interest_signals_purge",
                    "error": f"{type(e).__name__}: {e}"},
            source="interest_signals_purge",
        )


async def weekly_maintenance_job() -> None:
    """v1.8 R3: 周日维护链 — SOUL 重生成 → 掌握度迁移 → 周回顾 → db_diet。

    原 soul_weekly (Sun 04:00) / migrate_weekly (Sun 05:00) /
    summary_weekly (Sun 06:00) 三个 cron job 合并为单 job 顺序执行,
    保持原链式语义 (每个子 job 自带异常隔离, 不会中断后续)。

    v0.5 M2-Task4: 末尾追加 db_diet_job — 按 retention.json 台账清表,
    DB 瘦身的统一入口 (替代人工跑 scripts/db_diet.py)。
    """
    await _jobs_pkg.scheduled_soul_job()
    await _jobs_pkg.scheduled_migrate_job()
    await _jobs_pkg.scheduled_summary_job()
    await db_diet_job()
    await interest_signals_purge()
    # v0.5: 周日轮转 — 强制 full backup, 重置增量链
    await _force_full_backup_rotate()


async def _force_full_backup_rotate() -> None:
    """周日 weekly 强制 full backup (重置增量链)。

    与 daily_db_backup_job (增量) 互补, 保证周一到周日: 6 增量 + 1 full。
    """
    try:
        from backend.services.backup_service import backup_incremental

        result = await asyncio.to_thread(backup_incremental, True)  # force_full=True
        if result.get("mode") == "full":
            _logger.info(
                f"weekly_full_rotate: full={result['path'].rsplit('/', 1)[-1]} "
                f"({result['size'] / 1e6:.1f} MB)"
            )
    except Exception as e:
        _logger.error(f"weekly_full_rotate crashed: {e}")


@instrument_job("daily_db_backup")  # v0.8.6 P0-5: 对齐 scheduler job id (原 "db_backup_daily" 与 id 错配)
async def daily_db_backup_job() -> None:
    """P1: 每日 04:30 (Asia/Shanghai) 数据库自动备份。

    v0.5: 改走增量备份 (backup_incremental), 链累积超 MAX_INCREMENTAL_PAGES
    或周日 weekly_maintenance 强制轮转时自动升级为 full。

    失败只 log.error (不抛), 保证 scheduler 不死循环。
    """
    try:
        from backend.services.backup_service import backup_incremental

        result = await asyncio.to_thread(backup_incremental)
        if result.get("mode") == "full":
            _logger.info(
                f"daily_db_backup_job (full): {result['path'].rsplit('/', 1)[-1]} "
                f"({result['size'] / 1e6:.1f} MB) retained={result['retained']} "
                f"removed={result['removed']}"
            )
        else:
            _logger.info(
                f"daily_db_backup_job (incremental): "
                f"{result.get('pages', 0)} pages, {result.get('size', 0)} bytes, "
                f"kept={result.get('incremental_kept', 0)} removed={result.get('incremental_removed', 0)}"
            )
    except Exception as e:
        _logger.error(f"daily_db_backup_job crashed: {e}")
        raise  # 让 instrument_job 标记 ok=False


async def backup_verify_job() -> None:
    """v0.8.2 Y-A4 (CRITICAL_REVIEW §2.4): 周一 02:00 备份完整性校验。

    校验最新 full 备份 (integrity_check + 行数单调性 + audit_log 抽样 +
    knowledge zip); 失败 → audit_log 留痕 + ok=False (job 运行记录/告警链
    可见)。永不抛除标记性失败 — 灾难检查自身不能拖垮 scheduler。
    """
    try:
        from backend.services.backup_verify_service import verify_latest_backup

        report = await asyncio.to_thread(verify_latest_backup)
        if report.get("ok"):
            _logger.info(
                f"backup_verify_job: OK — {Path(report['backup_path']).name} "
                f"({report['duration_ms']}ms)"
            )
        else:
            _logger.error(f"backup_verify_job: FAILED — {report['errors']}")
            raise RuntimeError(f"backup verify failed: {report['errors'][:2]}")
    except RuntimeError:
        raise  # 校验失败 → instrument_job 标记 ok=False
    except Exception as e:
        _logger.error(f"backup_verify_job crashed: {e}")
        raise


async def fts_rebuild_job() -> None:
    """v1.7 Phase 5: FTS5 索引重建 (5min).

    unified_fts 是迁移 033 创建的虚拟表, 此 job 触发其 REBUILD 优化查询性能.
    """
    try:
        from backend.repository.db import get_connection

        def _rebuild():
            conn = get_connection()
            conn.execute("INSERT INTO unified_fts(unified_fts) VALUES('rebuild')")

        await asyncio.to_thread(_rebuild)
    except Exception as e:
        # 表可能不存在 (旧 DB), 不报严重错
        _logger.debug(f"fts_rebuild_job: {e}")


async def wiki_items_fts_sync_job() -> None:
    """v0.6 Phase 6: wiki_items_fts 失同步自愈 (与 fts_rebuild_job 链式触发).

    正常路径: 073_v0.6_wiki_items_fts_sync.sql 的 3 触发器 (AI/AD/AU)
    自动维护 wiki_items_fts 与 knowledge_items 同步. 本 job 是兜底:
    触发器被误删 / 大批量历史数据迁移后, 比较两侧 COUNT, 失同步则
    ``INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('rebuild')``
    (FTS5 的增量 rebuild 自愈命令).
    """
    try:
        from backend.repository.db import get_connection, knowledge_items_table

        def _sync():
            conn = get_connection()
            cur = conn.execute(
                f"SELECT (SELECT COUNT(*) FROM {knowledge_items_table()}),"
                " (SELECT COUNT(*) FROM wiki_items_fts)"
            )
            src_count, fts_count = cur.fetchone()
            if src_count != fts_count:
                _logger.warning(
                    f"wiki_items_fts_sync_job: drift detected "
                    f"(knowledge_items={src_count}, wiki_items_fts={fts_count}); "
                    "rebuilding"
                )
                # FTS5 没有 DELETE FROM 语法; 用 'delete-all' 命令清空 (SQLite
                # 3.7.4+, 对 content='/external 表都支持; content='' 表更稳)。
                # 'delete-all' 会清除全部 rowid 数据但保留表结构, 之后可重新
                # INSERT 填充。
                conn.execute(
                    "INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('delete-all')"
                )
                conn.execute(
                    f"""
                    INSERT INTO wiki_items_fts(rowid, id, title, topic, tags, type)
                    SELECT rowid, id, IFNULL(title, ''), IFNULL(topic, ''),
                           IFNULL(tags, ''), IFNULL(type, '')
                    FROM {knowledge_items_table()}
                    """
                )
                conn.execute(
                    "INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('optimize')"
                )

        await asyncio.to_thread(_sync)
    except Exception as e:
        # 表可能不存在 (旧 DB, 073 未跑), 不报严重错
        _logger.debug(f"wiki_items_fts_sync_job: {e}")


async def profile_decay_job() -> None:
    """v1.7 Phase 5: 每日 03:00 Shanghai 衰减所有 profile 权重."""
    try:
        from backend.services.profile_service import decay_all
        n = await asyncio.to_thread(decay_all)
        _logger.info(f"profile_decay_job: decayed {n} entries")
    except Exception as e:
        _logger.error(f"profile_decay_job crashed: {e}")


async def retention_decay_job() -> None:
    """周 job: 扫 ``llm-wiki-2.0/retention.json``, 按 Ebbinghaus 公式更新 current_score。

    关闭策略: ``config.llm_wiki_v2=False`` 时直接跳过。
    """
    from backend.config import config

    if not config.llm_wiki_v2:
        _logger.info("retention_decay_job skipped (llm_wiki_v2 disabled)")
        return

    from backend.services.retention_engine import run_decay

    _t0 = datetime.now(tz=timezone.utc)
    retention_path = config.llm_wiki_v2_path / "retention.json"
    try:
        stats = run_decay(retention_path)
        _logger.info(
            f"retention_decay_job: {stats} (path={retention_path})"
        )
    except Exception as e:
        _logger.error(f"retention_decay_job crashed: {e}")
        try:
            job_done_event("retention_decay", "retention_decay", 0, ok=False)
        except Exception:
            pass
        return
    duration_ms = int((datetime.now(tz=timezone.utc) - _t0).total_seconds() * 1000)
    ok = stats.get("errors", 0) == 0
    try:
        job_done_event("retention_decay", "retention_decay", duration_ms, ok=ok)
    except Exception:
        pass


async def attention_aggregate_job() -> None:
    """Phase 17: 每 30 分钟聚合 attention 事件并更新 attention_score。

    调用 attention_scorer.batch_score() 批量计算。
    清理 30 天前的过期 attention_events。
    """
    try:
        from backend.services.attention_scorer import batch_score

        result = await asyncio.to_thread(batch_score)
        _logger.info(f"attention_aggregate_job: updated={result.get('updated')}, errors={result.get('errors')}")

        # 清理 30 天前的过期事件
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn = get_connection()
        conn.execute("DELETE FROM attention_events WHERE created_at < ?", (cutoff,))
        deleted = conn.total_changes
        _logger.info(f"attention_aggregate_job: cleaned {deleted} expired events")
    except Exception as e:
        _logger.error(f"attention_aggregate_job crashed: {e}")


async def planning_action_check_job() -> None:
    """Phase 13: 每 600s 生成规划动作."""
    from backend.services.planning_service import PlanningService
    try:
        service = PlanningService()
        report = await asyncio.to_thread(service.generate_actions)
        # P0-10: 全零报告 (例行空转) → DEBUG; 有动作生成保持 info
        _total = sum(v for v in report.values() if isinstance(v, int))
        _log = logger.info if _total else logger.debug
        _log(
            "planning_action_check_job: "
            + " ".join(f"{k}={v}" for k, v in report.items())
        )
    except Exception as e:
        logger.error(f"planning_action_check_job crashed: {e}")


async def scheduled_stats_job() -> None:
    """Phase 1f Task 6.9: 定时回收已发布文章统计数据。

    每日 06:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.stats_recycle_service import recycle_stats

        result = await asyncio.to_thread(recycle_stats)
        _logger.info(
            f"scheduled_stats_job: recycled={result.get('recycled')}, "
            f"skipped={result.get('skipped')}"
        )
    except Exception as e:
        _logger.error(f"scheduled_stats_job crashed: {e}")


def _reap_expired_v1_intents() -> int:
    """P0-E (FIRST_PRINCIPLES_ANALYSIS 2026-09-11): 回收超时未 commit 的 v1 evidence intent。

    INTENT_TIMEOUT_SEC=3600 → 频率匹配小时级 observability_ttl_job (不新增 job
    注册, 避免架构数字 churn)。失败由调用方 try/except 降级为 warning, 不影响
    TTL 清理主链。
    """
    from backend.services.v1_evidence_service import V1EvidenceService

    reaped = V1EvidenceService().reap_expired_intents()
    return len(reaped)


@instrument_job("observability_ttl")
async def observability_ttl_job() -> None:
    """v0.7 Batch 1+③+④: 观测表 TTL 清理 — 按迁移 080/081/082 的 retention 注释执行。

    job_runs 30d / agent_runs 30d / process_events 14d / audit_log 90d /
    api_events 7d (Batch ③) / observability_alerts 30d (Batch ④)。
    llm_usage_log 由 retention.json `scheduled_in == "telemetry_window"` 路径
    维护 (沿用现有周日凌晨清理链); 本 job 不重复清理。

    每小时一次: 6 张表均为追加写入, 缓慢累积, 高频清理能把单次 DELETE
    控制在毫秒级; 同时错峰 telemetry_window (周日凌晨) 的批量清理。
    """
    try:
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        now = datetime.now(timezone.utc)
        ttl_table = {
            "job_runs": now - timedelta(days=30),
            "agent_runs": now - timedelta(days=30),
            "process_events": now - timedelta(days=14),
            "audit_log": now - timedelta(days=90),
            "api_events": now - timedelta(days=7),
            "observability_alerts": now - timedelta(days=30),
        }
        ts_column = {
            "job_runs": "started_at",
            "agent_runs": "started_at",
            "process_events": "occurred_at",
            "audit_log": "occurred_at",
            "api_events": "occurred_at",
            "observability_alerts": "fired_at",
        }
        deleted_total = 0
        per_table = {}
        for table, cutoff in ttl_table.items():
            col = ts_column[table]
            cur = get_connection().execute(
                f"DELETE FROM {table} WHERE {col} < ?", (cutoff.isoformat(),)
            )
            n = cur.rowcount
            per_table[table] = n
            deleted_total += n
        # P0-E: 顺路回收超时 evidence intent (小时级周期与 INTENT_TIMEOUT_SEC
        # 匹配)。失败只 warning — intent 回收是尽力而为, 不拖垮 TTL 清理主链。
        try:
            reaped = await asyncio.to_thread(_reap_expired_v1_intents)
            if reaped:
                _logger.info(
                    f"observability_ttl_job: reaped {reaped} expired v1 evidence intents"
                )
        except Exception as reap_err:
            _logger.warning(
                f"observability_ttl_job: reap_expired_v1_intents failed (ignored): {reap_err}"
            )
        _logger.info(
            f"observability_ttl_job: deleted={deleted_total} per_table={per_table}"
        )
    except Exception as e:
        _logger.error(f"observability_ttl_job crashed: {e}")
        # DEV-0321: TTL 停摆 = 观测表无限累积。instrument 会记 job_runs
        # failed, 但 job.failure_rate_pct 阈值规则尚未被 evaluate 实现 —
        # 直接进告警链补这个缺口, 再照旧 raise。
        await _fire_alert(
            metric="observability_ttl.failure", level="warn", value=1.0,
            detail={"job": "observability_ttl",
                    "error": f"{type(e).__name__}: {e}"},
            source="observability_ttl",
        )
        raise  # 让 instrument_job 落 ok=False


@instrument_job("observability_aggregator")
async def observability_aggregator_job() -> None:
    """v0.7 Batch ③: api_events → api_metrics_hourly roll-up.

    每小时跑一次, 重算最近 2h 防小时边界跨越 (与 ttl 错峰运行避免同窗口).
    p50/p95 走 Python 二次扫描: GROUP BY 拉出 (hour, path_template) 各分组的
    duration_ms 列表, 取 COUNT*0.50 / COUNT*0.95 位置 (sorted 索引).

    SQL correlated subquery 在 SQLite 不能引用外层 SELECT 别名或外层 FROM 表,
    复杂度受限; 用两步走比单条 SQL 更清晰且基数 < 10k/h/path 时差异可忽略。
    主键 (hour, path_template) INSERT OR REPLACE 幂等.
    """
    try:
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=2)).isoformat()

        # 1) 拉取每个 (hour, path_template) 的 duration_ms 列表
        rows = get_connection().execute(
            "SELECT strftime('%Y-%m-%dT%H', occurred_at) AS hr, "
            "path_template, duration_ms, status "
            "FROM api_events WHERE occurred_at > ? ORDER BY hr, path_template, duration_ms",
            (cutoff,),
        ).fetchall()

        # 2) Python 聚合: p50/p95 + total/errors/max
        buckets: dict[tuple[str, str], list[int]] = {}
        errors_map: dict[tuple[str, str], int] = {}
        max_map: dict[tuple[str, str], int] = {}
        for r in rows:
            key = (r["hr"], r["path_template"])
            buckets.setdefault(key, []).append(int(r["duration_ms"]))
            if int(r["status"]) >= 500:
                errors_map[key] = errors_map.get(key, 0) + 1
            v = int(r["duration_ms"])
            if key not in max_map or v > max_map[key]:
                max_map[key] = v

        # 3) 写回 (幂等)
        n = 0
        conn = get_connection()
        for (hr, path), durs in buckets.items():
            durs_sorted = sorted(durs)
            n_count = len(durs_sorted)
            p50 = durs_sorted[max(0, int(n_count * 0.50))] if n_count else 0
            p95 = durs_sorted[max(0, min(n_count - 1, int(n_count * 0.95)))] if n_count else 0
            total = n_count
            errors = errors_map.get((hr, path), 0)
            max_ms = max_map.get((hr, path), 0)
            conn.execute(
                "INSERT OR REPLACE INTO api_metrics_hourly "
                "(hour, path_template, total, errors, p50_ms, p95_ms, max_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (hr, path, total, errors, p50, p95, max_ms),
            )
            n += 1
        _logger.info(f"observability_aggregator_job: upserted={n} buckets (since {cutoff})")
        # D3 (Batch ⑧): SSE 推送到前端, 替代 polling
        try:
            from backend.core.events import publish_event

            await publish_event(
                "observability.update",
                {"source": "aggregator", "buckets": n, "since": cutoff},
            )
        except Exception as e:
            _logger.debug(f"publish_event aggregator failed: {e}")
    except Exception as e:
        _logger.error(f"observability_aggregator_job crashed: {e}")
        raise


# v0.7 Batch ④: 阈值检查 — 拉 settings.kv 规则 → 扫 api_events 1h 摘要 →
# 评估 breach → 写 observability_alerts (cooldown 防止同阈值风暴).
@instrument_job("observability_threshold_check")
async def observability_threshold_check_job() -> None:
    """每小时跑一次, 与 aggregator 错峰 (aggregator 起点 +5min).

    cooldown 策略: 同 (metric, level) 已存在 cooldown_until > now 的活跃告警,
    跳过本轮 — 不重复刷屏.
    """
    try:
        from datetime import datetime, timezone

        from backend.observability_records import record_audit
        from backend.repository.db import get_connection
        from backend.services.observability_thresholds import (
            DEFAULT_THRESHOLDS,
            evaluate,
            load_thresholds,
        )

        now = datetime.now(timezone.utc)
        cooldown_min = int(DEFAULT_THRESHOLDS["alerts"]["cooldown_minutes"])
        dispatch_tasks: list = []  # D2 (Batch ⑧): 收集本轮 dispatch 任务

        # 1) 拉阈值规则
        try:
            thresholds = load_thresholds()
        except Exception as e:
            _logger.warning(f"observability_threshold_check_job: load_thresholds failed, using defaults: {e}")
            thresholds = DEFAULT_THRESHOLDS

        # 2) 计算最近 60min api 摘要 (复用 Batch ③ summary 逻辑的轻量版)
        cutoff = (now - timedelta(minutes=60)).isoformat()
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS errors "
            "FROM api_events WHERE occurred_at > ?",
            (cutoff,),
        ).fetchone()
        total = int(row["total"] or 0)
        errors = int(row["errors"] or 0)
        error_rate_pct = (errors / total * 100) if total > 0 else 0.0

        # p95: 拉所有 duration_ms 排序取位 (与 aggregator 同算法, 单次扫描)
        durations = [
            int(r["duration_ms"])
            for r in conn.execute(
                "SELECT duration_ms FROM api_events WHERE occurred_at > ? "
                "ORDER BY duration_ms",
                (cutoff,),
            ).fetchall()
        ]
        if durations:
            idx = max(0, min(len(durations) - 1, int(len(durations) * 0.95)))
            p95_latency_ms = durations[idx]
        else:
            p95_latency_ms = 0

        # 3) 评估
        breaches = evaluate(
            api_summary={"error_rate_pct": error_rate_pct, "p95_latency_ms": p95_latency_ms},
            thresholds=thresholds,
        )

        # 4) cooldown 去重 + 写入
        new_alerts = 0
        for breach in breaches:
            existing = conn.execute(
                "SELECT id, cooldown_until FROM observability_alerts "
                "WHERE metric = ? AND level = ? AND acked = 0 "
                "ORDER BY fired_at DESC LIMIT 1",
                (breach.metric, breach.level),
            ).fetchone()
            if existing and existing["cooldown_until"] > now.isoformat():
                continue  # cooldown 期间跳过
            conn.execute(
                "INSERT INTO observability_alerts "
                "(level, metric, value, threshold, window_minutes, detail, "
                "fired_at, cooldown_until, acked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    breach.level, breach.metric, breach.value, breach.threshold,
                    breach.window_minutes, json.dumps(breach.detail or {}),
                    now.isoformat(),
                    (now + timedelta(minutes=cooldown_min)).isoformat(),
                ),
            )
            alert_rowid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            new_alerts += 1
            # 同步入 audit_log (沿用 Batch ② audit pattern, action=threshold.breach)
            try:
                record_audit(
                    action="threshold.breach",
                    target=breach.metric,
                    status="warn",
                    detail=f"{breach.level} {breach.value} >= {breach.threshold}",
                )
            except Exception as e:
                _logger.debug(f"record_audit threshold.breach failed: {e}")

            # D2 (Batch ⑧): 投递到已配置 channels (webhook / slack / feishu / dingtalk / email)
            # 不阻塞主路径: 收集本轮所有 dispatch task, 退出循环后统一 await
            try:
                from backend.services.alert_channels import AlertPayload
                from backend.services.alert_dispatcher import dispatch

                payload = AlertPayload(
                    metric=breach.metric,
                    level=breach.level,
                    value=breach.value,
                    threshold=breach.threshold,
                    window_minutes=breach.window_minutes,
                    detail=breach.detail or {},
                    fired_at=now.isoformat(),
                    source="observability_thresholds",
                )
                dispatch_tasks.append(dispatch(payload, alert_id=alert_rowid))
            except Exception as e:
                _logger.debug(f"alert dispatch schedule failed: {e}")

            # D3 (Batch ⑧): SSE 推送 breach, 前端可立即高亮 (替代 polling 5s 延迟)
            try:
                from backend.core.events import publish_event

                await publish_event(
                    "observability.breach",
                    {
                        "alert_id": alert_rowid,
                        "level": breach.level,
                        "metric": breach.metric,
                        "value": breach.value,
                        "threshold": breach.threshold,
                    },
                )
            except Exception as e:
                _logger.debug(f"publish_event breach failed: {e}")

        # D2: 集中 await 所有本轮创建的 dispatch tasks (并发执行, 失败 swallow)
        for t in dispatch_tasks:
            try:
                await t
            except Exception as e:
                _logger.debug(f"await dispatch failed: {e}")

        _logger.info(
            f"observability_threshold_check_job: "
            f"errors={errors}/{total}={error_rate_pct:.2f}% p95={p95_latency_ms}ms "
            f"breaches={len(breaches)} new={new_alerts}"
        )
    except Exception as e:
        _logger.error(f"observability_threshold_check_job crashed: {e}")
        raise


# 注: Batch ⑤ 可在此处加 metrics aggregate helpers.
