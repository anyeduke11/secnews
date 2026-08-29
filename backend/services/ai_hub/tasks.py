"""ai_hub/tasks.py — AI 任务门面：评价辅助 + evaluate_article 入口。

v0.7 拆分: 原 tasks.py (412 行) 拆为:
- ``service.py`` — ``AIService`` 整个类 (评价/门禁/限频/缓存/用量) + ``_DETECT_SYSTEM`` 常量
- ``write_back.py`` — 知识写回门面 (write_score / write_item / update_frontmatter)
- ``tasks.py`` (本文件) — 评价辅助 + ``evaluate_article`` 入口

向后兼容: 所有原有 ``from backend.services.ai_hub import ...`` 仍可解析
(由 ``__init__.py`` re-export 统一暴露).
"""
from __future__ import annotations

import hashlib
import json
import logging

log = logging.getLogger("hotspot.ai_hub")

# 默认评分兜底 (score 0-10 / confidence 用 0.5 见 write_item 侧)
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
    from backend.services.ai_hub.service import ai_service
    import asyncio

    def _call():
        return ai_service.evaluate(
            content, title=title, provider=provider,
            api_key=api_key, timeout=timeout,
        )

    # evaluate 为同步阻塞的 httpx 调用，放入线程池避免阻塞事件循环
    return await asyncio.to_thread(_call)


__all__ = [
    "DEFAULT_SCORE",
    "evaluate_article",
    "_cache_key",
    "_est_tokens",
    "_eval_prompt",
    "_parse_eval_json",
    "_parse_score01",
]
