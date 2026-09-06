"""v1.0 T12 ActionService — Action 7 态机 + plan_hash 不变量 + 启动→Run 桥接.

对应 contracts.md §6 (Action) + §10.1 (judgment 引用校验) + EXECUTION_GUIDE §T12.

状态机 (7 态):
  planned → approve → approved → start → running → finish → succeeded
                              ↓ fail             ↑ fail
                            failed ←──────────────┘ (retry 仅同 plan_hash)
                            cancelled / rejected
"""
from __future__ import annotations

import hashlib
import random
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.action_repo import ActionRepository
from backend.repository.db import get_connection
from backend.repository.judgment_repo import JudgmentRepository


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------
class ActionValidationError(InvalidParamException):
    def __init__(self, message: str = "action validation failed") -> None:
        super().__init__(message)


class ActionNotFoundError(NotFoundException):
    def __init__(self, message: str = "action not found") -> None:
        super().__init__(message)


class ActionConflictError(ConflictException):
    def __init__(self, message: str = "action state conflict") -> None:
        super().__init__(message)


# 状态机 + allowed_actions (contracts §6.3)
_ACTION_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "planned": ["approve", "reject", "edit", "cancel"],
    "approved": ["start", "edit", "cancel", "revise_to_planned"],
    "running": ["cancel"],
    "succeeded": ["view_only", "create_followup"],
    "failed": ["retry", "revise", "cancel"],
    "cancelled": ["view_only", "create_followup"],
    "rejected": ["view_only"],
}

