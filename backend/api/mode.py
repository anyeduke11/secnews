"""v1.7 Phase 3 — 模式切换 API.

PRD §3.2.10 / §4.2 Phase 3: 每日首次打开返回 brief 模式 (有未读简报时),
用户切换后记录状态。

端点
----
- ``GET /api/mode/current`` — 返回当前推荐模式 (brief / scan)
- ``PUT /api/mode/switch?mode=...`` — 用户主动切换模式, 标记简报已读

模式集合 (PRD §4.2):
- ``brief``: 简报模式 (每日首次, 有未读简报)
- ``scan``: 扫读模式 (默认)
- ``deep``: 深读模式
- ``organize``: 整理模式
- ``review``: 复习模式 (SM-2)
- ``alert``: 告警模式
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.services.digest_service import has_unread_digest, mark_digest_read

router = APIRouter(prefix="/api/mode", tags=["mode"])

# PRD §4.2 定义的 6 种模式
_MODES = {"brief", "scan", "deep", "organize", "review", "alert"}


@router.get("/current")
async def current_mode():
    """返回当前推荐模式。

    逻辑:
    - 如果有未读简报 → ``brief`` (每日首次打开)
    - 否则 → ``scan`` (默认扫读)

    Returns
    -------
    dict
        ``{"version": "1.7.0", "mode": "brief" | "scan"}``
    """
    mode = "brief" if has_unread_digest() else "scan"
    return {"version": "1.7.0", "mode": mode}


@router.put("/switch")
async def switch_mode(mode: str = Query(..., description="目标模式")):
    """用户主动切换模式。

    切换时自动标记简报已读 (后续 ``GET /current`` 返回 ``scan``)。

    Parameters
    ----------
    mode:
        目标模式, 必须在 ``_MODES`` 中。

    Returns
    -------
    dict
        ``{"version": "1.7.0", "mode": "<mode>"}``
    """
    if mode not in _MODES:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"invalid mode: {mode}",
                "valid_modes": sorted(_MODES),
            },
        )

    # 切换模式时标记简报已读, 避免 /current 持续返回 brief
    mark_digest_read()

    return {"version": "1.7.0", "mode": mode}


@router.get("/modes")
async def list_modes():
    """返回所有可用模式列表 (供前端渲染模式选择器)。"""
    return {"version": "1.7.0", "modes": sorted(_MODES)}
