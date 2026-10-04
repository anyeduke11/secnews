"""副驾起草器 (v0.8.6 P1-3 M3) — 副驾四卡的三条 LLM 起草链 + 批准产物渲染。

人主律链路位置 (与 judgment_drafter 同构): 卡片上下文 → 本模块生成**草案** →
v1_proposals(draft, source=copilot) 待审 → 人批准 → md 产物落盘 (Artifact
sha256 登记)。草案不构成事实; 失败由 RunLedgerService.copilot_draft 落
status=failed, 不回落默认值 (P0-6 纪律延续)。

- 档位: ``task="summary"`` (STANDARD 档, FLASH 便宜模型为主 — PRD M3 风险
  对策 "LLM 成本失控"; 判研 HEAVY 属 judgment_drafter/切片2, 不在本模块)。
- kind ↔ 四卡映射 (PRD §3.2 M3): 情报流研判建议 → judgment_draft (走
  /draft-judgment, 不在本文件); 知识自动摘要 → knowledge_draft;
  案件证据召回 → case_suggestion; SK-04 复盘草案 → report。
- 渲染: render_copilot_markdown 供批准后 Artifact 落盘; case 锚定时正文
  内嵌证据 Source url (回溯链终端, 用例 A① 同约定)。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

COPILOT_DRAFT_PROMPT_VERSION = "copilot-draft@v1"

# 三条副驾起草链 (judgment_draft 由 /draft-judgment 承接, 不在此列)
COPILOT_DRAFT_KINDS = ("case_suggestion", "knowledge_draft", "report")

_KIND_TITLES = {
    "case_suggestion": "建案建议草案",
    "knowledge_draft": "知识摘要草案",
    "report": "复盘草案",
}

# payload 契约: required = 非空字符串 (缺 → 显式失败不编造); lists = 字符串数组
_KIND_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "case_suggestion": {"required": ("title", "rationale"), "lists": ("evidence_refs",)},
    "knowledge_draft": {"required": ("title", "summary"), "lists": ("key_points",)},
    "report": {"required": ("title", "summary"), "lists": ("lessons", "next_actions")},
}

_SYSTEM_PROMPTS = {
    "case_suggestion": (
        "你是安全案件分析助手。仅基于用户给出的案件证据材料起草建案建议草案, "
        "不得编造证据中不存在的事实。只输出一个 JSON 对象, 字段: "
        "title(建议标题,一句话), rationale(立项理由与预期价值), "
        "evidence_refs(数组:支撑本建议的证据材料编号)。不要输出 JSON 以外的文字。"
    ),
    "knowledge_draft": (
        "你是知识整理助手。基于用户给出的资讯条目起草知识摘要草案, 忠于原文, "
        "不得添加原文不存在的事实。只输出一个 JSON 对象, 字段: "
        "title(知识标题), summary(摘要,2-4 句), "
        "key_points(数组:关键要点)。不要输出 JSON 以外的文字。"
    ),
    "report": (
        "你是复盘助手。基于用户给出的案件证据与结论材料起草行动复盘草案, "
        "聚焦可复用经验, 不追责。只输出一个 JSON 对象, 字段: "
        "title(复盘标题), summary(过程概述), "
        "lessons(数组:经验教训), next_actions(数组:后续行动建议)。"
        "不要输出 JSON 以外的文字。"
    ),
}


class CopilotDraftError(Exception):
    """副驾起草失败: LLM 不可用/超时/返回不可解析或缺必填字段。"""


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
        raise CopilotDraftError(f"draft response is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise CopilotDraftError("draft response JSON is not an object")
    return obj


def _coerce_payload(kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    """规整 + 必填校验 (缺必填 = 模型未完成任务, 显式失败)。"""
    contract = _KIND_CONTRACTS[kind]
    payload: dict[str, Any] = {}
    for field in contract["required"]:
        val = obj.get(field)
        if not isinstance(val, str) or not val.strip():
            raise CopilotDraftError(f"{kind} draft missing non-empty {field!r}")
        payload[field] = val.strip()
    for field in contract["lists"]:
        arr = obj.get(field) or []
        if not isinstance(arr, list):
            raise CopilotDraftError(f"{kind} draft {field!r} must be an array")
        payload[field] = [
            str(x).strip() for x in arr if x is not None and str(x).strip()
        ]
    return payload


def _build_user_prompt(context: dict[str, Any]) -> str:
    kind = context["kind"]
    lines: list[str] = []
    if kind == "knowledge_draft":
        item = context.get("item") or {}
        lines.append(f"资讯条目 {context.get('knowledge_id', '')}:")
        lines.append(f"标题: {item.get('title') or '(无标题)'}")
        if item.get("topic"):
            lines.append(f"内容摘要: {item['topic']}")
        lines.append("请输出知识摘要草案 JSON。")
        return "\n".join(lines)
    case_id = context.get("case_id", "")
    lines.append(f"案件 {case_id} 关联证据材料:")
    for i, m in enumerate(context.get("evidence") or [], 1):
        title = m.get("title") or m.get("id") or "(无标题)"
        url = m.get("url") or ""
        lines.append(f"{i}. [{m.get('id')}] {title} {url}\n   摘要: {m.get('summary') or ''}")
    ask = ("请基于以上材料输出建案建议草案 JSON。" if kind == "case_suggestion"
           else "请基于以上材料输出行动复盘草案 JSON。")
    lines.append(ask)
    return "\n".join(lines)


def ai_copilot_draft(context: dict[str, Any]) -> dict[str, Any]:
    """默认生产 drafter (同步): kind 上下文 → STANDARD 档 → 规整草案 dict。

    任何失败抛 CopilotDraftError, 由 RunLedgerService.copilot_draft 落
    failed 提案 (收件箱可见, 可重试)。
    """
    from backend.services.ai_hub import ai_service

    kind = context["kind"]
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPTS[kind]},
        {"role": "user", "content": _build_user_prompt(context)},
    ]
    try:
        raw = asyncio.run(ai_service.generate_text(
            messages, task="summary", max_tokens=1200, temperature=0.3,
        ))
    except CopilotDraftError:
        raise
    except Exception as e:  # 超时/拒绝/网络 — 显式失败, 不吞
        raise CopilotDraftError(f"{type(e).__name__}: {e}") from e
    if not raw or not raw.strip():
        raise CopilotDraftError("empty draft response (model refused/unavailable)")
    return _coerce_payload(kind, _parse_json_object(raw))


def render_copilot_markdown(
    *, kind: str, anchor_id: str | None, payload: dict[str, Any],
    evidence: list[dict[str, Any]], proposal_id: str,
) -> str:
    """批准产物 md (三 kind 通用): 草案字段 + 证据原文链接 (case 锚定时) + 溯源。"""
    title = _KIND_TITLES.get(kind, kind)
    anchor = f"案件 {anchor_id}" if anchor_id else _KIND_TITLES.get(kind, kind)
    lines = [f"# {title} — {anchor}", ""]
    lines.append(f"- 提案: `{proposal_id}` (人工批准, dual-sign)")
    lines.append(f"- prompt 版本: `{COPILOT_DRAFT_PROMPT_VERSION}`")
    lines.append("")
    if kind == "case_suggestion":
        lines.extend(["## 建议标题", str(payload.get("title", "")).strip(), "",
                      "## 立项理由"])
        lines.append(str(payload.get("rationale", "")).strip())
        refs = payload.get("evidence_refs") or []
        lines.extend(["", "## 引用证据编号"])
        lines.extend(f"- {r}" for r in refs) if refs else lines.append("(未列明)")
    else:
        lines.extend(["## 标题", str(payload.get("title", "")).strip(), "",
                      "## 摘要"])
        lines.append(str(payload.get("summary", "")).strip())
        for field, heading in (
            ("key_points", "关键要点"),
            ("lessons", "经验教训"),
            ("next_actions", "后续行动建议"),
        ):
            arr = payload.get(field) or []
            if not arr:
                continue
            lines.extend(["", f"## {heading}"])
            lines.extend(f"- {x}" for x in arr)
    if evidence:
        lines.extend(["", "## 证据材料 (回溯 Source 原文)"])
        for m in evidence:
            t = m.get("title") or m.get("id") or "(无标题)"
            url = m.get("url") or ""
            h = str(m.get("content_hash") or "")[:16]
            lines.append(f"- [{m.get('id')}] {t} — {url} (sha256:{h})")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COPILOT_DRAFT_KINDS",
    "COPILOT_DRAFT_PROMPT_VERSION",
    "CopilotDraftError",
    "ai_copilot_draft",
    "render_copilot_markdown",
]
