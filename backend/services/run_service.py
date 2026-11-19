"""v1.0 T12 RunService — Run 三层幂等 (contracts §7.4) + 7 态机 + 桥接 action.

三层幂等:
  1. 重复 (idempotency_key, action_id) body相同 → 200 + replayed (沿用 §7.4 idempotent replay)
  2. body不同 (同 key) → 409 E_CONFLICT
  3. 同一 (action_id, attempt) 已存在 → 422 (UNIQUE INDEX + service 双重 check)

7 态机 (contracts §7.1):
  queued → claimed → running → succeeded
                              ↓ fail/cancel
                            failed / cancelled / timed_out

T12 范围: 同步链路 (action.start 立即创建 run 并 finish). 真异步派发留 T12+ (T09 worker_coordinator).
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.observability_records import stage_span
from backend.repository.run_repo import RunRepository


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------
class RunValidationError(InvalidParamException):
    def __init__(self, message: str = "run validation failed") -> None:
        super().__init__(message)


class RunNotFoundError(NotFoundException):
    def __init__(self, message: str = "run not found") -> None:
        super().__init__(message)


class RunConflictError(ConflictException):
    def __init__(self, message: str = "run state conflict") -> None:
        super().__init__(message)


_RUN_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "queued": ["claim", "cancel"],
    "claimed": ["start", "cancel"],
    "running": ["finish", "fail", "cancel"],
    "succeeded": ["view_only"],
    "failed": ["retry", "view_only"],
    "cancelled": ["view_only"],
    "timed_out": ["retry", "view_only"],
}
_VALID_RUN_STATUS = set(_RUN_ALLOWED_ACTIONS.keys())
# v1.0 C07 R05 修复: 'mock' 协议从生产 _VALID_RUN_PROTOCOLS 移除 (旧路径虚报完成).
# mock 演示模式不进 v1_runs (技能域已于 2026-11-19 整体退役).
_VALID_RUN_PROTOCOLS = {"dsh", "pi", "direct"}
_VALID_TRIGGER_SOURCES = {"user", "agent", "system", "scheduled", "webhook"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_ulid() -> str:
    """Run ID = 'run_' + 26 字符 ULID."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "run_" + "".join(random.choice(alphabet) for _ in range(26))


