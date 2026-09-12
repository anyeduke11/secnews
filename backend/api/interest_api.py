"""Interest Engine API — 行为信号 / 域权重 (DEV-0182, gate: interest_engine).

端点
----
- ``POST /api/interest/signals``  记录行为信号 (item_id + signal_type; 域归因服务端做)
- ``GET  /api/interest/weights``  10 域三层分 + 近 30d 事件数 (权重条数据源)
- ``POST /api/interest/reset``    清行为信号 (显式勾选保留) + audit_log
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.services.interest_engine_service import InterestEngineService

router = APIRouter(prefix="/api/interest", tags=["interest"])
_service = InterestEngineService()

_AUDIT_ACTION = "workbench.interest_reset"


class InterestSignalRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=200, description="hotspot id")
    signal_type: str = Field(..., description="view|read|dwell|deep_read|favorite")


class InterestResetRequest(BaseModel):
    actor: str = Field("web")


@router.post("/signals")
async def record_signal(req: InterestSignalRequest) -> dict:
    """记录行为信号; 无域条目返 202 accepted_no_domain (记录丢弃但不算错误)。"""
    result = _service.record_signal(req.item_id, req.signal_type)
    status = result.get("status", "error")
    if status in ("no_domain",):
        return {"status": "accepted_no_domain", "domain": None}
    if status in ("error", "invalid_type", "invalid_item"):
        from backend.exceptions import InvalidParamException

        raise InvalidParamException(f"interest signal rejected: {status}")
    return {"status": "ok", "domain": result.get("domain")}


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
