"""quality_rules_api.py — /api/quality/custom-rules: 两层质量规则管理面 (v0.8.6 P2)。

- GET    /api/quality/custom-rules?kind=       规则列表 (rule_kind 过滤)
- POST   /api/quality/custom-rules             新建 (expert: 5 matcher / semantic: nl)
- PUT    /api/quality/custom-rules/{rule_id}   更新 (白名单字段)
- DELETE /api/quality/custom-rules/{rule_id}   删除
- GET    /api/quality/custom-rules/gates       全量 gate 清单 (name/tier/enabled)
- POST   /api/quality/custom-rules/dry-run     命中预览 (专家确定性; 语义 LLM cap 5)

DB 直连 QualityCustomRulesRepository (P1-5 quality_api 同模式: quality 域
薄路由 + 单写者 repo); gate 执行面在 backend/quality/custom_rules_gate.py。
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.quality.custom_rules_gate import (
    gate_enabled,
)
from backend.quality.pipeline import QualityGatePipeline
from backend.repository.quality_custom_rules_repo import (
    ACTIONS,
    MATCH_KINDS_EXPERT,
    QualityCustomRulesRepository,
)

router = APIRouter(prefix="/api/quality", tags=["quality"])

_repo = QualityCustomRulesRepository()


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rule_kind: Literal["expert", "semantic"]
    match_kind: str
    match_value: str = Field(min_length=1)
    action: Literal["flag", "reject"] = "flag"
    deduction: int = Field(10, ge=0, le=100)
    scope_category: str = ""
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    match_kind: str | None = None
    match_value: str | None = None
    action: Literal["flag", "reject"] | None = None
    deduction: int | None = Field(None, ge=0, le=100)
    scope_category: str | None = None
    enabled: bool | None = None


@router.get("/custom-rules")
def list_rules(
    kind: str | None = Query(None, pattern="^(expert|semantic)$"),
) -> dict[str, Any]:
    return {"rules": _repo.list_rules(kind=kind)}


@router.post("/custom-rules")
def create_rule(payload: RuleCreate) -> dict[str, Any]:
    if payload.rule_kind == "semantic":
        match_kind, action = "nl", "flag"  # 语义规则仅软扣分
    else:
        if payload.match_kind not in MATCH_KINDS_EXPERT:
            raise HTTPException(
                422, f"expert match_kind 须为 {list(MATCH_KINDS_EXPERT)}")
        match_kind, action = payload.match_kind, payload.action
    if action not in ACTIONS:
        raise HTTPException(422, f"action 须为 {list(ACTIONS)}")
    return _repo.create(
        name=payload.name, rule_kind=payload.rule_kind,
        match_kind=match_kind, match_value=payload.match_value,
        action=action, deduction=payload.deduction,
        scope_category=payload.scope_category.strip(), enabled=payload.enabled,
    )


@router.get("/custom-rules/gates")
def list_gates() -> dict[str, Any]:
    return {"gates": [
        {"name": g.name, "tier": g.gate_type, "enabled": gate_enabled(g.name)}
        for g in QualityGatePipeline.DEFAULT_GATES
    ]}



# ---------------------------------------------------------------------------
# POST /custom-rules/dry-run
# DEV-0287 (D5): 170>150 拆出 → quality_rules_dry_run_api.py (同 prefix 聚合挂载, URL 零变更)

@router.put("/custom-rules/{rule_id}")
def update_rule(rule_id: int, payload: RuleUpdate) -> dict[str, Any]:
    if payload.match_kind is not None and payload.match_kind not in (
            *MATCH_KINDS_EXPERT, "nl"):
        raise HTTPException(
            422, f"match_kind 须为 {[*MATCH_KINDS_EXPERT, 'nl']}")
    fields = payload.model_dump(exclude_none=True)
    updated = _repo.update(rule_id, fields)
    if updated is None:
        raise HTTPException(404, f"rule {rule_id} not found")
    return updated


@router.delete("/custom-rules/{rule_id}")
def delete_rule(rule_id: int) -> dict[str, Any]:
    deleted = _repo.delete(rule_id)
    if not deleted:
        raise HTTPException(404, f"rule {rule_id} not found")
    return {"deleted": rule_id}


__all__ = ["router"]
