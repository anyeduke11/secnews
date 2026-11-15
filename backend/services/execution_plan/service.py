"""ExecutionPlan 服务 — submit (草稿) / approve (冻结) / reject 状态机 (L1 计划层)。

状态机: draft → approved | rejected (rejected 后可重新 submit 覆盖 — P10 §4
"plan 存 run 行内不加表", 历史经 audit_log boundary_hash 留痕)。
不变量:
  - approved 信封 immutable (再 submit → 409; 改 plan = 新 run attempt);
  - boundary_hash = plan 载荷的 sha256 (envelope 内 plan 被篡改即可检出);
  - 只允许 queued/claimed 的 run 变更计划 (running/terminal → 409)。
审计: submit/approve/reject 全落 audit_log (actor=web)。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.observability_records import record_audit
from backend.repository.run_repo import RunRepository
from backend.services.execution_plan.schema import ExecutionPlan

_PLAN_ACTIVE_STATUSES = ("queued", "claimed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def boundary_hash(plan: ExecutionPlan | dict[str, Any]) -> str:
    """plan 载荷指纹 (sha256, canonical json) — L4 逐条比对的完整性依据。"""
    payload = plan.model_dump() if isinstance(plan, ExecutionPlan) else plan
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class ExecutionPlanValidationError(InvalidParamException):
    def __init__(self, message: str = "execution plan validation failed") -> None:
        super().__init__(message)


class ExecutionPlanConflictError(ConflictException):
    def __init__(self, message: str = "execution plan state conflict") -> None:
        super().__init__(message)


class ExecutionPlanNotFoundError(NotFoundException):
    def __init__(self, message: str = "execution plan not found") -> None:
        super().__init__(message)


class ExecutionPlanService:
    """ExecutionPlan 状态机 — submit/approve/reject/get (L1 计划层)。"""

    def __init__(self, repo: RunRepository | None = None) -> None:
        self.repo = repo or RunRepository()

    # ------------------------------------------------------------------
    def _load_run(self, run_id: str) -> dict[str, Any]:
        r = self.repo.get(run_id)
        if r is None:
            raise NotFoundException(f"run {run_id} not found")
        if r["status"] not in _PLAN_ACTIVE_STATUSES:
            raise ExecutionPlanConflictError(
                f"run {run_id} status={r['status']}; "
                f"plan 只允许在 queued/claimed 阶段变更 (L1: 执行期不可改边界)")
        return r

    def _audit(self, action: str, run_id: str, detail: dict[str, Any]) -> None:
        record_audit("web", f"plan.{action}", target=f"run:{run_id}", detail=detail)

    # ------------------------------------------------------------------
    def submit(
        self, run_id: str, plan_payload: dict[str, Any], *,
        submitted_by: str, source: str = "manual",
    ) -> dict[str, Any]:
        """提交 plan 草稿 (人工手写表单或 ai_draft — 两者同为建议, 未审批不执行)。"""
        r = self._load_run(run_id)
        existing = r.get("execution_plan") or {}
        if existing.get("status") == "approved":
            raise ExecutionPlanConflictError(
                f"run {run_id} 已有 approved plan (boundary_hash={r.get('boundary_hash', '')[:16]}…); "
                "immutable — 改 plan 请拒绝后重提或新开 run attempt")
        try:
            plan = ExecutionPlan.model_validate(plan_payload)
        except ValidationError as e:
            raise ExecutionPlanValidationError(
                f"execution plan schema 校验失败: {e.errors()[:3]}") from e
        envelope = {
            "plan": plan.model_dump(),
            "status": "draft",
            "submitted_by": submitted_by,
            "source": source,
            "submitted_at": _now_iso(),
            "approved_by": None,
            "approved_at": None,
            "reject_reason": None,
        }
        bh = boundary_hash(plan)
        self.repo.set_execution_plan(run_id, envelope, bh)
        self._audit("submit", run_id, {
            "boundary_hash": bh, "source": source,
            "commands": len(plan.commands),
        })
        return self.get(run_id)

    def approve(self, run_id: str, *, reviewed_by: str) -> dict[str, Any]:
        """draft → approved (冻结; 默认拒绝语义的反面 = 显式放行, 落审计)。"""
        r = self._load_run(run_id)
        envelope = r.get("execution_plan") or {}
        if not envelope:
            raise ExecutionPlanNotFoundError(
                f"run {run_id} 无 plan 草稿; 先经 POST /plan 提交")
        if envelope.get("status") != "draft":
            raise ExecutionPlanConflictError(
                f"run {run_id} plan status={envelope.get('status')} (approve requires draft)")
        # L4 完整性: 冻结前重验 plan 内容与 boundary_hash 一致 (防落库后被改)
        if boundary_hash(envelope["plan"]) != r.get("boundary_hash"):
            raise ExecutionPlanConflictError(
                f"run {run_id} plan 内容与 boundary_hash 不符 (落库后被篡改?)")
        envelope["status"] = "approved"
        envelope["approved_by"] = reviewed_by
        envelope["approved_at"] = _now_iso()
        self.repo.set_execution_plan(run_id, envelope, r.get("boundary_hash"))
        self._audit("approve", run_id, {
            "boundary_hash": r.get("boundary_hash"), "reviewed_by": reviewed_by,
        })
        return self.get(run_id)

    def reject(self, run_id: str, *, reviewed_by: str, reason: str) -> dict[str, Any]:
        """draft → rejected (reason 必填 ≤200; 默认拒绝语义的显式表达)。"""
        if not (reason or "").strip():
            raise ExecutionPlanValidationError("reject requires reason (≤200 字)")
        r = self._load_run(run_id)
        envelope = r.get("execution_plan") or {}
        if not envelope:
            raise ExecutionPlanNotFoundError(f"run {run_id} 无 plan 草稿")
        if envelope.get("status") != "draft":
            raise ExecutionPlanConflictError(
                f"run {run_id} plan status={envelope.get('status')} (reject requires draft)")
        envelope["status"] = "rejected"
        envelope["reject_reason"] = str(reason)[:200]
        envelope["approved_by"] = reviewed_by
        self.repo.set_execution_plan(run_id, envelope, r.get("boundary_hash"))
        self._audit("reject", run_id, {
            "boundary_hash": r.get("boundary_hash"), "reviewed_by": reviewed_by,
            "reason": str(reason)[:200],
        })
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        """读 run 的 plan 信封 (无则 404 — 前端空态依据)。"""
        r = self.repo.get(run_id)
        if r is None:
            raise NotFoundException(f"run {run_id} not found")
        envelope = r.get("execution_plan") or {}
        if not envelope:
            raise ExecutionPlanNotFoundError(f"run {run_id} 无 execution plan")
        return {
            **envelope,
            "boundary_hash": r.get("boundary_hash"),
            "executor": r.get("executor"),
        }
