"""FastAPI app — Phase 4: lifespan + middleware + router 注册 + uvicorn 入口。

业务逻辑全部下沉到 :mod:`backend.api` 和 :mod:`backend.services`。

Phase 5: 启动耗时打 ``startup_complete`` 事件。
Phase 7: 集成 MCP server (Option A) — 启动时 seeding 9 tool 元数据,
         挂载 /mcp/sse SSE 端点, stdio 由 backend.mcp_stdio_main 启动。
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.api import register_routers
from backend.api.mcp_config import (
    build_mcp_server,
    is_mcp_enabled,
    mcp_tool_registry_seed,
    mount_sse_endpoint,
)
from backend.api.middleware import TokenAuthMiddleware, TraceIDMiddleware
from backend.cache import invalidate as cache_invalidate
from backend.cache import warmup
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.logging_config import logger
from backend.logging_config import setup as setup_logging
from backend.observability import log_event, set_start_time
from backend.repository.db import close_db, init_db
from backend.scheduler.jobs import set_service
from backend.scheduler.scheduler import HotspotScheduler, get_scheduler
from backend.services.collection_service import CollectionService
from backend.services.export_service import rebuild_export_cache
from backend.version import APP_VERSION

log = logging.getLogger("hotspot.main")


def _apply_persisted_refresh_interval() -> None:
    """cadence 修正批: 启动时回读 settings 表持久化的采集间隔。

    POST /api/settings/refresh-interval 此前只改内存 config, 重启即回默认;
    现在该 API 同步写 ``collection.refresh_interval_seconds``, 此处在
    scheduler 构造前应用, 让前端改的间隔重启后仍生效。env 优先级不变
    (pydantic Settings 先读 env, 此处只是把持久值覆盖到同一起点)。
    读取失败静默走 config 默认 (settings 表缺失/损坏不阻断启动)。
    """
    try:
        from backend.repository.settings_repo import SettingsRepository

        persisted = SettingsRepository().get("collection.refresh_interval_seconds")
        if isinstance(persisted, int) and 60 <= persisted <= 86400:
            from backend.config import config

            config.collect_interval_seconds = persisted
            log.info(
                "refresh interval restored from settings: %ss", persisted
            )
    except Exception as e:  # pragma: no cover
        log.warning(f"persisted refresh interval restore failed (ignored): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动: log → db → cache + export → scheduler; 关闭: scheduler → cache → db。

    Phase 8: scheduler 写入 app.state.scheduler（替代模块 singleton），
    保证 /api/health 跨请求读到的总是当前 lifespan 的实例。
    T17 E2E-10: 启动时校验 in-flight skill_runs.version 与 BUILTIN 当前 version,
    不一致仅 warning (T19 全量收口前容忍 in-flight 旧版本).
    """
    boot_start = time.time()
    set_start_time(boot_start)
    setup_logging()
    init_db()
    _check_skill_run_version_compatibility()  # T19 E2E-10 启停校验 (strict 模式)
    warmup()
    try:
        rebuild_export_cache()
    except Exception as e:  # pragma: no cover
        log.warning(f"export prebuild failed: {e}")

    # v1.7 Phase 7: MCP server — HTTP/SSE transport 挂载 + tool registry seeding
    # 幂等: mcp_tool_registry_seed 用 PRIMARY KEY name 保证重启不重复插入
    # 失败只告警不阻断启动 (MCP 是增强功能, 不因挂载失败拖垮整个服务)
    try:
        if is_mcp_enabled():
            mcp_tool_registry_seed()
            mcp = build_mcp_server(app)
            mount_sse_endpoint(app, mcp)
            log.info("MCP server enabled: SSE endpoint /mcp/sse + tool registry seeded")
        else:
            log.info("MCP server disabled (feature.mcp_server=False), SSE endpoint not mounted")
    except Exception as e:
        log.warning(f"MCP setup failed (ignored): {e}")
    # v0.8.2 X-B3: mcp 双开关契约显式化 — stdlib log 全仓不可见, 两态诊断走 loguru
    try:
        from backend.extensions import is_extension_enabled
        logger.info(
            "MCP switches: server={} (config.feature_mcp) | debug routes /api/mcp/*={} (gate mcp)",
            "on" if is_mcp_enabled() else "off",
            "on" if is_extension_enabled("mcp") else "off",
        )
    except Exception as e:  # pragma: no cover
        log.warning(f"MCP switch diagnostic failed (ignored): {e}")

    svc = CollectionService()
    set_service(svc)
    # cadence 修正批: interval=300 硬编码曾压过 env/config 链 (调 HOTSPOT_
    # COLLECT_INTERVAL_SECONDS 无效的根因); 现回落构造器默认 → config →
    # settings 表持久值 (API 改间隔重启后不丢)。
    _apply_persisted_refresh_interval()
    sched = get_scheduler() or HotspotScheduler()
    sched.attach_service(svc)
    # v085-review F5 (P0-3): dev 与生产后端并行时, dev 实例不再起全套
    # 采集/触发 job (实测双实例叠加会让采集背靠背连轴转 + 事件循环冻结)。
    # env 显式关闭, API 正常可用; 不设或非 "1" 时行为不变。
    if os.getenv("HOTSPOT_DISABLE_SCHEDULER") == "1":
        log.warning("HOTSPOT_DISABLE_SCHEDULER=1 — scheduler NOT started (dev 并行模式)")
        app.state.scheduler = None
    else:
        sched.start()
        # Phase 8: scheduler 注册到 app.state（替代模块级 singleton）
        app.state.scheduler = sched

    # C11 R18: outbox dispatcher — 业务 outbox 行 → SSE 广播
    try:
        from backend.services.outbox_dispatcher import get_dispatcher
        await get_dispatcher().start()
    except Exception as e:
        log.warning(f"outbox dispatcher start failed (ignored): {e}")

    # v1.3.0 Phase 5: 尝试从 OS keychain 自动恢复 unlock 状态
    try:
        from backend.services.secrets_service import try_auto_unlock
        try_auto_unlock()
    except Exception as e:
        log.warning(f"auto-unlock failed (ignored): {e}")

    # v0.6.3: dsh 内置受管服务 — autostart=true 且已配置启动命令时自动拉起。
    # gate 关闭 (is_extension_enabled("dsh")=false) 时跳过; 失败不阻塞启动
    # (认知层缺失时业务走 LLM fallback)。
    try:
        from backend.extensions import is_extension_enabled
        if is_extension_enabled("dsh"):
            from backend.services.dsh.supervisor import autostart_if_configured
            autostart_if_configured()
    except Exception as e:
        log.warning(f"dsh autostart hook failed (ignored): {e}")

    # P1: 默认启用 knowledge watchdog — 文件↔DB 双向同步。
    # 此前仅手动 POST /api/obsidian/watchdog/start 才启动, 默认部署下
    # knowledge/*.md 变更不会自动回灌 SQLite。config.knowledge_watchdog_
    # enabled=False 可整体关闭 (start_watcher 幂等: 已运行返回 False)。
    try:
        if config.knowledge_watchdog_enabled:
            from backend.services.knowledge_watcher import start_watcher
            started = start_watcher()
            log.info(f"knowledge watchdog: started={started}")
        else:
            log.info("knowledge watchdog disabled by config.knowledge_watchdog_enabled")
    except Exception as e:
        log.warning(f"knowledge watchdog start failed (ignored): {e}")

    # v1.9 Phase 9: 启动后自动追抓「本周一 00:00 (Asia/Shanghai) → 现在」
    # 抓取流程已标准化 (per-source checkpoint + 结构化日志 + 数据完整性验证)
    # 用 background task 不阻塞 startup, 防 watchdog 5 分钟内重复 enqueue
    # v1.8: config.catchup_on_startup=False 可整体关闭 (测试环境必须关闭)
    try:
        from backend.services.catchup_service import (
            enqueue_catchup,
            mark_auto_enqueued,
            should_enqueue_auto,
        )
        from backend.utils.business_days import current_week_start
        if not config.catchup_on_startup:
            log.info("startup auto-catchup disabled by config.catchup_on_startup")
        elif should_enqueue_auto():
            since_iso = current_week_start().astimezone(timezone.utc).isoformat()
            run_id = await enqueue_catchup(
                mode="auto",
                since=since_iso,
                until=None,
                categories=None,
                max_per_source=30,
            )
            mark_auto_enqueued()
            log.info(
                f"startup auto-catchup enqueued: run_id={run_id} since={since_iso}"
            )
        else:
            log.info("startup auto-catchup skipped (within 5min debounce)")
    except Exception as e:
        log.warning(f"startup auto-catchup failed (ignored): {e}")

    startup_duration_ms = round((time.time() - boot_start) * 1000, 2)
    log_event(
        "startup_complete",
        startup_duration_ms=startup_duration_ms,
        db_wal=True,
        collectors_ready=True,
    )
    log.info(f"startup complete in {startup_duration_ms}ms")

    # MP-1 DEV-0217: 图谱点火 — 启动期同步 attack 静态数据 + MITRE STIX bundle
    # 1) attack_techniques + attack_cwe_map (data/stix/ 静态子集, ~200/700 行)
    # 2) security_entities + security_edges (完整 STIX bundle, ~1000+/5000+ 行)
    # 两步均幂等 (attack_loader 用 COUNT==0, MitreAttackClient.upsert 用 ON CONFLICT),
    # 失败仅 warning 不阻断 startup (graph 端点允许空数据回退)。
    try:
        from backend.services.attack_loader import load_attack_data as _load_attack
        _loaded = _load_attack()
        log.info(
            f"attack_loader: techniques={_loaded.get('techniques', 0)} "
            f"cwe_mappings={_loaded.get('cwe_mappings', 0)}"
        )
    except Exception as e:
        log.warning(f"attack_loader startup hook failed (ignored): {e}")

    try:
        from backend.security.mitre_attack import MitreAttackClient as _MitreClient
        _sync_result = _MitreClient().sync_to_db(force=True)
        log.info(
            f"mitre_attack sync: entities={_sync_result.get('entities', 0)} "
            f"edges={_sync_result.get('edges', 0)} from_cache={_sync_result.get('from_cache', False)}"
        )
    except Exception as e:
        log.warning(f"mitre_attack sync startup hook failed (ignored): {e}")

    yield

    # v0.8.1 Day 0 (PRD F5/D-b): drain 必须在 sched.stop() 之前 —
    # AsyncIOScheduler.shutdown() 会 cancel pending futures (协作式打断
    # 在跑 job), 先等自然收尾 (有界, HOTSPOT_GRACEFUL_TIMEOUT 默认 30s)。
    # 统计日志由 drain_in_flight 内部走 loguru 输出。
    try:
        from backend.utils.shutdown import drain_in_flight
        await drain_in_flight(sched)
    except Exception as e:
        log.warning(f"graceful drain error (ignored): {e}")
    # gateway 方案 §3.1: crawl4ai/Playwright 单例优雅停机 — 进程 shutdown
    # 时关闭常驻 Chromium, 否则浏览器变僵尸进程 (第 1 步实施缺口)。
    # crawl4ai 未安装时 close_client 内部 no-op, 不影响无依赖环境。
    try:
        from backend.utils.crawl4ai_client import close_client
        await close_client()
    except Exception as e:
        log.warning(f"crawl4ai close_client error: {e}")
    try:
        # F5: dev 并行模式 (scheduler 未启动) 时为 None, 跳过 stop
        if app.state.scheduler is not None:
            app.state.scheduler.stop(wait=False)
    except Exception as e:
        log.warning(f"scheduler.stop error: {e}")
    # v0.8.1 Day 0: dsh 受管子进程随主进程退出, 防孤儿 (autostart 拉起的才管)。
    try:
        from backend.services.dsh.supervisor import stop_dsh
        stop_dsh()
    except Exception as e:
        log.warning(f"dsh stop error (ignored): {e}")
    # C11 R18: outbox dispatcher 停机
    try:
        from backend.services.outbox_dispatcher import get_dispatcher
        await get_dispatcher().stop()
    except Exception as e:
        log.warning(f"outbox dispatcher stop error: {e}")
    # Phase 8: 清理 app.state.scheduler
    try:
        app.state.scheduler = None
    except Exception:
        pass
    # v0.8.1 Day 0: close_db 前显式折叠 WAL (PRD 验收项; busy 不致命, 下次
    # 打开时 SQLite 自动恢复)。
    try:
        from backend.utils.shutdown import wal_checkpoint
        wal_checkpoint()
    except Exception as e:
        log.warning(f"wal checkpoint error (ignored): {e}")
    cache_invalidate("*")
    close_db()


