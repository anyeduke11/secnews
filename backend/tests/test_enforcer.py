"""C4-1 enforcer 编译 — 审批快照 → 进程约束 (L2/L4) 的边界用例。

覆盖 PRD §7 四层边界的 L2 与 L4 断言: 未审批即拒绝 (L1 对应物)、argv
双重校验、plan 外路径拒绝、网络默认全禁 (env 级)、双超时预算、审批快照
指纹比对。
"""
from __future__ import annotations

import time

import pytest

from backend.services.execution_plan.enforcer import BoundaryViolation, compile_enforcement
from backend.services.execution_plan.schema import ExecutionPlan
from backend.services.execution_plan.service import boundary_hash

_PLAN = {
    "commands": [["python", "-c", "print('hi')"]],
    "writable_paths": ["out"],
    "readable_paths": ["."],
    "network": [],
    "command_timeout_sec": 30,
    "total_timeout_sec": 120,
    "output_artifact": {"kind": "report", "title": "CVE brief", "acceptance_notes": ""},
}


def _envelope(**plan_overrides) -> dict:
    plan = {**_PLAN, **plan_overrides}
    return {"status": "approved", "plan": plan, "submitted_by": "tester"}


def _compile(envelope: dict, expected_hash: str | None = None):
    return compile_enforcement(
        envelope, run_id="run-1", workspace="workspace/demo", expected_hash=expected_hash)


# ---------------------------------------------------------------------------
# L1 对应物: 默认拒绝 — 未 approved 不被消费
# ---------------------------------------------------------------------------
def test_unapproved_plan_is_rejected():
    draft = _envelope()
    draft["status"] = "draft"
    with pytest.raises(BoundaryViolation) as e:
        _compile(draft)
    assert e.value.reason_code == "E_PLAN_NOT_APPROVED"

    with pytest.raises(BoundaryViolation):
        _compile({})  # 无 plan


# ---------------------------------------------------------------------------
# L2: argv 双重校验 (静态白名单 ∩ plan 动态子集)
# ---------------------------------------------------------------------------
def test_argv_outside_plan_rejected():
    spec = _compile(_envelope())
    assert spec.check_command(["python", "-c", "print('hi')"]) == ("python", "-c", "print('hi')")
    # 静态白名单内但未列入 plan → 拒绝
    with pytest.raises(BoundaryViolation) as e:
        spec.check_command(["python", "-c", "import os"])
    assert e.value.reason_code == "E_ARGV_NOT_IN_PLAN"


def test_argv_not_in_static_allowlist_rejected():
    # 即使写进 plan, 静态白名单 (P0-A) 仍先拦截 — 只收紧不放松
    spec = _compile(_envelope(commands=[["curl", "https://example.com"]]))
    with pytest.raises(BoundaryViolation) as e:
        spec.check_command(["curl", "https://example.com"])
    assert e.value.reason_code == "E_ARGV_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# L2: plan 外路径拒绝 (writable/readable 必须相对 workspace 锁定根)
# ---------------------------------------------------------------------------
def test_paths_outside_workspace_rejected():
    for bad in ({"writable_paths": ["../escape"]}, {"readable_paths": ["/etc"]}):
        with pytest.raises(BoundaryViolation) as e:
            _compile(_envelope(**bad))
        assert e.value.reason_code == "E_PATH_OUTSIDE_WORKSPACE"


def test_workspace_lock_required():
    with pytest.raises(BoundaryViolation) as e:
        compile_enforcement(_envelope(), run_id="run-1", workspace="")
    assert e.value.reason_code == "E_WORKSPACE_INVALID"
    with pytest.raises(BoundaryViolation) as e:
        compile_enforcement(_envelope(), run_id="run-1", workspace="/tmp/elsewhere")
    assert e.value.reason_code == "E_WORKSPACE_INVALID"


# ---------------------------------------------------------------------------
# L2: 网络默认全禁 + env 隔离 (凭据/代理不下传)
# ---------------------------------------------------------------------------
def test_network_default_denied_and_secrets_stripped():
    spec = _compile(_envelope())
    assert spec.network_open is False
    env = spec.build_env({
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "sk-xxx",
        "ANTHROPIC_TOKEN": "tok",
        "HTTPS_PROXY": "http://proxy:8080",
        "HOTSPOT_EXEC_WORKSPACE": "workspace/demo",
    })
    assert "OPENAI_API_KEY" not in env and "ANTHROPIC_TOKEN" not in env
    assert "HTTPS_PROXY" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["HOTSPOT_EXEC_NETWORK"] == ""          # 空 = 全禁 (声明)
    assert env["HOTSPOT_EXEC_BOUNDARY_HASH"] == spec.boundary_hash


def test_network_open_when_plan_allows():
    spec = _compile(_envelope(network=["nvd.nist.gov"]))
    assert spec.network_open is True
    assert spec.build_env({})["HOTSPOT_EXEC_NETWORK"] == "nvd.nist.gov"


# ---------------------------------------------------------------------------
# 双超时预算
# ---------------------------------------------------------------------------
def test_total_timeout_budget_exhaustion():
    spec = _compile(_envelope())
    assert spec.command_timeout_sec == 30
    assert 0 < spec.remaining_seconds(time.monotonic()) <= 120
    assert spec.remaining_seconds(time.monotonic() - 121) < 0


# ---------------------------------------------------------------------------
# L4: 审批快照指纹 (落库后被改 = 越界)
# ---------------------------------------------------------------------------
def test_boundary_hash_mismatch_detected():
    envelope = _envelope()
    good = boundary_hash(ExecutionPlan.model_validate(envelope["plan"]))
    assert _compile(envelope, expected_hash=good).boundary_hash == good

    envelope["plan"]["commands"] = [["python", "-c", "print('tampered')"]]
    with pytest.raises(BoundaryViolation) as e:
        _compile(envelope, expected_hash=good)
    assert e.value.reason_code == "E_BOUNDARY_HASH_MISMATCH"