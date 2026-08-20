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

from backend.api import register_routers
from backend.api.mcp_config import (
    build_mcp_server,
    is_mcp_enabled,
    mcp_tool_registry_seed,
    mount_sse_endpoint,
)
from backend.api.middleware import TraceIDMiddleware
from backend.cache import invalidate as cache_invalidate
from backend.cache import warmup
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.logging_config import setup as setup_logging
from backend.observability import log_event, set_start_time
from backend.repository.db import close_db, init_db
from backend.scheduler.jobs import set_service
from backend.scheduler.scheduler import HotspotScheduler, get_scheduler
from backend.services.collection_service import CollectionService
from backend.services.export_service import rebuild_export_cache
from backend.version import APP_VERSION

log = logging.getLogger("hotspot.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动: log → db → cache + export → scheduler; 关闭: scheduler → cache → db。

    Phase 8: scheduler 写入 app.state.scheduler（替代模块 singleton），
    保证 /api/health 跨请求读到的总是当前 lifespan 的实例。
    """
    boot_start = time.time()
    set_start_time(boot_start)
    setup_logging()
    init_db()
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

    svc = CollectionService()
    set_service(svc)
    sched = get_scheduler() or HotspotScheduler(interval=300)
    sched.attach_service(svc)
    sched.start()
    # Phase 8: scheduler 注册到 app.state（替代模块级 singleton）
    app.state.scheduler = sched

    # v1.3.0 Phase 5: 尝试从 OS keychain 自动恢复 unlock 状态
    try:
        from backend.services.secrets_service import try_auto_unlock
        try_auto_unlock()
    except Exception as e:
        log.warning(f"auto-unlock failed (ignored): {e}")

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
    yield

    try:
        sched.stop()
    except Exception as e:
        log.warning(f"scheduler.stop error: {e}")
    # Phase 8: 清理 app.state.scheduler
    try:
        app.state.scheduler = None
    except Exception:
        pass
    cache_invalidate("*")
    close_db()


app = FastAPI(
    title="热点地图 API",
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
register_exception_handlers(app)
register_routers(app)


@app.get("/")
async def root():
    return {
        "name": "热点地图 API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    from backend.config import config
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOTSPOT_HOST") or os.getenv("HOST", config.host),
        port=int(os.getenv("HOTSPOT_PORT") or os.getenv("PORT", str(config.port))),
        reload=False,
    )
