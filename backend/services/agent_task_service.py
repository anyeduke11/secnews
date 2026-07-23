"""v1.7 Phase 5 — Agent Task Service.

职责:
  1. 创建任务 (DB 记录 + .md 任务文件)
  2. 列出待处理任务 (供 Agent API 返回)
  3. 完成任务 (更新 DB 状态 + 移动任务文件)

复用 knowledge_tasks 表 (不新建表), 遵循 project_memory 约定:
  - task_type 字段区分任务类型 (extract / compile / publish / ...)
  - params JSON 存放 target_type / target_id / priority 等元数据
  - 任务文件写入 knowledge/learning/tasks/pending/ 供外部 Agent 轮询
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.db import get_connection

log = logging.getLogger(__name__)

# 任务文件目录 (与 learning_service 一致)
TASKS_DIR = Path("knowledge/learning/tasks")
PENDING_DIR = TASKS_DIR / "pending"
PROCESSING_DIR = TASKS_DIR / "processing"
DONE_DIR = TASKS_DIR / "done"
FAILED_DIR = TASKS_DIR / "failed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    for d in (PENDING_DIR, PROCESSING_DIR, DONE_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 任务文件格式
# ---------------------------------------------------------------------------

_TASK_TEMPLATES = {
    "extract": "# 任务：自动提取标签\n\n请对目标内容提取标签 (CVE/技术栈/概念等)。\n\n## 步骤\n1. 读取目标内容\n2. 调用 extract_service.extract_tags\n3. 将结果写入 tags_repo + hotspot_tags",
    "compile": "# 任务：编译知识\n\n请将目标知识条目从 signal 编译为 generate 阶段。\n\n## 步骤\n1. 读取 knowledge/items/{id}.md\n2. 提取核心概念并结构化\n3. 更新 lifecycle=generate",
    "publish": "# 任务：发布内容\n\n请根据目标知识生成并发布内容。\n\n## 步骤\n1. 读取知识条目\n2. 生成内容草稿\n3. 写入 content/drafts/",
    "generate_learning_plan": "# 任务：生成学习计划\n\n请使用 knowledge-master skill 生成本周学习计划。",
    "generate_soul": "# 任务：生成 SOUL 画像\n\n请根据知识库内容更新 SOUL.md。",
}


def _write_task_file(
    task_id: int,
    task_type: str,
    params: dict,
    target_type: str = "",
    target_id: str = "",
) -> Path:
    """在 pending/ 目录创建任务 .md 文件."""
    _ensure_dirs()
    path = PENDING_DIR / f"task-{task_id}.md"
    template = _TASK_TEMPLATES.get(task_type, f"# 任务：{task_type}\n\n请处理此任务。")
    body = f"""---
task_id: {task_id}
task_type: "{task_type}"
status: "pending"
created_at: "{_now_iso()}"
target_type: "{target_type}"
target_id: "{target_id}"
priority: {params.get("priority", 1)}
params:
{json.dumps(params, ensure_ascii=False, indent=2)}
---

{template}

## 目标
- 类型: {target_type or "(未指定)"}
- ID: {target_id or "(未指定)"}

## 参数
```json
{json.dumps(params, ensure_ascii=False, indent=2)}
```
"""
    path.write_text(body, encoding="utf-8")
    return path


def _move_task_file(task_id: int, target_dir: Path) -> None:
    """将任务文件从 pending/ 移到 target_dir."""
    src = PENDING_DIR / f"task-{task_id}.md"
    if src.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / f"task-{task_id}.md"
        src.rename(dst)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def create_task(
    task_type: str,
    target_type: str = "",
    target_id: str = "",
    priority: int = 1,
    params: Optional[dict] = None,
) -> dict:
    """创建任务 (DB + .md 文件).

    Args:
        task_type: 任务类型 (extract / compile / publish / ...)
        target_type: 目标类型 (hotspot / knowledge / concept)
        target_id: 目标 ID
        priority: 优先级 (1=最高)
        params: 额外参数

    Returns:
        {"task_id": int, "task_type": str, "status": "pending", ...}
    """
    full_params = {
        "target_type": target_type,
        "target_id": target_id,
        "priority": priority,
        **(params or {}),
    }
    task = knowledge_repo.create_task(task_type, full_params)
    _write_task_file(task.id, task_type, full_params, target_type, target_id)
    log.info(
        "created agent task %d: type=%s target=%s/%s",
        task.id, task_type, target_type, target_id,
    )
    return {
        "task_id": task.id,
        "task_type": task_type,
        "status": "pending",
        "target_type": target_type,
        "target_id": target_id,
        "priority": priority,
        "created_at": task.created_at,
    }


def list_pending(limit: int = 10) -> list[dict]:
    """列出 pending 状态的任务 (按 created_at 升序)."""
    tasks = knowledge_repo.list_tasks(status="pending")
    # 按 created_at 升序 (先创建先处理)
    tasks.sort(key=lambda t: t.created_at)
    result = []
    for t in tasks[:limit]:
        params = t.params or {}
        result.append({
            "task_id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "target_type": params.get("target_type", ""),
            "target_id": params.get("target_id", ""),
            "priority": params.get("priority", 1),
            "created_at": t.created_at,
            "params": params,
        })
    return result


def get_task(task_id: int) -> Optional[dict]:
    """查询单个任务详情."""
    row = knowledge_repo.get_task(task_id)
    if row is None:
        return None
    params = json.loads(row["params"]) if row.get("params") else {}
    return {
        "task_id": row["id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "target_type": params.get("target_type", ""),
        "target_id": params.get("target_id", ""),
        "priority": params.get("priority", 1),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "params": params,
        "result_path": row.get("result_path"),
        "error_message": row.get("error_message"),
    }


def complete_task(
    task_id: int,
    status: str = "done",
    result: Optional[dict] = None,
    error: str = "",
) -> dict:
    """完成任务: 更新 DB 状态 + 移动任务文件.

    Args:
        task_id: 任务 ID
        status: 新状态 (done / failed)
        result: 结果数据 (写入 params)
        error: 错误信息

    Returns:
        {"task_id": int, "status": str, "success": True}

    Raises:
        ValueError: task_id 不存在
    """
    existing = get_task(task_id)
    if existing is None:
        raise ValueError(f"task {task_id} not found")

    result_path = ""
    error_message = error or ""

    # 如果有 result, 更新 params 中的 result 字段
    if result:
        params = existing.get("params", {})
        params["result"] = result
        knowledge_repo.update_task_params(task_id, params)
        result_path = f"task-{task_id}.md"

    knowledge_repo.update_task_status(
        task_id=task_id,
        status=status,
        result_path=result_path or None,
        error_message=error_message or None,
    )

    # 移动任务文件
    if status == "done":
        _move_task_file(task_id, DONE_DIR)
    elif status == "failed":
        _move_task_file(task_id, FAILED_DIR)

    log.info("completed agent task %d: status=%s", task_id, status)
    return {"task_id": task_id, "status": status, "success": True}
