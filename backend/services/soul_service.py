"""SOUL.md service — read / regenerate role profile."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.domain.knowledge_models import now_iso

log = logging.getLogger("hotspot.soul")

SOUL_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge" / "SOUL.md"
PENDING_DIR = SOUL_PATH.parent / "learning" / "tasks" / "pending"

DEFAULT_SOUL = """---
updated_at: "{timestamp}"
---

# SOUL.md — 角色画像

> 此文件由 Agent 自动生成。点击"重新生成"触发更新。

## 身份
- 角色: 待补充
- 核心领域: 待补充

## 知识深度
| 主题 | 掌握度 | 条目数 | 最近学习 |
|------|--------|--------|----------|
| (暂无数据) | | | |

## 学习偏好
- 偏好类型: 待补充
- 偏好难度: 待补充
"""


def get_soul() -> dict:
    """Read SOUL.md. Create default template on first access."""
    if not SOUL_PATH.exists():
        content = DEFAULT_SOUL.format(timestamp=now_iso())
        SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SOUL_PATH.write_text(content, encoding="utf-8")
        log.info("created default SOUL.md")
        return {"content": content, "exists": False}
    return {"content": SOUL_PATH.read_text(encoding="utf-8"), "exists": True}


def create_soul_task() -> dict:
    """Create a generate_soul task for Agent to execute."""
    from backend.repository.knowledge_repo import knowledge_repo
    task = knowledge_repo.create_task("generate_soul", {})

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    task_path = PENDING_DIR / f"task-{task.id}.md"
    task_path.write_text(
        f"""---
task_type: "generate_soul"
status: "pending"
created_at: "{now_iso()}"
---

# SOUL 重新生成任务

请扫描 knowledge/items/ 和 knowledge/concepts/，重新生成 SOUL.md 角色画像。
""",
        encoding="utf-8",
    )
    log.info(f"created soul task: {task.id}")
    return {"task_id": task.id, "status": "pending"}
