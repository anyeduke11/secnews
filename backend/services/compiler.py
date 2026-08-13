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

# P0 背压: 单次 stale 检测配额。历史 bug: 把所有 compiled=false 条目
# 全部视为 stale, 每日定时任务一次生成 ~400 个任务 (10 条/批), 积压到
# 1980+ 无消费者。现在每次最多返回 STALE_ITEM_DAILY_QUOTA 条 (按
# updated_at 最旧优先), 形成自然背压, 让 Agent 有节奏地消化积压。
STALE_ITEM_DAILY_QUOTA = 50

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


def _parse_updated_at(item) -> Optional[datetime]:
    """解析 item.updated_at 为可比较的 datetime (用于最旧优先排序).

    兼容 ISO 8601 带 Z 后缀 / 无时区 (按 UTC 处理) / 解析失败返回 None。
    """
    updated_at_str = item.updated_at
    if not updated_at_str:
        return None
    if updated_at_str.endswith("Z"):
        updated_at_str = updated_at_str[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(updated_at_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def detect_stale_items(limit: int = STALE_ITEM_DAILY_QUOTA) -> dict:
    """Detect items that need recompilation.

    Conditions:
      1. compiled=false → reason="compiled=false"
      2. .md file mtime > SQLite updated_at → reason="file_modified"

    P0 背压修复:
      - 不再把全部 compiled=false 视为 stale — 默认只返回 ``limit`` 条
        (50), 按 updated_at 最旧优先排序, 避免历史积压一次性全量入队。
      - ``limit=0`` 表示不限制 (预览全量用)。

    Returns: {"stale_items": [id1, id2], "reasons": {id1: "compiled=false", ...}}
    """
    stale_items: list = []
    reasons: dict[str, str] = {}

    items = knowledge_repo.list_items(limit=10000)
    for item in items:
        # Condition 1: compiled=false
        if not item.compiled:
            stale_items.append(item)
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

        updated_at_dt = _parse_updated_at(item)
        if updated_at_dt is None:
            continue
        if file_mtime_dt > updated_at_dt:
            stale_items.append(item)
            reasons[item.id] = "file_modified"

    # 背压: 按 updated_at 最旧优先 (缺失 updated_at 视为最旧, 优先处理),
    # 只取前 limit 条。limit<=0 表示不限制。
    if limit and limit > 0 and len(stale_items) > limit:
        _SENTINEL_OLD = datetime.min.replace(tzinfo=timezone.utc)
        stale_items.sort(key=lambda it: _parse_updated_at(it) or _SENTINEL_OLD)
        stale_items = stale_items[:limit]

    return {
        "stale_items": [it.id for it in stale_items],
        "reasons": {it.id: reasons[it.id] for it in stale_items},
    }


def _pending_compile_item_ids() -> set[str]:
    """收集所有 pending compile 任务中已入队的 item_id (创建前去重用).

    knowledge_tasks 表没有 item_id 列 — item_ids 存在 params JSON 里
    ({"item_ids": [...]}), 因此遍历 pending 任务解析 params 求并集。
    查询失败时返回空集 (不去重, 仅 log 警告, 不阻断任务创建)。
    """
    queued: set[str] = set()
    try:
        tasks = knowledge_repo.list_tasks(status="pending")
    except Exception as e:
        log.warning(f"failed to list pending tasks for dedup: {e}")
        return queued
    for t in tasks:
        if t.task_type != "compile":
            continue
        params = t.params or {}
        item_ids = params.get("item_ids")
        if isinstance(item_ids, list):
            queued.update(str(i) for i in item_ids)
    return queued


def create_compile_task(item_ids: Optional[list[str]] = None) -> dict:
    """Create a compile task.

    Args:
        item_ids: specific item IDs to compile. If None, detect stale items
                  (compiled=false or file modified, 背压限 50 条). If empty
                  list, return no_items.

    P0 去重: 创建前检查 pending 队列中是否已有同 item 的任务, 命中则跳过。

    Returns:
        ≤10 items: {task_id, status, items_to_compile, skipped_duplicates}
        >10 items: {tasks: [{task_id, items_count}], total_tasks, items_to_compile,
                    skipped_duplicates}
    """
    if item_ids is None:
        # Detect stale items (compiled=false OR file modified, 限量背压)
        stale = detect_stale_items()
        item_ids = stale["stale_items"]
    elif not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": 0}

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": 0}

    # P0 去重: 跳过 pending 队列中已存在的同 item 任务
    skipped_duplicates = 0
    pending_ids = _pending_compile_item_ids()
    if pending_ids:
        deduped = [iid for iid in item_ids if iid not in pending_ids]
        skipped_duplicates = len(item_ids) - len(deduped)
        item_ids = deduped

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": skipped_duplicates}
    if skipped_duplicates:
        log.info(
            f"create_compile_task: skipped {skipped_duplicates} item(s) "
            f"already pending in queue"
        )

    # Batch processing: 10 items per task
    BATCH_SIZE = 10
    if len(item_ids) <= BATCH_SIZE:
        task_id = _create_single_compile_task(item_ids)
        _trigger_map_update()
        return {
            "task_id": task_id,
            "status": "pending",
            "items_to_compile": len(item_ids),
            "skipped_duplicates": skipped_duplicates,
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
        "skipped_duplicates": skipped_duplicates,
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
