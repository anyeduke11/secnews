"""信源探测与分类 — 拆自 ``backend/api/sources.py`` (Batch 3 R3 行数收缩)。

- ``CATEGORY_KEYWORDS`` / :func:`classify_by_url_and_title` — URL+title 关键词分类
- :func:`_probe_url` — 异步探测 URL 可用性 + 抓 title (SSRF 兜底校验)
- ``POST /api/sources/custom/{sid}/probe`` — 重新 probe 自定义信源

probe 流程
---------
1. ``_probe_url(url)`` GET 抓首页（≤ 8s timeout）
2. 解析 ``<title>`` + URL 关键词 → :func:`classify_by_url_and_title`
3. probe 失败 → 400；probe 成功 → 写入 custom_sources 表
"""
from __future__ import annotations

import re
import time

import aiohttp
from fastapi import APIRouter, HTTPException

from backend.repository.custom_source_repo import CustomSourceRepository
from backend.utils.url_safety import UrlSafetyError, validate_url

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ---------------------------------------------------------------------------
# 分类关键词字典
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "ai": [
        "ai", "artificial", "intelligence", "gpt", "llm", "openai",
        "anthropic", "claude", "gemini", "深度学习", "机器学习", "大模型",
    ],
    "security": [
        "security", "vuln", "cve", "exploit", "kreb", "sans",
        "freebuf", "hacker", "安全", "漏洞", "攻防",
    ],
    "finance": [
        "finance", "stock", "market", "trading", "invest", "fund",
        "新浪财经", "东方财富", "金融", "投资", "股票",
    ],
    "startup": [
        "startup", "vc", "venture", "yc", "ycombinator",
        "hackernews", "techcrunch", "创业", "孵化", "创新",
    ],
    "github": ["github.com", "github"],
}


def classify_by_url_and_title(url: str, title: str) -> str:
    """Phase 8: 基于 URL + 页面 title 关键词自动识别 category

    算法：把每个分类的关键词在 ``url + title`` 字符串里出现的次数计分，
    取最高分对应的分类；并列/无命中 → fallback 到 ``ai``。
    """
    text = f"{url} {title}".lower()
    scores: dict[str, int] = dict.fromkeys(CATEGORY_KEYWORDS, 0)
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text:
                scores[cat] += 1
    best = max(scores.items(), key=lambda x: x[1])
    if best[1] == 0:
        return "ai"  # 默认 fallback
    return best[0]


async def _probe_url(url: str, timeout: float = 8.0) -> dict:
    """异步探测 URL 可用性 + 抓取 title

    v0.7.x P0: SSRF 防护 — ``add_custom_source`` 已先验过,
    这里再次校验防 DB 内 url 被改 / 重 probe 时 url 已失效 (defense in depth)。

    Returns
    -------
    ``{"ok": bool, "status_code": int, "latency_ms": float, "title"?: str, "error"?: str}``
    """
    # Defense in depth: 防御性 SSRF 校验 (add_custom_source 已先验, 这里兜底)
    try:
        validate_url(url)
    except UrlSafetyError as e:
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": 0.0,
            "error": f"ssrf_block: {str(e)[:200]}",
        }

    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session, session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": "Mozilla/5.0"},
        ) as resp:
            latency_ms = round((time.time() - t0) * 1000, 2)
            if resp.status >= 400:
                return {
                    "ok": False,
                    "status_code": resp.status,
                    "latency_ms": latency_ms,
                    "error": f"HTTP {resp.status}",
                }
            html = await resp.text(errors="replace")
            html = html[:50000]
            m = re.search(
                r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL
            )
            title = m.group(1).strip()[:200] if m else ""
            return {
                "ok": True,
                "status_code": resp.status,
                "latency_ms": latency_ms,
                "title": title,
            }
    except Exception as e:
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": round((time.time() - t0) * 1000, 2),
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }


@router.post("/custom/{sid}/probe")
async def re_probe_source(sid: int):
    repo = CustomSourceRepository()
    items = repo.list()
    src = next((s for s in items if s.id == sid), None)
    if src is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source id={sid} not found"},
        )
    probe = await _probe_url(src.url)
    repo.update_probe_result(
        sid,
        "ok" if probe["ok"] else "fail",
        probe["latency_ms"],
        probe.get("title", ""),
    )
    return {"status": "ok" if probe["ok"] else "fail", "probe": probe}