app = FastAPI(
    title="热点地图 - SecNews API",
    version=APP_VERSION,
    description="多域热点聚合仪表盘 — Phase 4 API 层",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8898",
        "http://127.0.0.1:8898",
        "http://localhost:8899",
        "http://127.0.0.1:8899",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
# v0.8.2 X-C2 (CRITICAL_REVIEW §3.2): 全局 gzip 压缩 — >1000B 响应体才压,
# 小 JSON 不压缩避免 CPU 浪费; SettingsHub 17 cat / quality rules 等大 payload 显著省带宽
app.add_middleware(GZipMiddleware, minimum_size=1000)
# P0-A 配套 (FIRST_PRINCIPLES_ANALYSIS §0.1): 最小 token 鉴权 — env
# HOTSPOT_API_TOKEN 设置时对 /api/* 校验 X-Hotspot-Token, 未设置时完全关闭。
app.add_middleware(TokenAuthMiddleware, exempt_paths=["/api/health"])
register_exception_handlers(app)
register_routers(app)


@app.get("/")
async def root():
    return {
        "name": "热点地图 - SecNews API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    from backend.config import config, resolve_bind_host
    host = os.getenv("HOTSPOT_HOST") or os.getenv("HOST", config.host)
    uvicorn.run(
        "backend.main:app",
        # P0-B: 复用 run.py 的回环守卫 (backend.config.resolve_bind_host),
        # 修复此前 __main__ 分支绕过守卫直接绑 config.host 的问题。
        host=resolve_bind_host(host),
        port=int(os.getenv("HOTSPOT_PORT") or os.getenv("PORT", str(config.port))),
        reload=False,
    )


def _check_skill_run_version_compatibility() -> None:
    """T19 全量收口: E2E-10 启停校验 — 严格模式 (默认) + warning 模式 (env opt-in).

    启动时扫 in-flight skill_runs (status='running'), 取每个 skill_id 的最新 version,
    与 BUILTIN 当前 SkillDef.version 对比.

    严格模式 (T19 默认): 不一致 → RuntimeError 阻断启动, 强制 operator 先 drain in-flight
    再部署新版本 (避免半新半旧 skill_run 在生产并发跑两个版本的 prompt/契约).
    Warning 模式 (T17 旧行为, 通过 env HOTSPOT_SKILL_RUN_VERSION_CHECK=warn 开启):
    不一致 → 仅 log.warning 不阻断 (用于 in-flight 跨版本过渡期/灰度).

    选择标准:
      - 默认严格 = 1.0 上线后任何版本切换必须先 drain; 这是 v1 之后跨大版本的安全门.
      - warning mode 留给 (1) 灰度期 (2) 测试 (3) dev (4) 用户明令保留期.
    """
    from backend.repository.db import get_connection
    from backend.services.skill_registry.builtin import BUILTIN
    mode = os.getenv("HOTSPOT_SKILL_RUN_VERSION_CHECK", "strict").lower()
    if mode not in ("strict", "warn", "off"):
        log.warning(f"unknown HOTSPOT_SKILL_RUN_VERSION_CHECK={mode}, falling back to strict")
        mode = "strict"
    if mode == "off":
        log.debug("skill_run version check disabled (HOTSPOT_SKILL_RUN_VERSION_CHECK=off)")
        return
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT skill_id, MAX(version) AS last_version "
            "FROM skill_runs WHERE status = 'running' GROUP BY skill_id"
        ).fetchall()
    except Exception as e:
        log.debug(f"skill_run version check skipped: {e}")
        return
    mismatches: list[tuple[str, str | None, str | None]] = []
    for skill_id, last_version in rows:
        current = BUILTIN.get(skill_id)
        if current is None:
            continue  # 旧 SK 已不在 BUILTIN (可能 unregister)
        if last_version and last_version != current.version:
            mismatches.append((skill_id, last_version, current.version))
    if not mismatches:
        return
    detail = "; ".join(f"skill={s} in_flight={inf} current={cur}" for s, inf, cur in mismatches)
    if mode == "strict":
        raise RuntimeError(
            f"E2E-10 in-flight skill_run version mismatch (strict mode): {detail}. "
            f"Drain in-flight runs first, or set HOTSPOT_SKILL_RUN_VERSION_CHECK=warn to skip."
        )
    log.warning(f"E2E-10 in-flight skill_run version mismatch (warn mode): {detail}")
