"""plan 起草生成器 — ai_hub 草稿 + 人工手写兜底 (C3-3)。

角色分工 (P10 §1, D1 继承): LLM 起草的 plan 是**建议**, 人未审批不执行 (L1 默认拒绝);
生成失败 (LLM 不可用 / 输出非法) → ExecutionPlanGenerationError, 前端落人工手写兜底表单
(D3 裁决③: plan 本质是结构化表单)。

ai_hub 红线不碰: 只走公共入口 ``llm_service.generate`` (rejection_explain 同款
sync 包装 asyncio.run; 调用方在 to_thread 线程无 loop — DEV-0287 D2 契约)。
dsh 可达性: vendor 死路 (D3 节点) → 起草者即 ai_hub 生态 LLM, 信任模型不变
(产出仍过人审批 + enforce + L4 逐条比对)。
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from backend.exceptions import InvalidParamException


class ExecutionPlanGenerationError(InvalidParamException):
    """plan 起草失败 (LLM 不可用 / 输出不可解析) — 前端落人工手写兜底。"""

    def __init__(self, message: str = "execution plan generation failed") -> None:
        super().__init__(message)


def build_plan_prompt(action: dict[str, Any]) -> str:
    """从 action 行构建起草 prompt — 只用 action 既有字段, 不引入新概念。"""
    return f"""你是安全工作台的执行计划起草器。请为以下已批准的 Action 起草一份 ExecutionPlan (JSON)。

Action 信息:
- 标题: {action.get("title", "")}
- 计划描述: {action.get("plan", "")}
- 成功标准: {action.get("success_criteria", "")}
- 预期产物: {action.get("expected_artifacts", [])}

ExecutionPlan schema (严格遵守):
{{
  "commands": [["可执行名", "参数", ...], ...],   // argv 级允许执行的命令, 逐条列出; 只读类任务用 cat/ls/python 等
  "writable_paths": ["相对可写目录", ...],
  "readable_paths": ["相对可读目录", ...],
  "network": [],                                   // 默认空 = 全禁出站; 非必要不放开
  "command_timeout_sec": 120,                      // 单命令上限 (1~3600)
  "total_timeout_sec": 900,                        // 总时长上限 (1~86400)
  "output_artifact": {{"kind": "report", "title": "...", "acceptance_notes": "验收要点"}}
}}
kind 仅允许: report|file|data|chart|code_patch|message。

只输出一个 JSON 对象, 不要多余文字。最小权限原则: 命令尽可能少、路径尽可能窄、network 保持空。
"""


def _extract_json(raw: str | None) -> dict[str, Any]:
    """从 LLM 输出提取首个 JSON 对象 (rejection_explain 同款策略, 对象版)。"""
    if not raw:
        raise ExecutionPlanGenerationError("LLM 返回为空")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ExecutionPlanGenerationError("LLM 输出中无 JSON 对象")
    import json
    try:
        data = json.loads(m.group(0))
    except ValueError as e:
        raise ExecutionPlanGenerationError(f"LLM 输出 JSON 不可解析: {e}") from e
    if not isinstance(data, dict):
        raise ExecutionPlanGenerationError("LLM 输出非 JSON 对象")
    return data


def generate_plan_draft(
    *, run_id: str, action: dict[str, Any], submitted_by: str = "user",
) -> dict[str, Any]:
    """起草 ExecutionPlan → schema 校验 → 提交为 draft (source='ai_draft')。

    未审批不执行 (L1); 任何失败抛 ExecutionPlanGenerationError → 人工手写兜底。
    """
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.service import ExecutionPlanService

    prompt = build_plan_prompt(action)
    try:
        raw = asyncio.run(llm_service.generate(prompt, task="execution_plan_draft"))
    except Exception as e:
        raise ExecutionPlanGenerationError(f"LLM 调用失败: {type(e).__name__}: {e}") from e
    payload = _extract_json(raw)
    try:
        return ExecutionPlanService().submit(
            run_id, payload, submitted_by=submitted_by, source="ai_draft",
        )
    except Exception as e:
        # schema 校验失败同样落兜底 (LLM 幻觉字段/越权命令由人改写)
        raise ExecutionPlanGenerationError(
            f"AI 起草的 plan 未过 schema 校验 (人工手写兜底): {e}") from e
