"""Compiler service — create compile tasks for Agent to execute.

Design: backend only creates task records + pending task files.
The actual LLM compilation is done by Agent via knowledge-base-manager skill.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.compiler")

PENDING_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "pending"
)

ITEMS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "items"
)


def detect_stale_items() -> dict:
    """Detect items that need recompilation.

    Conditions:
      1. compiled=false → reason="compiled=false"
      2. .md file mtime > SQLite updated_at → reason="file_modified"

    Returns: {"stale_items": [id1, id2], "reasons": {id1: "compiled=false", ...}}
    """
    stale_items: list[str] = []
    reasons: dict[str, str] = {}

    items = knowledge_repo.list_items(limit=10000)
    for item in items:
        # Condition 1: compiled=false
        if not item.compiled:
            stale_items.append(item.id)
            reasons[item.id] = "compiled=false"
            continue

        # Condition 2: file mtime > SQLite updated_at
        md_path = ITEMS_DIR / f"{item.id}.md"
        if not md_path.exists():
            continue
        try:
            file_mtime = os.path.getmtime(md_path)
            file_mtime_dt = datetime.fromtimestamp(file_mtime, tz=timezone.utc)
        except OSError:
            continue

        updated_at_str = item.updated_at
        if not updated_at_str:
            continue
        # Handle ISO 8601 with Z suffix
        if updated_at_str.endswith("Z"):
            updated_at_str = updated_at_str[:-1] + "+00:00"
        try:
            updated_at_dt = datetime.fromisoformat(updated_at_str)
        except ValueError:
            continue
        if updated_at_dt.tzinfo is None:
            updated_at_dt = updated_at_dt.replace(tzinfo=timezone.utc)

        if file_mtime_dt > updated_at_dt:
            stale_items.append(item.id)
            reasons[item.id] = "file_modified"

    return {"stale_items": stale_items, "reasons": reasons}


def create_compile_task(item_ids: Optional[list[str]] = None) -> dict:
    """Create a compile task.

    Args:
        item_ids: specific item IDs to compile. If None, detect stale items
                  (compiled=false or file modified). If empty list, return no_items.

    Returns:
        ≤10 items: {task_id, status, items_to_compile} (backward compatible)
        >10 items: {tasks: [{task_id, items_count}], total_tasks, items_to_compile}
    """
    if item_ids is None:
        # Detect stale items (compiled=false OR file modified)
        stale = detect_stale_items()
        item_ids = stale["stale_items"]
    elif not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0}

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0}

    # Batch processing: 10 items per task
    BATCH_SIZE = 10
    if len(item_ids) <= BATCH_SIZE:
        task_id = _create_single_compile_task(item_ids)
        _trigger_map_update()
        return {
            "task_id": task_id,
            "status": "pending",
            "items_to_compile": len(item_ids),
        }

    # Multiple batches
    batches = [
        item_ids[i:i + BATCH_SIZE]
        for i in range(0, len(item_ids), BATCH_SIZE)
    ]
    tasks_created: list[dict] = []
    for batch in batches:
        task_id = _create_single_compile_task(batch)
        tasks_created.append({"task_id": task_id, "items_count": len(batch)})

    _trigger_map_update()
    return {
        "tasks": tasks_created,
        "total_tasks": len(tasks_created),
        "items_to_compile": len(item_ids),
    }


def _create_single_compile_task(item_ids: list[str]) -> int:
    """Create a single compile task record + pending task file. Returns task_id."""
    task = knowledge_repo.create_task("compile", {"item_ids": item_ids})

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    task_path = PENDING_DIR / f"task-{task.id}.md"
    id_list = "\n".join(f"- [[{iid}]]" for iid in item_ids)

    task_path.write_text(
        f"""---
task_type: "compile"
status: "pending"
created_at: "{now_iso()}"
params:
  item_ids: {item_ids}
---

# 编译任务

请对以下知识条目执行编译：

{id_list}

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{{slug}}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
""",
        encoding="utf-8",
    )

    log.info(f"created compile task {task.id}: {len(item_ids)} items")
    return task.id


def _trigger_map_update() -> None:
    """Proactively update _MAP.md after creating compile tasks."""
    try:
        from backend.services.map_updater import update_map
        update_map()
    except Exception as e:
        log.warning(f"failed to update _MAP.md after compile task: {e}")
