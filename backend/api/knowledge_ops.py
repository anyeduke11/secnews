"""Knowledge API — sync + task queue + wiki health metrics.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.exceptions import InvalidParamException
from backend.repository.knowledge_repo import knowledge_repo

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/sync")
async def trigger_sync(source: str = Query("cubox")):
    """Trigger cubox sync as an async task. Returns task_id for polling."""

    import json as _json
    import threading

    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.cubox_sync import sync_cubox_with_progress

    if source not in ("cubox", "all"):
        raise InvalidParamException("only source=cubox or source=all is supported")

    # Create task record
    task = knowledge_repo.create_task(
        task_type="cubox_sync",
        params={"source": source, "limit": 100, "phase": "pending", "current": 0, "total": 0},
    )
    task_id = task.id

    def _run_sync():
        repo = knowledge_repo
        try:
            repo.update_task_status(task_id, "processing")
            repo.update_task_params(task_id, {"source": source, "phase": "connecting", "current": 0, "total": 0})

            def on_progress(phase: str, current: int, total: int):
                try:
                    repo.update_task_params(task_id, {
                        "source": source, "phase": phase, "current": current, "total": total,
                    })
                except Exception:
                    pass

            result = sync_cubox_with_progress(limit=100, on_progress=on_progress)
            repo.update_task_status(task_id, "done", result_path=_json.dumps(result))
            repo.update_task_params(task_id, {
                "source": source, "phase": "done",
                "current": result["total"], "total": result["total"],
                "result": result,
            })
        except Exception as e:
            repo.update_task_status(task_id, "failed", error_message=str(e))

    threading.Thread(target=_run_sync, daemon=True).start()

    return {"task_id": task_id, "status": "pending"}


@router.post("/tasks")
async def create_task(data: dict):
    """Submit a task (e.g. generate_learning_plan)."""
    task_type = data.get("task_type", "unknown")
    params = data.get("params")
    task = knowledge_repo.create_task(task_type, params)
    return task.to_dict()


@router.get("/tasks")
async def list_tasks(status: str | None = Query(None)):
    """List knowledge tasks."""
    tasks = knowledge_repo.list_tasks(status=status)
    return {"tasks": [t.to_dict() for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: int):
    """Get a single knowledge task by id (for polling progress)."""
    import json
    task = knowledge_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    # params is stored as JSON string in DB, parse it for frontend
    if isinstance(task.get("params"), str):
        try:
            task["params"] = json.loads(task["params"])
        except (json.JSONDecodeError, TypeError):
            pass
    return task


@router.get("/health")
async def knowledge_health():
    """Get knowledge wiki health metrics."""
    total = knowledge_repo.count_items()
    compiled_count = knowledge_repo.count_items(compiled=True)
    coverage = knowledge_repo.domain_coverage()
    gap_analysis = [
        {
            "domain": c["domain"],
            "coverage": round(c["coverage"], 2),
            "suggestion": (
                "覆盖良好" if c["coverage"] >= 0.5
                else f"建议补充 {c['domain']} 相关条目"
            ),
        }
        for c in coverage
    ]
    return {
        "total_items": total,
        "total_concepts": len(knowledge_repo.list_concepts()),
        "compiled_count": compiled_count,
        "compiled_ratio": (compiled_count / total) if total > 0 else 0,
        "orphan_items": knowledge_repo.count_orphan_items(),
        "stale_concepts": knowledge_repo.count_stale_concepts(),
        "gap_analysis": gap_analysis,
    }
