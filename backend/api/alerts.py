"""v1.7 Phase 3 — Alerts REST API.

端点:
- GET    /api/alerts/rules             规则列表
- POST   /api/alerts/rules             新建规则
- GET    /api/alerts/rules/{id}        查看规则
- PUT    /api/alerts/rules/{id}        更新规则
- DELETE /api/alerts/rules/{id}        删除规则
- GET    /api/alerts                   告警列表 (?status=&rule_id=)
- GET    /api/alerts/{id}              查看告警
- PUT    /api/alerts/{id}/read         标记已读
- PUT    /api/alerts/{id}/dismiss      忽略告警 (status=dismissed)
- DELETE /api/alerts/{id}              删除告警
- POST   /api/alerts/evaluate/{hotspot_id}  手动触发热点评估
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.alerts_repo import AlertRepository, AlertRuleRepository
from backend.services.alert_service import evaluate_hotspot

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    condition: dict
    action: dict = Field(default_factory=dict)
    cooldown_sec: int = Field(3600, ge=0, le=86400 * 7)
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    condition: Optional[dict] = None
    action: Optional[dict] = None
    cooldown_sec: Optional[int] = Field(None, ge=0, le=86400 * 7)
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# 规则 CRUD
# ---------------------------------------------------------------------------
@router.get("/rules")
async def list_rules(enabled_only: bool = Query(False)):
    items = await asyncio.to_thread(AlertRuleRepository().list, enabled_only)
    return {"version": "1.7.0", "count": len(items), "items": items}


@router.post("/rules", status_code=201)
async def create_rule(req: RuleCreate):
    rid = f"rule-{uuid4().hex[:12]}"
    item = await asyncio.to_thread(
        AlertRuleRepository().add,
        rid, req.name, req.condition, req.action, req.cooldown_sec, req.enabled,
    )
    return {"version": "1.7.0", "item": item}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str):
    item = await asyncio.to_thread(AlertRuleRepository().get, rule_id)
    if not item:
        raise HTTPException(status_code=404, detail={"message": f"规则不存在: {rule_id}"})
    return {"version": "1.7.0", "item": item}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, req: RuleUpdate):
    item = await asyncio.to_thread(
        AlertRuleRepository().update,
        rule_id, req.name, req.condition, req.action, req.cooldown_sec, req.enabled,
    )
    if not item:
        raise HTTPException(status_code=404, detail={"message": f"规则不存在: {rule_id}"})
    return {"version": "1.7.0", "item": item}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    n = await asyncio.to_thread(AlertRuleRepository().delete, rule_id)
    if not n:
        raise HTTPException(status_code=404, detail={"message": f"规则不存在: {rule_id}"})
    return {"version": "1.7.0", "deleted": n}


# ---------------------------------------------------------------------------
# 告警 CRUD
# ---------------------------------------------------------------------------
@router.get("")
async def list_alerts(
    status: Optional[str] = Query(None),
    rule_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    items = await asyncio.to_thread(
        AlertRepository().list, status, rule_id, limit
    )
    return {"version": "1.7.0", "count": len(items), "items": items}


@router.get("/{alert_id}")
async def get_alert(alert_id: str):
    item = await asyncio.to_thread(AlertRepository().get, alert_id)
    if not item:
        raise HTTPException(status_code=404, detail={"message": f"告警不存在: {alert_id}"})
    return {"version": "1.7.0", "item": item}


@router.put("/{alert_id}/read")
async def mark_read(alert_id: str):
    item = await asyncio.to_thread(AlertRepository().mark_read, alert_id)
    if not item:
        raise HTTPException(status_code=404, detail={"message": f"告警不存在: {alert_id}"})
    return {"version": "1.7.0", "item": item, "status": "ok"}


@router.put("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    item = await asyncio.to_thread(
        AlertRepository().mark_processed, alert_id, "dismissed"
    )
    if not item:
        raise HTTPException(status_code=404, detail={"message": f"告警不存在: {alert_id}"})
    return {"version": "1.7.0", "item": item, "status": "ok"}


@router.delete("/{alert_id}")
async def delete_alert(alert_id: str):
    n = await asyncio.to_thread(AlertRepository().delete, alert_id)
    if not n:
        raise HTTPException(status_code=404, detail={"message": f"告警不存在: {alert_id}"})
    return {"version": "1.7.0", "deleted": n}


# ---------------------------------------------------------------------------
# 手动触发评估
# ---------------------------------------------------------------------------
@router.post("/evaluate/{hotspot_id}")
async def evaluate(hotspot_id: str):
    """手动触发对某热点的规则评估 (验收 1: 60s 内匹配触发)."""
    fired = await asyncio.to_thread(evaluate_hotspot, hotspot_id)
    return {"version": "1.7.0", "hotspot_id": hotspot_id, "fired_rules": fired}


__all__ = ["router"]
