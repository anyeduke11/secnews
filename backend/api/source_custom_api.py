"""自定义信源 CRUD — 拆自 ``backend/api/sources.py`` (Batch 3 R3 行数收缩)。

- ``GET    /api/sources/custom``               列出所有自定义信源
- ``POST   /api/sources/custom``               添加（自动 probe + 分类识别）
- ``DELETE /api/sources/custom/{sid}``         删除
- ``POST   /api/sources/custom/{sid}/toggle``  启用/禁用

SSRF 防护: 添加入口 URL 必须先过 ``validate_url`` (v0.7.x P0)。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.source_probe_api import _probe_url, classify_by_url_and_title
from backend.domain.enums import Category
from backend.logging_config import logger
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.utils.url_safety import UrlSafetyError, validate_url

router = APIRouter(prefix="/api/sources", tags=["sources"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AddSourceRequest(BaseModel):
    url: str
    name: str = ""
    category: str | None = None  # None = 自动识别


@router.get("/custom")
async def list_custom_sources():
    """列出所有自定义信源"""
    repo = CustomSourceRepository()
    return {"sources": [s.to_dict() for s in repo.list()]}


@router.post("/custom")
async def add_custom_source(req: AddSourceRequest):
    """添加自定义信源：先探测，探测通过则写入

    v0.7.x P0: SSRF 防护 — 用户自定义 source 是高风险入口,
    URL 必须先过 ``validate_url`` 防 localhost / 私网 / 环回 IP,
    阻断时直接 400 拒收 (符合 ``parallel-session-stash-wipes`` 约束)。
    """
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail={"message": "URL 必须以 http:// 或 https:// 开头"},
        )

    # SSRF 防护: 协议 + 主机 + IP 全链路校验
    try:
        validate_url(url)
    except UrlSafetyError as e:
        logger.warning(f"custom_source ssrf_block: url={url[:80]} reason={e}")
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "ssrf_block",
                "message": (
                    f"URL 命中 SSRF 黑名单 (拒绝 localhost / 环回 / 私网 / "
                    f"保留 IP): {str(e)[:200]}"
                ),
            },
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
