"""v0.8 P1 info_filter — 独立资讯筛选门禁 API.

Endpoints
---------
- GET    /api/info-filter/rules         — 列出全部规则 (含 enabled=false)
- POST   /api/info-filter/rules         — 创建规则 (rule_type × match_kind × match_value)
- PATCH  /api/info-filter/rules/{id}    — 更新规则 (note/enabled/三要素任一)
- DELETE /api/info-filter/rules/{id}    — 删除规则
- POST   /api/info-filter/preview       — 预览: 给定 (category, source_name) 命中情况
- GET    /api/info-filter/gate          — 当前 feature gate 状态 (前端 fallback)

行为约定:
- 写操作后 invalidate_cache() 让下一次 evaluate 立即生效 (5s TTL 兜底)
- 校验失败返 400, 带 InfoFilterError 描述
- 规则不存在 (PATCH/DELETE) 返 404
- 该 router 受 is_extension_enabled("info_filter") 守卫, gate off → 404 不可达
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.repository.db import get_connection
from backend.services.info_filter_gate import (
    invalidate_cache,
)
from backend.services.info_filter_service import (
    InfoFilterError,
    create_rule,
    delete_rule,
    evaluate,
    list_rules,
    update_rule,
)

router = APIRouter(prefix="/api/info-filter", tags=["info-filter"])


# ---------- 请求/响应模型 ----------


class CreateRuleRequest(BaseModel):
    rule_type: str = Field(..., description="allow | deny")
    match_kind: str = Field(
        ..., description="category | source_name | source_id | tag"
    )
    match_value: str = Field(..., min_length=1, max_length=200)
    note: str = Field(default="", max_length=500)
    enabled: int = Field(default=1, ge=0, le=1)


class UpdateRuleRequest(BaseModel):
    rule_type: Optional[str] = None
    match_kind: Optional[str] = None
    match_value: Optional[str] = None
    note: Optional[str] = None
    enabled: Optional[int] = Field(default=None, ge=0, le=1)


class PreviewRequest(BaseModel):
    category: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    source_id: Optional[str] = None
    tag: Optional[str] = None


# ---------- 端点 ----------


@router.get("/rules")
def list_rules_endpoint(enabled_only: bool = False) -> dict:
    """列出全部规则. 默认含 disabled; ?enabled_only=true 只看启用."""
    conn = get_connection()
    rules = list_rules(conn, enabled_only=enabled_only)
    return {"rules": rules, "count": len(rules)}


@router.post("/rules", status_code=201)
def create_rule_endpoint(req: CreateRuleRequest) -> dict:
    """创建规则. 校验失败返 400."""
    conn = get_connection()
    try:
        new_id = create_rule(
            conn,
            rule_type=req.rule_type,
            match_kind=req.match_kind,
            match_value=req.match_value,
            note=req.note,
            enabled=req.enabled,
        )
    except InfoFilterError as e:
        raise HTTPException(status_code=400, detail=str(e))
    invalidate_cache()
    return {"id": new_id, "ok": True}


@router.patch("/rules/{rule_id}")
def update_rule_endpoint(rule_id: int, req: UpdateRuleRequest) -> dict:
    """更新规则 (PATCH 语义: 仅改传入字段)."""
    conn = get_connection()
    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        changed = update_rule(conn, rule_id, **payload)
    except InfoFilterError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    invalidate_cache()
    return {"id": rule_id, "changed": changed, "ok": True}


@router.delete("/rules/{rule_id}")
def delete_rule_endpoint(rule_id: int) -> dict:
    """删除规则. 不存在返 404."""
    conn = get_connection()
    try:
        changed = delete_rule(conn, rule_id)
    except InfoFilterError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not changed:
        raise HTTPException(status_code=404, detail=f"rule id={rule_id} not found")
    invalidate_cache()
    return {"id": rule_id, "ok": True}


@router.post("/preview")
def preview_endpoint(req: PreviewRequest) -> dict:
    """预览: 给定源/项 → 评估会命中什么规则.

    不依赖 DB 写, 只读现有规则 + 调 evaluate. 用于前端"如果现在启会怎样".
    """
    conn = get_connection()
    rules = list_rules(conn, enabled_only=True)
    verdict, matched = evaluate(
        rules,
        category=req.category,
        source_name=req.source_name,
        source_id=req.source_id,
        tag=req.tag,
    )
    return {
        "verdict": verdict,
        "matched_rule": matched,
    }


@router.get("/gate")
def gate_status_endpoint() -> dict:
    """前端用于检测 feature gate 状态 (dsh 模式: 404 → gateOff).

    本端点始终 200 (router 本身已被 gate 守卫); 返 is_enabled
    供前端双保险 (例如 API 在, 但用户手动关 TOML 后, 实时反映).
    """
    from backend.extensions import is_extension_enabled
    return {
        "extension": "info_filter",
        "is_enabled": is_extension_enabled("info_filter"),
    }


__all__ = ["router"]