_PLAN_MAX_BYTES = 50_000
_TITLE_MAX_BYTES = 200
_SUCCESS_CRITERIA_MAX_BYTES = 500
_VALID_ACTION_STATUS = set(_ACTION_ALLOWED_ACTIONS.keys())


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ulid26() -> str:
    """26 字符 ULID (random.choice, 不用确定性避免 UNIQUE 撞库 — T11 fix)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _plan_hash(plan: str) -> str:
    """contracts §6.4: plan_hash = sha256(plan); plan 改 = hash 改 = 必走 revise → reject → 重建."""
    return hashlib.sha256(plan.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ActionService
# ---------------------------------------------------------------------------
class ActionService:
    """Action 服务 — 校验链 + 7 态机 + 启动→Run 桥接 + plan_hash 不变量."""

    def __init__(
        self, repo: ActionRepository | None = None,
        judgment_repo: JudgmentRepository | None = None,
        run_service: Any = None,  # RunService (避免循环 import; 注入供单测)
        *, dsh_caller: Any = None,
    ) -> None:
        self.repo = repo or ActionRepository()
        self.judgment_repo = judgment_repo or JudgmentRepository()
        self._run_service = run_service
        self._dsh_caller = dsh_caller

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def _validate_create_payload(
        self, *, case_id: str, judgment_id: str, title: str, plan: str,
        success_criteria: str | None, expected_artifacts: list[str],
    ) -> None:
        if not case_id or not isinstance(case_id, str):
            raise ActionValidationError("case_id required")
        if not judgment_id or not isinstance(judgment_id, str):
            raise ActionValidationError("judgment_id required")
        if not title or not title.strip():
            raise ActionValidationError("title must be non-empty")
        if len(title.encode("utf-8")) > _TITLE_MAX_BYTES:
            raise ActionValidationError(f"title exceeds {_TITLE_MAX_BYTES} bytes")
        if not plan or not plan.strip():
            raise ActionValidationError("plan must be non-empty")
        if len(plan.encode("utf-8")) > _PLAN_MAX_BYTES:
            raise ActionValidationError(f"plan exceeds {_PLAN_MAX_BYTES} bytes")
        if success_criteria is not None and len(success_criteria.encode("utf-8")) > _SUCCESS_CRITERIA_MAX_BYTES:
            raise ActionValidationError(f"success_criteria exceeds {_SUCCESS_CRITERIA_MAX_BYTES} bytes")
        if not isinstance(expected_artifacts, list) or len(expected_artifacts) == 0:
            raise ActionValidationError("expected_artifacts must be non-empty list")

    def _require_published_judgment(self, judgment_id: str) -> None:
        """contracts §10.1: action.judgment_id 必引 published judgment."""
        j = self.judgment_repo.get(judgment_id)
        if j is None:
            raise ActionValidationError(f"judgment {judgment_id} not found")
        if j.get("status") != "published":
            raise ActionValidationError(
                f"action.judgment_id={judgment_id} must reference published judgment "
                f"(current status={j.get('status')})"
            )

    # ------------------------------------------------------------------
    # create_with_dsh (T12 SK-03 主路径)
    # ------------------------------------------------------------------
    def create_with_dsh(
        self,
        *,
        case_id: str,
        judgment_id: str,
        title: str,
        subject_name: str,
        cve_id: str,
        scope: str,
        evidence_materials: list[dict[str, Any]],
        submitted_by: str = "user",
    ) -> dict[str, Any]:
        """通过 dsh (或 mock) 生成 inspection-materials plan, 落库成 planned action.

        Returns
        -------
        {"action": <dict>, "idempotent_replay": bool}
        """
        # 1) 校验 judgment_id 已 published (contracts §10.1)
        self._require_published_judgment(judgment_id)
        # 2) 调 dsh
        from backend.services.ai_hub.prompts import (
            build_inspection_materials_prompt,
            parse_inspection_materials_response,
        )
        prompt = build_inspection_materials_prompt(
            case_id=case_id, judgment_id=judgment_id, subject_name=subject_name,
            cve_id=cve_id, scope=scope, evidence_materials=evidence_materials,
        )
        raw = self._call_dsh(prompt)
        try:
            parsed = parse_inspection_materials_response(raw)
        except ValueError as e:
            raise ActionValidationError(f"dsh response parse failed: {e}") from e
        # 3) 校验
        self._validate_create_payload(
            case_id=case_id, judgment_id=judgment_id, title=title, plan=parsed["plan"],
            success_criteria=parsed.get("success_criteria"),
            expected_artifacts=parsed["expected_artifacts"],
        )
        # 4) 落库
        return self._insert_planned(
            case_id=case_id, judgment_id=judgment_id, title=title, scope=scope,
            plan=parsed["plan"], tool_versions=parsed["tool_versions"],
            expected_artifacts=parsed["expected_artifacts"],
            success_criteria=parsed["success_criteria"],
            unknowns=parsed["unknowns"], submitted_by=submitted_by,
        )

    def _call_dsh(self, prompt: str) -> str:
        """调 dsh (mock 注入优先, 默认走 ai_hub.generate_text)."""
        if self._dsh_caller is not None:
            return self._dsh_caller(prompt)
        try:
            from backend.services.ai_hub.service import ai_service
            return ai_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                task="inspection_materials", max_tokens=6000, temperature=0.2,
            )
        except Exception as e:
            raise ActionValidationError(f"ai_hub generate_text failed: {e}") from e

    def _insert_planned(
        self, *, case_id: str, judgment_id: str, title: str, scope: str | None,
        plan: str, tool_versions: dict[str, str], expected_artifacts: list[str],
        success_criteria: str, unknowns: list[str], submitted_by: str,
    ) -> dict[str, Any]:
        aid = _ulid26()
        now = _utcnow_iso()
        plan_h = _plan_hash(plan)
        body = {
            "id": aid,
            "case_id": case_id, "judgment_id": judgment_id, "title": title,
            "scope": scope, "plan": plan, "plan_hash": plan_h,
            "tool_versions": tool_versions, "expected_artifacts": expected_artifacts,
            "success_criteria": success_criteria, "expires_at": None,
            "status": "planned",
            "approved_by": None, "approved_at": None, "rejection_reason": None,
            "revision": 1, "created_at": now, "updated_at": now,
            "allowed_actions": _ACTION_ALLOWED_ACTIONS["planned"],
            "reason": None,
        }
        self.repo.insert(body)
        self.repo.link_to_case(case_id, aid)
        # 走 V1EvidenceService (best-effort, 同 T11)
        try:
            from backend.services.v1_evidence_service import V1EvidenceService
            evidence = V1EvidenceService()
            intent = evidence.create_intent(
                f"v1-action-{case_id}-{judgment_id}-{plan_h[:16]}",
                "action", body, submitted_by=submitted_by,
            )
            evidence.commit_intent(intent["intent_id"], entity_id=aid, projection=None)
        except Exception as e:
            logger.warning(f"V1EvidenceService trace failed (action still inserts): {e}")
        return {"action": body, "idempotent_replay": False}

    # ------------------------------------------------------------------
    # 状态机: approve / reject / start / cancel
    # ------------------------------------------------------------------
    def approve(self, action_id: str, *, expected_revision: int, approved_by: str) -> dict[str, Any]:
        a = self._require(action_id)
        if a["status"] != "planned":
            raise ActionConflictError(f"action {action_id} status={a['status']} (approve requires planned)")
        if a["revision"] != expected_revision:
            raise ActionConflictError(
                f"action {action_id} revision mismatch: expected={expected_revision}, actual={a['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            action_id, "approved", expected_revision=expected_revision,
            approved_by=approved_by, approved_at=_utcnow_iso(),
            allowed_actions=_ACTION_ALLOWED_ACTIONS["approved"], reason=None,
        )
        if rowcount == 0:
            raise ActionConflictError(f"action {action_id} CAS race")
        return self._require(action_id)

    def reject(
        self, action_id: str, *, expected_revision: int, reason: str, rejected_by: str,
    ) -> dict[str, Any]:
        a = self._require(action_id)
        if a["status"] not in ("planned", "approved"):
            raise ActionConflictError(f"action {action_id} status={a['status']} (reject requires planned/approved)")
        if a["revision"] != expected_revision:
            raise ActionConflictError(
                f"action {action_id} revision mismatch: expected={expected_revision}, actual={a['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            action_id, "rejected", expected_revision=expected_revision,
            rejection_reason=reason, allowed_actions=_ACTION_ALLOWED_ACTIONS["rejected"],
            reason=f"rejected_by={rejected_by}: {reason}",
        )
        if rowcount == 0:
            raise ActionConflictError(f"action {action_id} CAS race")
        return self._require(action_id)

    def start(
        self, action_id: str, *, expected_revision: int,
        idempotency_key: str, protocol: str = "mock",
        trigger_source: str = "user", skill_id: str | None = None,
    ) -> dict[str, Any]:
        """启动 action → 创建 Run (走 RunService 三层幂等) → action.status=running.

        Returns
        -------
        {"action": <updated>, "run": <new>, "replayed": bool}
        """
        a = self._require(action_id)
        if a["status"] != "approved":
            raise ActionConflictError(f"action {action_id} status={a['status']} (start requires approved)")
        if a["revision"] != expected_revision:
            raise ActionConflictError(
                f"action {action_id} revision mismatch: expected={expected_revision}, actual={a['revision']}"
            )
        # action → running (CAS)
        rowcount = self.repo.update_status_cas(
            action_id, "running", expected_revision=expected_revision,
            allowed_actions=_ACTION_ALLOWED_ACTIONS["running"], reason=None,
        )
        if rowcount == 0:
            raise ActionConflictError(f"action {action_id} CAS race")
        # 创建 Run (走 RunService 注入)
        from backend.services.run_service import RunService
        run_svc = self._run_service or RunService()
        run = run_svc.create_or_replay(
            action_id=action_id, idempotency_key=idempotency_key, attempt=1,
            protocol=protocol, trigger_source=trigger_source, skill_id=skill_id,
            inputs={"action_id": action_id, "plan_hash": a["plan_hash"]},
        )
        return {"action": self._require(action_id), "run": run["run"], "replayed": run["replayed"]}

    def cancel(self, action_id: str, *, expected_revision: int, reason: str) -> dict[str, Any]:
        a = self._require(action_id)
        if a["status"] in ("succeeded", "cancelled", "rejected"):
            raise ActionConflictError(f"action {action_id} status={a['status']} (cancel requires non-terminal)")
        if a["revision"] != expected_revision:
            raise ActionConflictError(
                f"action {action_id} revision mismatch: expected={expected_revision}, actual={a['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            action_id, "cancelled", expected_revision=expected_revision,
            allowed_actions=_ACTION_ALLOWED_ACTIONS["cancelled"], reason=reason,
        )
        if rowcount == 0:
            raise ActionConflictError(f"action {action_id} CAS race")
        return self._require(action_id)

    def finish(self, action_id: str, *, expected_revision: int, succeeded: bool) -> dict[str, Any]:
        """Run 完成后被 RunService 调: action.status = succeeded / failed (CAS)."""
        a = self._require(action_id)
        if a["status"] != "running":
            raise ActionConflictError(f"action {action_id} status={a['status']} (finish requires running)")
        if a["revision"] != expected_revision:
            raise ActionConflictError(
                f"action {action_id} revision mismatch: expected={expected_revision}, actual={a['revision']}"
            )
        new_status = "succeeded" if succeeded else "failed"
        rowcount = self.repo.update_status_cas(
            action_id, new_status, expected_revision=expected_revision,
            allowed_actions=_ACTION_ALLOWED_ACTIONS[new_status], reason=None,
        )
        if rowcount == 0:
            raise ActionConflictError(f"action {action_id} CAS race")
        return self._require(action_id)

    # ------------------------------------------------------------------
    # list / get
    # ------------------------------------------------------------------
    def list_by_case(
        self, case_id: str, *, status: str | None = None, judgment_id: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in _VALID_ACTION_STATUS:
            raise ActionValidationError(f"invalid status: {status}")
        items, total = self.repo.list_by_case(
            case_id, status=status, judgment_id=judgment_id, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, action_id: str) -> dict[str, Any]:
        return self._require(action_id)

    def _require(self, action_id: str) -> dict[str, Any]:
        a = self.repo.get(action_id)
        if a is None:
            raise ActionNotFoundError(f"action {action_id} not found")
        return a
