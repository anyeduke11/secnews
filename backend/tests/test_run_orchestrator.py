"""run_orchestrator 最小单测 — action.start → Run 桥接语义保持 (Batch 4 解环).

验证点 (与原 ActionService.start 内联桥接逐项等价):
1. 注入优先: run_service 非 None 时原样使用, 不构造默认实例;
2. 缺省构造: run_service=None 时构造 RunService();
3. 调用形状: attempt 恒 1, inputs 恒 {"action_id", "plan_hash"}, 其余参数透传;
4. 返回形状: create_or_replay 返回值原样透传, 不捕获不改写异常。
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.services import run_orchestrator
from backend.services.run_orchestrator import create_run_for_action_start
from backend.services.run_service import RunService


class _FakeRunService:
    """记录调用入参并返回固定形状的 RunService 替身."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result if result is not None else {"run": {"id": "run_x"}, "replayed": False}

    def create_or_replay(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self._result


def test_injected_run_service_is_used_with_exact_call_shape() -> None:
    fake = _FakeRunService()
    out = create_run_for_action_start(
        action_id="act1", plan_hash="ph123", idempotency_key="idem-1",
        protocol="dsh", trigger_source="agent", skill_id="sk-9",
        run_service=fake,
    )
    assert out == {"run": {"id": "run_x"}, "replayed": False}
    assert fake.calls == [
        {
            "action_id": "act1",
            "idempotency_key": "idem-1",
            "attempt": 1,  # 语义不变: attempt 恒 1
            "protocol": "dsh",
            "trigger_source": "agent",
            "skill_id": "sk-9",
            "inputs": {"action_id": "act1", "plan_hash": "ph123"},  # 形状不变
        }
    ]


def test_none_run_service_constructs_default_run_service(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _SpyRunService(RunService):
        def __init__(self) -> None:
            captured["constructed"] = True
            super().__init__()

        def create_or_replay(self, **kwargs: Any) -> dict[str, Any]:
            captured["kwargs"] = kwargs
            return {"run": {"id": "run_default"}, "replayed": True}

    monkeypatch.setattr(run_orchestrator, "RunService", _SpyRunService)
    out = create_run_for_action_start(
        action_id="a2", plan_hash="p2", idempotency_key="k2", protocol="pi",
    )
    assert captured["constructed"] is True
    assert out == {"run": {"id": "run_default"}, "replayed": True}
    # 缺省参数语义: trigger_source 默认 user, skill_id 默认 None
    assert captured["kwargs"]["trigger_source"] == "user"
    assert captured["kwargs"]["skill_id"] is None
    assert captured["kwargs"]["attempt"] == 1


def test_exceptions_from_run_service_pass_through_unchanged() -> None:
    class _BoomRunService:
        def create_or_replay(self, **_kwargs: Any) -> dict[str, Any]:
            raise ValueError("run conflict (synthetic)")

    with pytest.raises(ValueError, match="run conflict"):
        create_run_for_action_start(
            action_id="a3", plan_hash="p3", idempotency_key="k3",
            protocol="direct", run_service=_BoomRunService(),
        )


def test_real_run_service_accepts_bridge_call_shape() -> None:
    """真 RunService 走桥接调用形状 → 协议校验语义不变 (invalid protocol 抛原异常)."""
    from backend.services.run_service import RunValidationError

    svc = RunService()
    with pytest.raises(RunValidationError, match="invalid protocol"):
        create_run_for_action_start(
            action_id="a4", plan_hash="p4", idempotency_key="k4",
            protocol="mock", run_service=svc,
        )
