"""Phase 8 Addendum 8.4: 信源管理 API

端点
----
- ``GET    /api/sources/custom``          列出所有自定义信源
- ``POST   /api/sources/custom``          添加（自动 probe + 分类识别）
- ``DELETE /api/sources/custom/{sid}``    删除
- ``POST   /api/sources/custom/{sid}/probe``  重新 probe
- ``POST   /api/sources/custom/{sid}/toggle?enabled=...``  启用/禁用
- ``GET    /api/sources/health``          Phase 9 招标源质量门禁：所有源覆盖度报告
- ``GET    /api/sources/health/{category}``  1 个分类下的源健康度
- ``POST   /api/sources/health/{category}/{source_name}/reset``  手动重置 (清 zero_yield)
- ``POST   /api/sources/health/{category}/{source_name}/dead``   手动标 dead

probe 流程
---------
1. ``_probe_url(url)`` GET 抓首页（≤ 8s timeout）
2. 解析 ``<title>`` + URL 关键词 → :func:`classify_by_url_and_title`
3. probe 失败 → 400；probe 成功 → 写入 custom_sources 表
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.domain.enums import Category
from backend.logging_config import logger
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.repository.source_stats_repo import SourceStatsRepository

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
    "bid": [
        "bid", "procurement", "tender", "tender.gov",
        "政府采购", "招标", "投标", "采购",
    ],
    "github": ["github.com", "github"],
}


def classify_by_url_and_title(url: str, title: str) -> str:
    """Phase 8: 基于 URL + 页面 title 关键词自动识别 category

    算法：把每个分类的关键词在 ``url + title`` 字符串里出现的次数计分，
    取最高分对应的分类；并列/无命中 → fallback 到 ``ai``。
    """
    text = f"{url} {title}".lower()
    scores: dict[str, int] = {c: 0 for c in CATEGORY_KEYWORDS}
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

    Returns
    -------
    ``{"ok": bool, "status_code": int, "latency_ms": float, "title"?: str, "error"?: str}``
    """
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
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


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AddSourceRequest(BaseModel):
    url: str
    name: str = ""
    category: Optional[str] = None  # None = 自动识别


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/custom")
async def list_custom_sources():
    """列出所有自定义信源"""
    repo = CustomSourceRepository()
    return {"sources": [s.to_dict() for s in repo.list()]}


@router.post("/custom")
async def add_custom_source(req: AddSourceRequest):
    """添加自定义信源：先探测，探测通过则写入"""
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail={"message": "URL 必须以 http:// 或 https:// 开头"},
        )

    # 1) 探测
    probe = await _probe_url(url)
    if not probe["ok"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"信源不可用: {probe.get('error', 'unknown')}",
                "probe": probe,
            },
        )

    # 2) 分类（自动 / 手动）
    category = req.category or classify_by_url_and_title(url, probe.get("title", ""))
    if category not in [c.value for c in Category]:
        category = "ai"

    # 3) 写入
    repo = CustomSourceRepository()
    try:
        sid = repo.add(
            url=url,
            name=req.name.strip() or probe.get("title", url)[:80],
            category=category,
            last_check_status="ok",
            last_check_latency_ms=probe["latency_ms"],
            last_check_title=probe.get("title", ""),
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail={"message": "URL 已存在"})
        raise HTTPException(status_code=500, detail={"message": str(e)[:200]})

    logger.info(f"custom_source added: id={sid} url={url} category={category}")
    return {
        "status": "ok",
        "id": sid,
        "url": url,
        "category": category,
        "probe": probe,
    }


@router.delete("/custom/{sid}")
async def delete_custom_source(sid: int):
    repo = CustomSourceRepository()
    ok = repo.delete(sid)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source id={sid} not found"},
        )
    return {"status": "ok", "deleted": sid}


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


@router.post("/custom/{sid}/toggle")
async def toggle_source(sid: int, enabled: bool):
    repo = CustomSourceRepository()
    ok = repo.set_enabled(sid, enabled)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source id={sid} not found"},
        )
    return {"status": "ok", "id": sid, "enabled": enabled}


# ===========================================================================
# Phase 9 招标源质量门禁 API
# ===========================================================================
def _build_health_payload(category: Optional[str]) -> dict:
    """同步构建 health 报告（在 thread pool 中执行）。"""
    repo = SourceStatsRepository()
    if category:
        rows = repo.list_by_category(category)
    else:
        rows = repo.list_all()
    summary = repo.summary_by_category()
    return {
        "version": "1.2.0",
        "category": category or "all",
        "summary": summary,
        "sources": [
            {
                "category": r["category"],
                "source_name": r["source_name"],
                "source_url": r["source_url"],
                "last_seen_at": r["last_seen_at"],
                "last_checked_at": r["last_checked_at"],
                "total_runs": int(r["total_runs"] or 0),
                "zero_yield_runs": int(r["zero_yield_runs"] or 0),
                "total_items": int(r["total_items"] or 0),
                "last_error": r["last_error"],
                "status": r["status"],
            }
            for r in rows
        ],
        "dead_count": sum(1 for r in rows if r["status"] == "dead"),
        "stale_count": sum(1 for r in rows if r["status"] == "stale"),
        "active_count": sum(1 for r in rows if r["status"] == "active"),
    }


@router.get("/health")
async def list_source_health(category: Optional[str] = None):
    """返回所有 / 指定分类的源健康度报告（用于运维盯盘）。

    Phase 9 招标源质量门禁：
    - ``active``: 最近 1 次 collect 有产出
    - ``stale``: 连续 N 次零产出 (默认 3)
    - ``dead``: 连续 N 次零产出 (默认 6)

    ``summary`` 字段按 category 聚合 active / stale / dead / total 计数。
    """
    return await asyncio.to_thread(_build_health_payload, category)


@router.get("/health/by-source/{category}/{source_name}")
async def get_source_health(category: str, source_name: str):
    """返回单条 source 的累计统计。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    return {
        "version": "1.2.0",
        **{
            "category": row["category"],
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "last_seen_at": row["last_seen_at"],
            "last_checked_at": row["last_checked_at"],
            "total_runs": int(row["total_runs"] or 0),
            "zero_yield_runs": int(row["zero_yield_runs"] or 0),
            "total_items": int(row["total_items"] or 0),
            "last_error": row["last_error"],
            "status": row["status"],
        },
    }


@router.post("/health/by-source/{category}/{source_name}/reset")
async def reset_source(category: str, source_name: str):
    """手动重置 zero_yield_runs（运维工具，确认源已恢复时调用）。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    repo.reset(category, source_name)
    return {"status": "ok", "category": category, "source_name": source_name}


@router.post("/health/by-source/{category}/{source_name}/dead")
async def mark_dead_source(category: str, source_name: str):
    """手动标 dead（运维工具，确认源已下线时调用）。"""
    repo = SourceStatsRepository()
    row = repo.get_one(category, source_name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"source {source_name} not found in {category}"},
        )
    repo.mark_dead(category, source_name)
    return {"status": "ok", "category": category, "source_name": source_name}


__all__ = ["router"]
