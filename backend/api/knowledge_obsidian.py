"""Knowledge API — Obsidian vault bridge + watchdog.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/obsidian/open")
async def obsidian_open():
    """Return an obsidian://open URL for the knowledge vault."""
    from backend.services.obsidian_service import open_vault
    return open_vault()


@router.get("/obsidian/conflicts")
async def obsidian_conflicts():
    """List .md conflict snapshots recorded by the watchdog."""
    from backend.services.obsidian_service import get_conflicts
    return {"conflicts": get_conflicts()}


@router.post("/obsidian/watchdog/start")
async def obsidian_watchdog_start():
    """Start the knowledge watchdog."""
    from backend.services.knowledge_watcher import is_running, start_watcher
    start_watcher()
    return {"running": is_running()}


@router.post("/obsidian/watchdog/stop")
async def obsidian_watchdog_stop():
    """Stop the knowledge watchdog."""
    from backend.services.knowledge_watcher import is_running, stop_watcher
    stop_watcher()
    return {"running": is_running()}


@router.get("/obsidian/watchdog/status")
async def obsidian_watchdog_status():
    """Return the current watchdog running state."""
    from backend.services.knowledge_watcher import is_running
    return {"running": is_running()}
