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
from backend.logging_config import logger
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
# mock 走 skill_runner 演示模式, 不进 v1_runs (留 skill_runs.skill_runner.core.run 显式 mock 入参).
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

    def __init__(
        self, repo: RunRepository | None = None,
        action_service: Any = None,  # ActionService (避免循环)
    ) -> None:
        self.repo = repo or RunRepository()
        self._action_service = action_service
        # 默认懒加载 ActionService (mock 协议 finish 路径用)
        if self._action_service is None:
            try:
                from backend.services.action_service import ActionService
                self._action_service = ActionService()
            except Exception:
                pass  # 避免循环 import, 走 best-effort

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