def _body_hash(inputs: dict[str, Any]) -> str:
    """run body 哈希 (用于 §7.4 幂等 replay 检测 body 是否相同)."""
    import json
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# RunService
# ---------------------------------------------------------------------------
class RunService:
    """Run 服务 — 三层幂等 + 状态机 + 桥接 action."""

    def __init__(self, repo: RunRepository | None = None) -> None:
        self.repo = repo or RunRepository()
        # Batch 4 解环注: 原 __init__ 曾惰性 import ActionService 存入
        # self._action_service (注释称 "mock 协议 finish 路径用"), 但该属性
        # 自 C07 R05 移除 mock 协议后全仓无任何读取方, 属死代码 — 已整体
        # 移除。run_service 现不依赖 action_service, action→run 桥接统一走
        # backend.services.run_orchestrator (R4 守卫: test_service_cycle_guard.py)。

    # ------------------------------------------------------------------
    # create_or_replay (contracts §7.4 三层幂等)
    # ------------------------------------------------------------------
    def create_or_replay(
        self, *, action_id: str, idempotency_key: str, attempt: int,
        protocol: str = "mock", trigger_source: str = "user",
        skill_id: str | None = None, inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """contracts §7.4:
          - (idempotency_key, action_id) 已存在 + body同 → 返原 run + replayed=True
          - 同上 body不同 → 409 E_CONFLICT
          - (action_id, attempt) 已存在 → 422
        """
        if protocol not in _VALID_RUN_PROTOCOLS:
            raise RunValidationError(f"invalid protocol: {protocol}")
        if trigger_source not in _VALID_TRIGGER_SOURCES:
            raise RunValidationError(f"invalid trigger_source: {trigger_source}")
        if attempt < 1:
            raise RunValidationError("attempt must be ≥ 1")
        if not idempotency_key or not idempotency_key.strip():
            raise RunValidationError("idempotency_key required")
        inputs = inputs or {}
        # 守卫 1: 同一 (action_id, attempt) 唯一
        existing_attempt = self.repo.find_by_action_attempt(action_id, attempt)
        if existing_attempt is not None and existing_attempt["idempotency_key"] != idempotency_key:
            raise RunValidationError(
                f"run for action={action_id} attempt={attempt} already exists "
                f"(id={existing_attempt['id']}); same attempt can only have one Run"
            )
        if existing_attempt is not None and existing_attempt["idempotency_key"] == idempotency_key:
            # 守卫 2: body 比对
            new_hash = _body_hash(inputs)
            old_hash = _body_hash(existing_attempt.get("inputs", {}))
            if new_hash != old_hash:
                raise RunConflictError(
                    f"idempotency_key={idempotency_key} reused with different body "
                    f"(action={action_id})"
                )
            return {"run": existing_attempt, "replayed": True}
        # 守卫 3: 沿 (idempotency_key, action_id) 检索 (与现有复用)
        existing_idem = self.repo.find_by_idem(action_id, idempotency_key)
        if existing_idem is not None:
            new_hash = _body_hash(inputs)
            old_hash = _body_hash(existing_idem.get("inputs", {}))
            if new_hash != old_hash:
                raise RunConflictError(
                    f"idempotency_key={idempotency_key} reused with different body "
                    f"(action={action_id})"
                )
            return {"run": existing_idem, "replayed": True}
        # 全新 Run: 落库 (统一 queued, 真实派发由 worker_pump._c07_r04_skill_dispatcher 走 SkillRunner.run)
        rid = _run_ulid()
        now = _utcnow_iso()
        body = {
            "id": rid, "action_id": action_id, "attempt": attempt,
            "skill_id": skill_id, "protocol": protocol, "trigger_source": trigger_source,
            "idempotency_key": idempotency_key,
            "status": "queued",  # v1.0 C07 R05 修复: 永远 queued (mock 协议已从生产移除)
            "inputs": inputs, "steps": [],
            "budget_tokens": None, "budget_seconds": None,
            "started_at": now,
            "finished_at": None,
            "duration_ms": None,
            "result_excerpt": None,
            "error": None, "artifact_ids": [],
            "revision": 1, "created_at": now, "updated_at": now,
            "allowed_actions": _RUN_ALLOWED_ACTIONS["queued"],
            "reason": None,
        }
        # R-10: run 段 span 覆盖 v1_runs 落库 (撞库 race-replay 分支亦在 span 内,
        # 以 replayed=True 返回时 span 记 ok — run 记录存在性未变)
        with stage_span("run", target=f"run:{rid}"):
            try:
                self.repo.insert(body)
            except Exception as e:
                # UNIQUE INDEX 撞库 → race; 返已存在的 run
                if "UNIQUE" in str(e).upper() or "unique" in str(e).lower():
                    existing = self.repo.find_by_action_attempt(action_id, attempt)
                    if existing is not None:
                        return {"run": existing, "replayed": True}
                raise
        return {"run": body, "replayed": False}

    def _get_action_revision(self, action_id: str) -> int:
        """读 action 当前 revision (走 ActionService)."""
        from backend.repository.action_repo import ActionRepository
        a = ActionRepository().get(action_id)
        return a["revision"] if a else 1

    # ------------------------------------------------------------------
    # R-1 人工回执 (v0.8.9): direct 执行体 = 人 — claim/start/finish/cancel
    # ------------------------------------------------------------------
    _RUN_OUTCOME_TO_STATUS: dict[str, str] = {  # noqa: RUF012 — 常量映射, 不可变使用
        "done": "succeeded",
        "failed": "failed",
        "cancelled": "cancelled",
        "timeout": "timed_out",
        "needs_human": "failed",
    }

    def _publish_v1_run_event(self, r: dict[str, Any], event_suffix: str) -> None:
        """R-6 前置: run 生命周期事件写 v1_outbox (下行 SSE 管道既有, 失败吞错)."""
        try:
            from backend.observability import get_trace_id
            from backend.repository.outbox_repo import OutboxRepo
            OutboxRepo().enqueue(
                event_type="v1_run",
                aggregate_type="run",
                aggregate_id=r["id"],
                revision=int(r.get("revision", 0) or 0),
                payload={
                    "id": r["id"], "action_id": r["action_id"],
                    "status": r.get("status"), "outcome": r.get("outcome"),
                    "event": event_suffix,
                },
                trace_id=get_trace_id() or "no-trace",
            )
        except Exception as e:
            import logging
            logging.getLogger("hotspot.run_service").debug(
                f"v1_run outbox enqueue skipped: {e}")

    def _audit_receipt(self, action_name: str, run_id: str, detail: dict[str, Any]) -> None:
        from backend.observability_records import record_audit
        record_audit("web", f"run.{action_name}", target=f"run:{run_id}", detail=detail)

    def claim(self, run_id: str, *, executor: str = "manual") -> dict[str, Any]:
        """queued → claimed (CAS)。认领执行 (R-1 人工=manual; R-3 pi 派发传 'pi')。

        D2 裁决: executor 列记录谁执行 ('manual' | 'pi'), claim 即落。
        """
        with stage_span("run", target=f"run:{run_id}"):
            r = self.repo.get(run_id)
            if r is None:
                raise RunNotFoundError(f"run {run_id} not found")
            rc = self.repo.transition(
                run_id, "queued", "claimed",
                allowed_actions=_RUN_ALLOWED_ACTIONS["claimed"], executor=executor)
            if rc == 0:
                raise RunConflictError(
                    f"run {run_id} status={r['status']} (claim requires queued)")
            updated = self.repo.get(run_id)
            self._publish_v1_run_event(updated, "claimed")
            self._audit_receipt("claim", run_id, {"from": "queued", "to": "claimed"})
            return updated

    def start(self, run_id: str) -> dict[str, Any]:
        """claimed → running (CAS)，重置 started_at 为真实开工时刻。"""
        with stage_span("run", target=f"run:{run_id}"):
            r = self.repo.get(run_id)
            if r is None:
                raise RunNotFoundError(f"run {run_id} not found")
            rc = self.repo.transition(
                run_id, "claimed", "running", started_at=_utcnow_iso(),
                allowed_actions=_RUN_ALLOWED_ACTIONS["running"])
            if rc == 0:
                raise RunConflictError(
                    f"run {run_id} status={r['status']} (start requires claimed)")
            updated = self.repo.get(run_id)
            self._publish_v1_run_event(updated, "started")
            self._audit_receipt("start", run_id, {"from": "claimed", "to": "running"})
            return updated

    def finish(
        self, run_id: str, *, outcome: str,
        result_excerpt: str | None = None, error: str | None = None,
    ) -> dict[str, Any]:
        """running → 终态 (CAS)，账本 outcome 终判 (R-1 核心)。

        - outcome ∈ {done, failed, cancelled, timeout, needs_human}；
          done → status=succeeded 且**必须已有 ≥1 artifact** (RA-9: 禁止成功但无产物)；
          failed/timeout/needs_human → error 必填 (失败真实性)；
        - artifact_ids 由 v1_artifacts 实表回填 (单一真相源，不信入参)。
        """
        with stage_span("run", target=f"run:{run_id}"):
            r = self.repo.get(run_id)
            if r is None:
                raise RunNotFoundError(f"run {run_id} not found")
            if r["status"] != "running":
                # 状态冲突优先于参数校验 (queued 直接 finish = 状态机违例, 非参数问题)
                raise RunConflictError(
                    f"run {run_id} status={r['status']} (finish requires running)")
            if outcome not in self._RUN_OUTCOME_TO_STATUS:
                raise RunValidationError(
                    f"invalid outcome: {outcome} "
                    f"(allowed: {sorted(self._RUN_OUTCOME_TO_STATUS)})")
            to_status = self._RUN_OUTCOME_TO_STATUS[outcome]
            artifact_ids: list[str] | None = None
            if outcome == "done":
                from backend.repository.artifact_repo import ArtifactRepository
                artifact_ids = ArtifactRepository().ids_by_run(run_id)
                if not artifact_ids:
                    raise RunValidationError(
                        f"outcome='done' requires ≥1 registered artifact for run "
                        f"{run_id} (RA-9: 禁止成功但无产物); register via POST /api/v1/artifacts first")
            if outcome in ("failed", "timeout", "needs_human") and not (error or "").strip():
                raise RunValidationError(
                    f"outcome='{outcome}' requires error (失败真实性: 必填原因码)")
            finished_at = _utcnow_iso()
            duration_ms: int | None = None
            try:
                started = datetime.fromisoformat(r.get("started_at") or "")
                if started.tzinfo is None:
                    from datetime import timezone as _tz
                    started = started.replace(tzinfo=_tz.utc)
                duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            except (ValueError, TypeError):
                duration_ms = None
            rc = self.repo.transition(
                run_id, "running", to_status,
                outcome=outcome, finished_at=finished_at, duration_ms=duration_ms,
                result_excerpt=result_excerpt,
                error=(str(error)[:500] if error else None),
                artifact_ids=artifact_ids,
                allowed_actions=_RUN_ALLOWED_ACTIONS[to_status],
            )
            if rc == 0:
                raise RunConflictError(
                    f"run {run_id} status={r['status']} (finish requires running)")
            updated = self.repo.get(run_id)
            self._publish_v1_run_event(updated, "finished")
            self._audit_receipt(
                "finish", run_id,
                {"outcome": outcome, "status": to_status, "artifacts": len(artifact_ids or [])})
            return updated

    def cancel(self, run_id: str, *, reason: str | None = None) -> dict[str, Any]:
        """queued/claimed/running → cancelled (CAS)，失败真实性: 保留 reason。"""
        with stage_span("run", target=f"run:{run_id}"):
            r = self.repo.get(run_id)
            if r is None:
                raise RunNotFoundError(f"run {run_id} not found")
            rc = self.repo.transition(
                run_id, ("queued", "claimed", "running"), "cancelled",
                outcome="cancelled", finished_at=_utcnow_iso(),
                result_excerpt=(str(reason)[:500] if reason else None),
                allowed_actions=_RUN_ALLOWED_ACTIONS["cancelled"],
            )
            if rc == 0:
                raise RunConflictError(
                    f"run {run_id} status={r['status']} (cancel requires queued/claimed/running)")
            updated = self.repo.get(run_id)
            self._publish_v1_run_event(updated, "cancelled")
            self._audit_receipt("cancel", run_id, {"from": r["status"], "to": "cancelled"})
            return updated

    # ------------------------------------------------------------------
    # list / get
    # ------------------------------------------------------------------
    def list_by_action(
        self, action_id: str, *, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in _VALID_RUN_STATUS:
            raise RunValidationError(f"invalid status: {status}")
        items, total = self.repo.list_by_action(
            action_id, status=status, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, run_id: str) -> dict[str, Any]:
        r = self.repo.get(run_id)
        if r is None:
            raise RunNotFoundError(f"run {run_id} not found")
        return r
