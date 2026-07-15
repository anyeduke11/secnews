"""Compiler service — create compile tasks for Agent to execute.

Design: backend only creates task records + pending task files.
The actual LLM compilation is done by Agent via knowledge-base-manager skill.
"""

from __future__ import annotations

import logging
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


def create_compile_task(item_ids: Optional[list[str]] = None) -> dict:
    """Create a compile task.

    Args:
        item_ids: specific item IDs to compile. If None, compile all
                  compiled=false items. If empty list, return no_items.

    Returns: {task_id, status, items_to_compile}
    """
    if item_ids is None:
        # Query all compiled=false items
        items = knowledge_repo.list_items(compiled=False, limit=1000)
        item_ids = [i.id for i in items]
    elif not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0}

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0}

    # Create task record in DB
    task = knowledge_repo.create_task("compile", {"item_ids": item_ids})

    # Write task file to pending/ for Agent to pick up
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
    return {
        "task_id": task.id,
        "status": "pending",
        "items_to_compile": len(item_ids),
    }
