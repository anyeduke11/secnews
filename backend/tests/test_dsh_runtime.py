"""dsh runtime mock/真子进程切换测试 (v0.8 Phase B B4).

覆盖 (对应 V0.8_REFACTOR_PLAN.md §6 B4 验收):
  1. 默认 mode=auto
  2. set_mode 持久化 (新实例读回)
  3. 非法 kv 值回退 auto
  4. auto + 无启动命令 → not_configured
  5. auto + 有命令 → subprocess
  6. 显式 mock + 有命令 → 仍 mock
  7. execute: subprocess 成功 → mode_used=subprocess, fallback=False
  8. execute: subprocess 异常 → mock 兜底 + fallback=True + 审计落 audit_log
  9. 连续 3 次回退 → 熔断, 第 4 次不再尝试 subprocess
  10. reset_health 后恢复尝试
  11. invoke_mock 也异常 → 上抛不吞
  12. 成功重置连续回退计数 (只对"连续"失败熔断)
"""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.repository.settings_repo import SettingsRepository
from backend.services.dsh.runtime import DshRuntime, DshRuntimeMode


@pytest.fixture()
def rt(temp_db):
    """每个测试独立 DshRuntime 实例 — 健康熔断状态是实例内缓存。"""
    return DshRuntime()


def _set_command(monkeypatch: pytest.MonkeyPatch, command: list[str]) -> None:
    """monkeypatch 既有配置读取函数 supervisor.get_dsh_config 模拟启动命令。"""
    from backend.services.dsh import supervisor as dsh_sup

    monkeypatch.setattr(
        dsh_sup,
        "get_dsh_config",
        lambda: {
            "endpoint": "http://localhost:3210",
            "command": command,
            "command_raw": " ".join(command),
            "autostart": False,
        },
    )


def _audit_fallback_rows() -> list:
    """查 audit_log 里的 dsh.runtime_fallback 行 (审计落点断言)。"""
    conn = get_connection()
    return conn.execute(
        "SELECT actor, action, target, detail FROM audit_log "
        "WHERE action = 'dsh.runtime_fallback'"
    ).fetchall()


# ---------------------------------------------------------------------------
# 模式读写 (settings.kv 持久化)
# ---------------------------------------------------------------------------
def test_default_mode_is_auto(rt: DshRuntime):
    """未写 kv 时默认 auto — B4 的"默认即安全"契约。"""
    assert rt.get_mode() is DshRuntimeMode.AUTO


def test_set_mode_persists_across_instances(rt: DshRuntime):
    """set_mode 落 settings.kv — 新实例 (模拟重启) 读回同值。"""
    rt.set_mode(DshRuntimeMode.SUBPROCESS)
    assert DshRuntime().get_mode() is DshRuntimeMode.SUBPROCESS
    # 字符串形式同样可写
    DshRuntime().set_mode("mock")
    assert DshRuntime().get_mode() is DshRuntimeMode.MOCK


def test_set_mode_rejects_invalid_value(rt: DshRuntime):
    """写入口拦脏值 — 非法 mode 不允许被持久化。"""
    with pytest.raises(ValueError, match="非法"):
        rt.set_mode("yolo")


def test_invalid_kv_value_falls_back_to_auto(temp_db):
    """存量脏 kv (字符串 / 非字符串) 读回 auto 而非崩溃。"""
    repo = SettingsRepository()
    repo.set("dsh.runtime_mode", "bogus")
    assert DshRuntime().get_mode() is DshRuntimeMode.AUTO
    repo.set("dsh.runtime_mode", 42)
    assert DshRuntime().get_mode() is DshRuntimeMode.AUTO


# ---------------------------------------------------------------------------
# resolve_effective (auto 解析)
# ---------------------------------------------------------------------------
def test_auto_without_command_not_configured(rt: DshRuntime, monkeypatch):
    """auto + 未配置启动命令 → not_configured (沿用既有降级语义)。"""
    _set_command(monkeypatch, [])
    effective, reason = rt.resolve_effective()
    assert effective == "not_configured"
    assert "no startup command" in reason


def test_auto_with_command_resolves_subprocess(rt: DshRuntime, monkeypatch):
    """auto + 已配置启动命令 → subprocess。"""
    _set_command(monkeypatch, ["node", "/tmp/dsh/dev.mjs"])
    assert rt.resolve_effective()[0] == "subprocess"


def test_explicit_mock_with_command_stays_mock(rt: DshRuntime, monkeypatch):
    """显式 mock 优先于命令配置 — 有命令也不走 subprocess。"""
    _set_command(monkeypatch, ["node", "/tmp/dsh/dev.mjs"])
    rt.set_mode(DshRuntimeMode.MOCK)
    assert rt.resolve_effective()[0] == "mock"


def test_explicit_subprocess_without_command(rt: DshRuntime, monkeypatch):
    """显式 subprocess 即使无命令也解析为 subprocess — 用户显式选择不被 auto 悄悄改写。"""
    _set_command(monkeypatch, [])
    rt.set_mode(DshRuntimeMode.SUBPROCESS)
    assert rt.resolve_effective()[0] == "subprocess"


