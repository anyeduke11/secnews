"""AI 研判起草器 (v0.8.6 P1-1 切片 2) — ai_hub HEAVY 单出口 + 结构化草案 + md 渲染。

人主律链路位置: Case 证据 → 本模块生成**草案** → v1_proposals(draft) 待审,
草案本身不构成事实; 超时/拒绝/返回不可解析 → 调用方落 status=failed,
不回落默认值、不缓存伪内容 (P0-6 纪律延续)。

- HEAVY 档: ``task="report"`` → model_router TASK_TIER_MAP → t3_summary
  (config/llm.yaml: sensenova deepseek-v4-pro), 零配置改动命中重档。
- 同步桥: 服务层同步调用, 仿 action_service/auto_classifier 用
  ``asyncio.run(ai_service.generate_text(...))``。
- md 渲染供批准后 Artifact 落盘, 正文内嵌证据 url (Source 原文),
  闭合用例 A 验收① "Artifact 一路回溯到 Source 原文"。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

JUDGMENT_DRAFT_PROMPT_VERSION = "judgment-draft@v1"

# 草案必备字段: 无 claim 视为模型未完成任务 (不编造)。
_REQUIRED_FIELDS = ("claim",)
_OPTIONAL_FIELDS = ("conditions", "confidence", "unknowns")
_VALID_CONFIDENCE = {"high", "medium", "low"}

_SYSTEM_PROMPT = (
    "你是安全研判助手。仅基于用户给出的案件证据材料起草研判草案, "
    "不得编造证据中不存在的事实; 证据不足时在 unknowns 中列明。"
    "只输出一个 JSON 对象, 字段: claim(研判结论,一句话), "
    "conditions(成立条件与前提), confidence(high|medium|low), "
    "unknowns(数组:尚需核实的事项)。不要输出 JSON 以外的文字。"
)


class JudgmentDraftError(Exception):
    """起草失败: LLM 不可用/超时/返回空或不可解析。消息进入 failed 提案 error_msg。"""


def _build_user_prompt(case_id: str, evidence: list[dict[str, Any]]) -> str:
    lines = [f"案件 {case_id} 关联证据材料:"]
    for i, m in enumerate(evidence, 1):
        title = m.get("title") or m.get("id") or "(无标题)"
        url = m.get("url") or ""
        summary = m.get("summary") or ""
        lines.append(f"{i}. [{m.get('id')}] {title} {url}\n   摘要: {summary}")
    lines.append("请基于以上材料输出研判草案 JSON。")
    return "\n".join(lines)


def _parse_json_object(raw: str) -> dict[str, Any]:
    """从模型输出提取首个 JSON 对象 (容忍 ```json fence 与前后缀文字)。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise JudgmentDraftError(f"draft response is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise JudgmentDraftError("draft response JSON is not an object")
    return obj


def _coerce_payload(obj: dict[str, Any]) -> dict[str, Any]:
    """规整 + 必填校验; confidence 非法归一为 unknowns 注记而非静默改值。"""
    payload: dict[str, Any] = {}
    claim = obj.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        raise JudgmentDraftError("draft missing non-empty 'claim'")
    payload["claim"] = claim.strip()
    payload["conditions"] = str(obj.get("conditions") or "").strip()
    confidence = obj.get("confidence")
    if confidence not in _VALID_CONFIDENCE:
        raise JudgmentDraftError(
            f"draft confidence invalid: {confidence!r} (expected high|medium|low)"
        )
    payload["confidence"] = confidence
    unknowns = obj.get("unknowns") or []
    if not isinstance(unknowns, list):
        raise JudgmentDraftError("draft 'unknowns' must be an array")
    payload["unknowns"] = [
        str(u).strip() for u in unknowns if u is not None and str(u).strip()
    ]
    return payload


def ai_draft_judgment(case_context: dict[str, Any]) -> dict[str, Any]:
    """默认生产 drafter (同步): 证据上下文 → HEAVY 档 → 规整后草案 dict。

    任何失败抛 JudgmentDraftError, 由 RunLedgerService.draft_judgment
    落 failed 提案 (用例 A②)。
    """
    from backend.services.ai_hub import ai_service

    evidence = case_context.get("evidence") or []
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(
            case_context.get("case_id", ""), evidence)},
    ]
    try:
        raw = asyncio.run(ai_service.generate_text(
            messages, task="report", max_tokens=1600, temperature=0.3,
        ))
    except JudgmentDraftError:
        raise
    except Exception as e:  # 超时/拒绝/网络 — 显式失败, 不吞 (用例 A②)
        raise JudgmentDraftError(f"{type(e).__name__}: {e}") from e
    if not raw or not raw.strip():
        raise JudgmentDraftError("empty draft response (model refused/unavailable)")
    return _coerce_payload(_parse_json_object(raw))


def render_judgment_markdown(
    *, case_id: str, payload: dict[str, Any], evidence: list[dict[str, Any]],
    proposal_id: str,
) -> str:
    """批准产物 md: 研判正文 + 证据原文链接 (回溯链终端) + 溯源元信息。"""
    lines = [
        f"# 研判草案 — 案件 {case_id}",
        "",
        f"- 提案: `{proposal_id}` (人工批准, dual-sign)",
        f"- prompt 版本: `{JUDGMENT_DRAFT_PROMPT_VERSION}`",
        f"- 置信度: **{payload.get('confidence', '')}**",
        "",
        "## 研判结论",
        str(payload.get("claim", "")).strip(),
        "",
        "## 成立条件",
        str(payload.get("conditions") or "(未列明)").strip(),
        "",
        "## 尚需核实",
    ]
    unknowns = payload.get("unknowns") or []
    if unknowns:
        lines.extend(f"- {u}" for u in unknowns)
    else:
        lines.append("(无)")
    lines.extend(["", "## 证据材料 (回溯 Source 原文)"])
    for m in evidence:
        title = m.get("title") or m.get("id") or "(无标题)"
        url = m.get("url") or ""
        h = str(m.get("content_hash") or "")[:16]
        lines.append(f"- [{m.get('id')}] {title} — {url} (sha256:{h})")
    lines.append("")
    return "\n".join(lines)
