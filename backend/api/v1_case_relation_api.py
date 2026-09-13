"""v1.0 T08/C11 R19 Case API — 关联对象聚合查询.

拆自 ``backend/api/case_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``GET /api/v1/cases/{id}/aggregate`` — 单次拉齐 case + judgments + actions
  + runs + artifacts (+ v0.8.5 recall_candidates / reuse_summary), 避免前端 N+1。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.v1_case_common import _case_to_dict
from backend.services.case_service import CaseNotFoundError, CaseService
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/cases", tags=["v1-cases"])


def _aggregate(
    case_id: str,
    *,
    judgments_limit: int,
    actions_limit: int,
    runs_per_action: int,
    artifacts_per_run: int,
) -> dict[str, Any]:
    """C11 R19: Case 聚合查询, 避免前端 N+1.

    调用 1 次: case + judgments + actions + runs (per action) + artifacts (per run).
    旧实现 (前端): 1+1+1+N+N×M 个 HTTP 请求; 修复后: 1 个聚合端点.
    v0.8.5 证据/复利只读 SQL 在 v1_evidence_service / knowledge_service
    (Batch 2 D 下沉); 本函数只做聚合编排。
    """
    def _recall_candidates(case_dict: dict[str, Any]) -> list[dict[str, Any]]:
        """v0.8.5 D3 (SK-05 自动召回): 已发布知识 × case 文本匹配, 失败显空不阻断."""
        try:
            from backend.services.knowledge_service import auto_recall_for_case
            return auto_recall_for_case(case_dict)
        except Exception:
            return []

    from backend.services.action_service import ActionService
    from backend.services.artifact_service import ArtifactService
    from backend.services.judgment_service import JudgmentService
    from backend.services.knowledge_service import KnowledgeService
    from backend.services.run_service import RunService
    from backend.services.v1_evidence_service import V1EvidenceService

    c_svc = CaseService()
    try:
        case = c_svc.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )

    j_svc = JudgmentService()
    judgments_resp = j_svc.list_by_case(case_id, limit=judgments_limit, offset=0)
    judgments = judgments_resp.get("items", []) if isinstance(judgments_resp, dict) else list(judgments_resp)

    a_svc = ActionService(dsh_caller=lambda _p: "{}")
    actions_resp = a_svc.list_by_case(case_id, limit=actions_limit, offset=0)
    actions = actions_resp.get("items", []) if isinstance(actions_resp, dict) else list(actions_resp)

    r_svc = RunService()
    art_svc = ArtifactService()
    runs: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for a in actions:
        a_id = a.get("id") if isinstance(a, dict) else getattr(a, "id", None)
        if not a_id:
            continue
        try:
            run_resp = r_svc.list_by_action(a_id, limit=runs_per_action, offset=0)
            run_items = run_resp.get("items", []) if isinstance(run_resp, dict) else list(run_resp)
        except Exception:
            run_items = []
        runs.extend(run_items)
        for r in run_items:
            r_id = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
            if not r_id:
                continue
            try:
                art_resp = art_svc.list_by_run(r_id, limit=artifacts_per_run, offset=0)
                art_items = art_resp.get("items", []) if isinstance(art_resp, dict) else list(art_resp)
            except Exception:
                art_items = []
            artifacts.extend(art_items)

    return {
        "version": API_VERSION,
        "case": _case_to_dict(case),
        "evidence_materials": V1EvidenceService().case_evidence_materials(case_id),
        # v0.8.5 D3 (SK-05 自动召回): 已发布知识按 case 文本自动匹配, Case 页浮现候选
        "recall_candidates": _recall_candidates(_case_to_dict(case)),
        # v0.8.5 D4: 复利卡 (诚实计数)
        "reuse_summary": KnowledgeService().case_reuse_summary(case_id),
        "judgments": [j for j in judgments if isinstance(j, dict)] if judgments and isinstance(judgments[0], dict) else [
            j.to_dict() if hasattr(j, "to_dict") else j for j in judgments
        ],
        "actions": [a for a in actions if isinstance(a, dict)] if actions and isinstance(actions[0], dict) else [
            a.to_dict() if hasattr(a, "to_dict") else a for a in actions
        ],
        "runs": [r for r in runs if isinstance(r, dict)] if runs and isinstance(runs[0], dict) else [
            r.to_dict() if hasattr(r, "to_dict") else r for r in runs
        ],
        "artifacts": [a for a in artifacts if isinstance(a, dict)] if artifacts and isinstance(artifacts[0], dict) else [
            a.to_dict() if hasattr(a, "to_dict") else a for a in artifacts
        ],
    }


@router.get("/{case_id}/aggregate")
async def get_case_aggregate_endpoint(
    case_id: str,
    judgments_limit: int = Query(default=50, ge=1, le=200),
    actions_limit: int = Query(default=50, ge=1, le=200),
    runs_per_action: int = Query(default=10, ge=1, le=50),
    artifacts_per_run: int = Query(default=10, ge=1, le=50),
):
    """C11 R19: Case 聚合查询, 1 次拉齐 5 类对象, 避免前端 N+1."""
    return await asyncio.to_thread(
        _aggregate, case_id,
        judgments_limit=judgments_limit, actions_limit=actions_limit,
        runs_per_action=runs_per_action, artifacts_per_run=artifacts_per_run,
    )