# ---------------------------------------------------------------------------
# execute_with_fallback (派发 + 回退)
# ---------------------------------------------------------------------------
def test_execute_subprocess_success(rt: DshRuntime, monkeypatch):
    """subprocess 成功 → 原样返回, mode_used=subprocess, 无回退。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])
    calls = {"sub": 0, "mock": 0}

    def sub(task):
        calls["sub"] += 1
        return {"ok": True, "via": "sub"}

    def mock(task):
        calls["mock"] += 1
        return {"ok": True, "via": "mock"}

    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "chat"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "sub"}
    assert mode_used == "subprocess"
    assert fallback is False
    assert calls == {"sub": 1, "mock": 0}


def test_execute_subprocess_error_falls_back_to_mock(rt: DshRuntime, monkeypatch):
    """subprocess 异常 → mock 兜底 + fallback=True + 审计落 audit_log。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])

    def sub(task):
        raise RuntimeError("spawn failed: exit 1")

    def mock(task):
        return {"ok": True, "via": "mock"}

    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "chat"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "mock"}
    assert mode_used == "mock"
    assert fallback is True
    # 审计落点: audit_log 出现一条 dsh.runtime_fallback, detail 带失败原因
    rows = _audit_fallback_rows()
    assert len(rows) == 1
    assert rows[0]["actor"] == "system"
    assert rows[0]["target"] == "chat"
    detail = json.loads(rows[0]["detail"])
    assert detail["trigger"] == "subprocess_error"
    assert "spawn failed" in detail["error"]


def test_three_consecutive_failures_trip_circuit(rt: DshRuntime, monkeypatch):
    """连续 3 次回退 (对齐 supervisor max_restarts=3) → 第 4 次不再尝试 subprocess。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])
    sub_calls = {"n": 0}

    def sub(task):
        sub_calls["n"] += 1
        raise TimeoutError("subprocess timeout")

    def mock(task):
        return {"ok": True, "via": "mock"}

    for _ in range(3):
        _, mode_used, fallback = rt.execute_with_fallback(
            {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
        )
        assert mode_used == "mock"
        assert fallback is True
    assert sub_calls["n"] == 3  # 前三次都真实尝试过

    # 第 4 次: 熔断生效, subprocess 不再被调用
    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "mock"}
    assert mode_used == "mock"
    assert fallback is True
    assert sub_calls["n"] == 3


def test_reset_health_restores_subprocess_attempt(rt: DshRuntime, monkeypatch):
    """熔断后 reset_health → 恢复对 subprocess 的尝试。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])
    sub_calls = {"n": 0}
    fail = {"on": True}

    def sub(task):
        sub_calls["n"] += 1
        if fail["on"]:
            raise RuntimeError("boom")
        return {"ok": True, "via": "sub"}

    def mock(task):
        return {"ok": True, "via": "mock"}

    for _ in range(3):
        rt.execute_with_fallback(
            {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
        )
    assert sub_calls["n"] == 3

    rt.reset_health()
    fail["on"] = False
    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "sub"}
    assert mode_used == "subprocess"
    assert fallback is False
    assert sub_calls["n"] == 4


def test_success_resets_consecutive_counter(rt: DshRuntime, monkeypatch):
    """非连续失败不熔断 — 成功一次即清零计数 (只统计"连续"回退)。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])
    sub_calls = {"n": 0}
    fail = {"on": True}

    def sub(task):
        sub_calls["n"] += 1
        if fail["on"]:
            raise RuntimeError("boom")
        return {"ok": True, "via": "sub"}

    def mock(task):
        return {"ok": True, "via": "mock"}

    # 2 次失败 → 1 次成功 → 1 次失败: 计数被成功清零, 未达熔断阈值
    rt.execute_with_fallback({"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock)
    rt.execute_with_fallback({"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock)
    fail["on"] = False
    rt.execute_with_fallback({"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock)
    fail["on"] = True
    rt.execute_with_fallback({"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock)

    # 第 5 次派发仍尝试 subprocess (未熔断)
    _, mode_used, _ = rt.execute_with_fallback(
        {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert sub_calls["n"] == 5
    assert mode_used == "mock"


def test_mock_error_propagates(rt: DshRuntime, monkeypatch):
    """invoke_mock 也异常 → 上抛不吞 (mock 是最后兜底, 坏了必须暴露)。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])

    def sub(task):
        raise RuntimeError("subprocess dead")

    def mock(task):
        raise ValueError("mock dead too")

    with pytest.raises(ValueError, match="mock dead too"):
        rt.execute_with_fallback(
            {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
        )


def test_execute_not_configured_uses_mock_without_fallback(rt: DshRuntime, monkeypatch):
    """auto + 无命令 → not_configured: mock 是第一选择, 不算回退、不写审计。"""
    _set_command(monkeypatch, [])
    calls = {"sub": 0, "mock": 0}

    def sub(task):
        calls["sub"] += 1
        return {"ok": True, "via": "sub"}

    def mock(task):
        calls["mock"] += 1
        return {"ok": True, "via": "mock"}

    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "mock"}
    assert mode_used == "mock"
    assert fallback is False
    assert calls == {"sub": 0, "mock": 1}
    assert _audit_fallback_rows() == []


def test_execute_explicit_mock_never_touches_subprocess(rt: DshRuntime, monkeypatch):
    """显式 mock 模式: 有命令也不触碰 subprocess。"""
    _set_command(monkeypatch, ["node", "dev.mjs"])
    rt.set_mode(DshRuntimeMode.MOCK)
    calls = {"sub": 0, "mock": 0}

    def sub(task):
        calls["sub"] += 1
        return {"ok": True, "via": "sub"}

    def mock(task):
        calls["mock"] += 1
        return {"ok": True, "via": "mock"}

    result, mode_used, fallback = rt.execute_with_fallback(
        {"task_type": "t"}, invoke_subprocess=sub, invoke_mock=mock
    )
    assert result == {"ok": True, "via": "mock"}
    assert mode_used == "mock"
    assert fallback is False
    assert calls == {"sub": 0, "mock": 1}
