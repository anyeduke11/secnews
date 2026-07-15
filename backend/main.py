"""FastAPI app — Phase 4: lifespan + middleware + router 注册 + uvicorn 入口。

业务逻辑全部下沉到 :mod:`backend.api` 和 :mod:`backend.services`。

Phase 5: 启动耗时打 ``startup_complete`` 事件。
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.cache import invalidate as cache_invalidate, warmup
from backend.exceptions import register_exception_handlers
from backend.logging_config import setup as setup_logging
from backend.observability import log_event, set_start_time
from backend.repository.db import close_db, init_db
from backend.scheduler.scheduler import HotspotScheduler, get_scheduler
from backend.scheduler.jobs import set_service
from backend.services.collection_service import CollectionService
from backend.services.export_service import rebuild_export_cache

log = logging.getLogger("hotspot.main")
APP_VERSION = "1.2.0"


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

    # v1.4 Phase 1c Group N: 启动 knowledge watchdog（失败不阻断主服务）
    try:
        from backend.config import config
        if config.knowledge_watchdog_enabled:
            from backend.services.knowledge_watcher import start_watcher
            if start_watcher():
                log.info("knowledge watchdog auto-started")
            else:
                log.warning("knowledge watchdog auto-start returned False (already running?)")
    except Exception as e:
        log.warning(f"knowledge watchdog auto-start failed (ignored): {e}")

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
    # v1.4 Phase 1c Group N: 停止 knowledge watchdog
    try:
        from backend.services.knowledge_watcher import stop_watcher
        stop_watcher()
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
