"""quality_rules_dry_run_api.py — 自定义规则 dry-run 预览 (DEV-0287 D5 拆分)。

R3 行数守卫: quality_rules_api.py 170>150 (DEV-0280 新文件即超限) — 拆出
``POST /api/quality/custom-rules/dry-run`` (专家三 gate 抽样预览, 语义 cap 5)。
URL/method 逐字不变 (同 prefix, 由 _registry 聚合挂载)。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.quality.custom_rules_gate import (
    ExpertFlagGate,
    ExpertRejectGate,
    SemanticRulesGate,
)
from backend.quality.pipeline import GateContext

router = APIRouter(prefix="/api/quality", tags=["quality"])


class DryRunRequest(BaseModel):
    limit: int = Field(20, ge=1, le=50)
    with_semantic: bool = False


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


__all__ = ["router"]
