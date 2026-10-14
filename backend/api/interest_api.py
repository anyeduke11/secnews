"""Interest Engine API — 行为信号 / 域权重 / 关注域 AI 推荐 (DEV-0182, gate: interest_engine).

端点
----
- ``POST /api/interest/signals``  记录行为信号 (item_id + signal_type; 域归因服务端做)
- ``DELETE /api/interest/reactions/{item_id}``  取消单 item 赞/踩 (DEV-0311, 删信号行)
- ``GET  /api/interest/reactions``  最近窗口 reaction 状态表 {item_id: like|dislike} (UI 回读)
- ``GET  /api/interest/weights``  10 域三层分 + 近 30d 事件数 (权重条数据源)
- ``POST /api/interest/reset``    清行为信号 (显式勾选保留) + audit_log
- ``GET  /api/interest/domains/recommendations``  关注域 AI 推荐 (density T3;
  ``?force=1`` 刷新缓存; 失败 200 + 空列表 + note; 采纳走既有
  ``PATCH /api/settings/interests``, 不新做写入端点 — 推荐不自动生效)
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.services.interest_engine_service import SIGNAL_TTL_DAYS, InterestEngineService

router = APIRouter(prefix="/api/interest", tags=["interest"])
_service = InterestEngineService()

_AUDIT_ACTION = "workbench.interest_reset"


class InterestSignalRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=200, description="hotspot id")
    signal_type: str = Field(
        ..., description="view|read|dwell|deep_read|favorite|like|dislike (reaction 走互斥/可取消语义)"
    )


class InterestResetRequest(BaseModel):
    actor: str = Field("web")


@router.post("/signals")
async def record_signal(req: InterestSignalRequest) -> dict:
    """记录行为信号; 无域非 reaction 条目返 202 accepted_no_domain (记录丢弃但不算错误)。

    DEV-0326: reaction (like/dislike) 无域时放行 (存哨兵域 weight 0) → 返回
    {"status": "ok", "domain": None}, 前端不再回滚; 累计型信号无域仍走 accepted_no_domain。
    """
    result = _service.record_signal(req.item_id, req.signal_type)
    status = result.get("status", "error")
    if status in ("no_domain",):
        return {"status": "accepted_no_domain", "domain": None}
    if status in ("error", "invalid_type", "invalid_item"):
        from backend.exceptions import InvalidParamException

        raise InvalidParamException(f"interest signal rejected: {status}")
    return {"status": "ok", "domain": result.get("domain")}


@router.delete("/reactions/{item_id}")
async def clear_reaction(item_id: str) -> dict:
    """取消单 item 赞/踩 (DEV-0311 状态型 reaction)。删除信号行, 无新插入。

    to_thread: 同步 SQL 不进 event loop (DEV-0304/R17 同类教训)。
    """
    result = await asyncio.to_thread(_service.clear_reaction, item_id)
    if result.get("status") == "invalid_item":
        from backend.exceptions import InvalidParamException

        raise InvalidParamException("interest reaction rejected: invalid_item")
    return result


@router.get("/reactions")
async def list_reactions(
    days: int = Query(SIGNAL_TTL_DAYS, ge=1, le=365, description="回读窗口 (默认 90 天, 与信号 TTL 对齐)"),
) -> dict:
    """reaction 状态表 {item_id: 'like'|'dislike'} (前端初始化回读, DEV-0311)。"""
    items = await asyncio.to_thread(_service.reactions_map, days=days)
    return {"items": items, "count": len(items)}


@router.get("/weights")
async def get_weights() -> dict:
    """10 域三层分 (explicit/behavioral/blended) + 近 30d 事件数 + R2 漂移检测。"""
    agg = _service.aggregate()
    drift = _service.detect_drift()
    return {
        "weights": agg,
        "domains": sorted(agg.keys()),
        "drift": drift,
    }


@router.post("/reset")
async def reset_weights(req: InterestResetRequest) -> dict:
    """清行为信号 + 行为分归零 (显式勾选保留) + audit_log。"""
    deleted = _service.reset()
    # DEV-0316: 信号清空 → 自动推导的内容偏好随之失效 (下次读重算 = {})
    from backend.services.hotspot_service import invalidate_auto_content_preferences

    invalidate_auto_content_preferences()
    try:
        from backend.observability_records import record_audit

        record_audit(
            actor=req.actor,
            action=_AUDIT_ACTION,
            target="interest.behavioral_signals",
            detail={"deleted_signals": deleted},
        )
    except Exception as e:
        logger.warning(f"interest reset audit failed (reset succeeded): {e}")
    logger.info(f"interest behavioral signals reset: deleted={deleted} (actor={req.actor})")
    return {"status": "ok", "deleted_signals": deleted}


@router.get("/domains/recommendations")
async def get_domain_recommendations(force: int = 0) -> dict:
    """关注域 AI 推荐 (density T3, 设计稿 §4.2) — 只读展示, 不自动生效。

    R3: 只调 advisor service; 缓存/LLM/枚举校验/兜底全在 service 层。
    """
    from backend.services.interest_domain_advisor import get_recommendations

    return await get_recommendations(force=bool(force))


@router.get("/content-prefs/recommendations")
async def get_content_pref_recommendations(force: int = 0) -> dict:
    """内容偏好 AI 优化建议 (DEV-0316) — 只读展示, 采纳走
    ``PATCH /api/settings/content-preferences`` (与域推荐同范式, 不自动生效)。
    """
    from backend.services.content_pref_advisor import get_suggestions

    return await get_suggestions(force=bool(force))
