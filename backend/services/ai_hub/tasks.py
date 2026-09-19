"""ai_hub/tasks.py — AI 任务门面：评价辅助 + evaluate_article 入口。

v0.7 拆分: 原 tasks.py (412 行) 拆为:
- ``service.py`` — ``AIService`` 整个类 (评价/门禁/限频/缓存/用量) + ``_DETECT_SYSTEM`` 常量
- 知识写回门面 (write_score / write_item / update_frontmatter) 已外移至
  ``backend/services/ai_write_back.py`` (解知识域 ↔ ai_hub 域级环)
- ``tasks.py`` (本文件) — 评价辅助 + ``evaluate_article`` 入口

向后兼容: 所有原有 ``from backend.services.ai_hub import ...`` 仍可解析
(由 ``__init__.py`` re-export 统一暴露).
"""
from __future__ import annotations

import hashlib
import json
import logging

log = logging.getLogger("hotspot.ai_hub")

# 默认评分兜底 (score 0-10 / confidence 用 0.5 见 ai_write_back.write_item 侧)
DEFAULT_SCORE = 5.0


# ═══════════════════════════════════════════════════════════════
# Prompt / 解析 (AI 能力辅助)
# ═══════════════════════════════════════════════════════════════

def _cache_key(prefix: str, content: str) -> str:
    return f"{prefix}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _eval_prompt(title: str, content: str) -> str:
    title_line = f"标题：{title}\n" if title else ""
    return (
        "你是一名资深内容质量评审。请对下面的文章做两件事，并严格以 JSON 输出"
        "（不要任何其他文字）：\n"
        "1. 评价文章质量，fields: {\"score\": 0到10的浮点数，"
        "\"verdict\": 一句话总体评价}\n"
        "2. 提取文章关键内容，fields: {\"summary\": 2-3句摘要, "
        "\"key_points\": [3-6个要点字符串]}\n"
        f"输出格式：{{\"score\": <0-10>,\"verdict\":\"...\","
        f"\"summary\":\"...\",\"key_points\":[\"...\",\"...\"]}}\n\n"
        f"{title_line}文章内容：\n{content[:4000]}"
    )


def _parse_eval_json(raw: str, *, provider: str) -> dict:
    import re
    try:
        start, end = raw.index("{"), raw.rindex("}")
        data = json.loads(raw[start:end + 1])
        if isinstance(data, dict):
            return {
                "provider": provider,
                "quality_score": float(data.get("score", DEFAULT_SCORE)),
                "verdict": str(data.get("verdict", "")),
                "summary": str(data.get("summary", "")),
                "key_points": [str(k) for k in data.get("key_points", [])],
            }
    except (ValueError, json.JSONDecodeError):
        pass
    m = re.search(r"\"score\"\s*:\s*(\d+(?:\.\d+)?)", raw)
    score = float(m.group(1)) if m else DEFAULT_SCORE
    return {
        "provider": provider,
        "quality_score": score,
        "verdict": raw[:200],
        "summary": "",
        "key_points": [],
    }


def _parse_score01(raw: str) -> float:
    import re
    m = re.search(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", (raw or "").strip())
    if not m:
        return 0.0
    return max(0.0, min(1.0, float(m.group(0))))


# ── 语义门禁 (2026-09-18 方案 B, gate semantic_filter) ─────────────
_SEMANTIC_VERDICT_PROMPT = """你是资讯质量门禁。判断以下条目是否值得保留进入知识管线。
判定标准:
- allow: 与安全 / AI / 技术资讯相关, 或对从业者有信息量
- reject: 广告、软文、招聘、活动宣传、与主题无关的噪声

条目内容:
{content}

只输出 JSON, 不要输出其他文字:
{{"verdict": "allow" 或 "reject", "reason": "一句话理由"}}"""


def _build_semantic_verdict_prompt(content: str) -> str:
    return _SEMANTIC_VERDICT_PROMPT.format(content=content[:2000])


def _parse_verdict_json(raw: str) -> dict:
    """容错解析 verdict JSON; 解析失败 → allow (fail-open, 门禁故障不丢内容)。"""
    import json as _json
    import re as _re
    try:
        m = _re.search(r"\{.*\}", raw or "", _re.DOTALL)
        if not m:
            return {"verdict": "allow", "reason": "parse_failed_empty"}
        data = _json.loads(m.group(0))
        verdict = data.get("verdict")
        if verdict == "reject":
            return {"verdict": "reject", "reason": str(data.get("reason", ""))}
        return {"verdict": "allow", "reason": str(data.get("reason", ""))}
    except Exception:
        return {"verdict": "allow", "reason": "parse_failed_exception"}


def semantic_verdict(content: str) -> dict:
    """LLM verdict-only 判别 (同步入口, 链路内 asyncio.run 包裹 — t1 同款模式)。

    走 gateway.generate 通用漏斗 (task="semantic_filter"); 全链失败
    generate 返回 "" → _parse_verdict_json fail-open allow。
    """
    import asyncio

    from .gateway import llm_service

    try:
        raw = asyncio.run(llm_service.generate(
            _build_semantic_verdict_prompt(content), task="semantic_filter",
        ))
    except Exception:
        # fail-open: LLM 链路故障 (provider 全挂/超时) 不丢内容。
        return {"verdict": "allow", "reason": "llm_failed_fail_open"}
    return _parse_verdict_json(raw or "")


def _est_tokens(text: str) -> int:
    return len(text) // 4


# ═══════════════════════════════════════════════════════════════
# evaluate_article — 文章评价统一入口 (M5 合并后单契约)
# ═══════════════════════════════════════════════════════════════
async def evaluate_article(
    content: str,
    *,
    title: str = "",
    provider: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict:
    """用大模型评价文章质量并提炼关键内容（统一委托 AIService）。

    凭据 / 缓存 / 用量 / 限频统一由 ``ai_service`` 管理（env 优先，
    不再读 settings 表）。返回结构化结果：

        { ok, provider, quality_score(0-10), verdict,
          key_points: [str], summary, error? }

    失败时 ok=False + error（不静默降级，便于测试定位）。
    """
    import asyncio

    from backend.services.ai_hub.service import ai_service

    def _call():
        return ai_service.evaluate(
            content, title=title, provider=provider,
            api_key=api_key, timeout=timeout,
        )

    # evaluate 为同步阻塞的 httpx 调用，放入线程池避免阻塞事件循环
    return await asyncio.to_thread(_call)


__all__ = [
    "DEFAULT_SCORE",
    "_cache_key",
    "_est_tokens",
    "_eval_prompt",
    "_parse_eval_json",
    "_parse_score01",
    "evaluate_article",
]
