"""v1.7 Phase 5 — Agent Executor.

根据 task_type 路由到对应 skill.
Skill 是可调用对象, 接收 (task, client) 并返回 dict 结果.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from agent.client import HotspotClient

log = logging.getLogger("hotspot.agent.executor")

# Skill 签名: Callable[[dict, HotspotClient], dict]
SkillFn = Callable[[dict, HotspotClient], dict]

# Skill 注册表 (按 task_type 分发)
SKILLS: dict[str, SkillFn] = {}


def register_skill(task_type: str):
    """装饰器: 注册 task_type → skill 函数."""
    def decorator(fn: SkillFn) -> SkillFn:
        SKILLS[task_type] = fn
        return fn
    return decorator


# ---- 内置 Skills ----

@register_skill("extract")
def extract_skill(task: dict, client: HotspotClient) -> dict:
    """提取任务 — 把目标 hotspot 的标题/摘要提取概念并写回知识条目.

    本 skill 不调用 LLM, 仅做基础概念提取 (关键词匹配),
    真实场景下可被外部 Agent 替换为更复杂的实现.
    """
    target_type = task.get("target_type", "")
    target_id = task.get("target_id", "")
    params = task.get("params", {})

    if not target_id:
        return {"extracted": 0, "note": "no target_id"}

    if target_type == "hotspot":
        from backend.repository.hotspot_repo import HotspotRepository
        repo = HotspotRepository()
        item = repo.get_by_id(target_id)
        if item is None:
            return {"extracted": 0, "note": f"hotspot {target_id} not found"}
        title = item.title or ""
        summary = item.summary or ""
        # 复用后端 extract_service
        try:
            from backend.services.extract_service import extract_tags
            tags = extract_tags(summary, title, item.category or "")
        except Exception as e:
            log.warning("extract_tags failed: %s", e)
            tags = []
        return {
            "extracted": len(tags),
            "tags": [t.get("tag_id") for t in tags if t.get("tag_id")],
            "target": f"{target_type}:{target_id}",
        }
    return {"extracted": 0, "note": f"unsupported target_type: {target_type}"}


@register_skill("compile")
def compile_skill(task: dict, client: HotspotClient) -> dict:
    """编译任务 — 将知识条目从 signal 升级到 generate."""
    target_id = task.get("target_id", "")
    if not target_id:
        return {"compiled": False, "note": "no target_id"}

    payload = {
        "item_id": target_id,
        "title": task.get("params", {}).get("title", f"Compiled: {target_id}"),
        "lifecycle": "generate",
        "tags": task.get("params", {}).get("tags", []),
    }
    try:
        client.write_knowledge(payload)
        return {"compiled": True, "item_id": target_id}
    except Exception as e:
        return {"compiled": False, "error": str(e)[:200]}


@register_skill("publish")
def publish_skill(task: dict, client: HotspotClient) -> dict:
    """发布任务 — 生成发布草稿 (实际平台发布由独立工作流处理)."""
    target_id = task.get("target_id", "")
    return {
        "published": True,
        "item_id": target_id,
        "note": "publish skill runs external workflow, agent only records intent",
    }


@register_skill("generate_learning_plan")
def plan_skill(task: dict, client: HotspotClient) -> dict:
    """学习计划任务 — 触发后端生成计划 (创建任务, 由 Agent 异步执行)."""
    try:
        from backend.repository.knowledge_repo import knowledge_repo
        task_record = knowledge_repo.create_task(
            "generate_learning_plan",
            params=task.get("params", {}),
        )
        return {"plan_generated": True, "task_id": task_record.id}
    except Exception as e:
        return {"plan_generated": False, "error": str(e)[:200]}


@register_skill("generate_soul")
def soul_skill(task: dict, client: HotspotClient) -> dict:
    """SOUL 生成任务 — 刷新 SOUL.md."""
    try:
        from backend.services.soul_service import get_soul
        result = get_soul()
        return {"soul_generated": True, "has_content": bool(result)}
    except Exception as e:
        return {"soul_generated": False, "error": str(e)[:200]}


# 注册可选 skills (通过 import 副作用触发装饰器)
try:
    from agent.skills import extract_tags as _extract_tags_skill  # noqa: F401
except ImportError:
    pass


# ---- 公开入口 ----

def execute_task(task: dict, client: Optional[HotspotClient] = None) -> dict:
    """根据 task_type 分发到对应 skill.

    Args:
        task: 任务 dict (含 task_type, target_type, target_id, params)
        client: HotspotClient 实例 (skill 可能调用写回 API)

    Returns:
        dict 结果 (写入任务的 params.result)
    """
    if client is None:
        client = HotspotClient()

    task_type = task.get("task_type", "")
    skill = SKILLS.get(task_type)
    if skill is None:
        log.warning("no skill for task_type=%s, skipping", task_type)
        return {"skipped": True, "reason": f"unknown task_type: {task_type}"}

    log.info("executing skill: task_type=%s", task_type)
    return skill(task, client)
