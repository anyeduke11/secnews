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

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.quality.base import GateContext
from backend.quality.custom_rules_gate import (
    ExpertFlagGate,
    ExpertRejectGate,
    SemanticRulesGate,
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


class DryRunRequest(BaseModel):
    limit: int = Field(20, ge=1, le=50)
    with_semantic: bool = False


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


def _dry_run_impl(limit: int, with_semantic: bool) -> dict[str, Any]:
    from backend.domain.enums import TimeRange
    from backend.repository.hotspot_repo import HotspotRepository

    items, _ = HotspotRepository().query(
        category=None, time_range=TimeRange.D7, limit=limit)
    ctx = GateContext(mode="loose")
    reject_hits: list[dict[str, Any]] = []
    flag_hits: list[dict[str, Any]] = []
    semantic_hits: list[dict[str, Any]] = []
    semantic_notes: list[str] = []
    semantic_cap = 5 if with_semantic else 0
    for item in items:
        base = {"item_id": item.id, "title": item.title, "source": item.source}
        r = ExpertRejectGate().check(item, ctx)
        if not r.passed:
            reject_hits.append({**base, "flags": r.flags,
                                "deduction": r.score_deduction, "reason": r.reason})
        f = ExpertFlagGate().check(item, ctx)
        if not f.passed:
            flag_hits.append({**base, "flags": f.flags,
                              "deduction": f.score_deduction, "reason": f.reason})
        used = int(getattr(ctx, "semantic_llm_calls", 0))
        if with_semantic and used < semantic_cap:
            s = SemanticRulesGate().check(item, ctx)
            if not s.passed:
                semantic_hits.append({**base, "flags": s.flags,
                                      "deduction": s.score_deduction,
                                      "reason": s.reason})
            elif s.flags:  # unavailable / budget_exhausted 可见不扣分
                semantic_notes.append(f"{item.id}: {';'.join(s.flags)}")
    ran = int(getattr(ctx, "semantic_llm_calls", 0))
    return {
        "sampled": len(items),
        "expert": {"reject_hits": reject_hits, "flag_hits": flag_hits},
        "semantic": {
            "ran": ran, "cap": semantic_cap,
            "skipped": max(0, len(items) - ran),
            "hits": semantic_hits, "notes": semantic_notes,
        },
    }


@router.post("/custom-rules/dry-run")
async def dry_run(payload: DryRunRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        _dry_run_impl, payload.limit, payload.with_semantic)


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
