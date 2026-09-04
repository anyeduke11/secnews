"""v0.8 B2.3 — SkillRegistry.execute 接线测试 (skill_registry → skill_runner).

设计:
- registry.execute(skill_id, inputs, ticket_id=...) 是 B5 worker 派发的统一入口
- 必须: 1) 未知 id 抛 SkillNotFoundError  2) gate 关抛 PermissionError
        3) gate 开委托 SkillRunner.run 透传结果
- 不依赖真实 backend 起动; gate 用 monkeypatch 模拟开
"""
from __future__ import annotations

import pytest

from backend.services.skill_registry import BUILTIN
from backend.services.skill_registry.core import SkillNotFoundError
from backend.services.skill_runner import SkillRunResult


@pytest.fixture
def skill_registry_gate_open(monkeypatch):
    """monkeypatch is_extension_enabled + kv 双开, 任意 skill 读数为开."""
    from backend.services.skill_registry import gate as gate_mod

    monkeypatch.setattr(gate_mod, "is_extension_enabled", lambda name: True)
    # kv 读数回落 SkillDef.default_enabled (全 False), 直接 monkeypatch 仓储方法
    from backend.repository.settings_repo import SettingsRepository

    monkeypatch.setattr(
        SettingsRepository, "get", lambda self, key, default=None: True
    )
    return gate_mod


# ---------------------------------------------------------------------------
# 1. gate 开 → 委托 runner → 返回 SkillRunResult
# ---------------------------------------------------------------------------
def test_registry_execute_dispatches_to_runner(skill_registry_gate_open, temp_db):
    """registry.execute 在 gate 开时委托 SkillRunner, 返回 SkillRunResult.

    用 builtin 里的真实 A 类 (source-health-scan) — target 是真 service
    (SourceSchedulerService.get_status), 不调 LLM, 不需要 mock.
    """
    result = BUILTIN.execute("source-health-scan", {})
    assert isinstance(result, SkillRunResult)
    assert result.status == "succeeded"
    assert result.fast_path is True
    # 真实 service 返回 dict, 至少含 stats 字段
    assert "stats" in result.outputs or result.outputs.get("stats") is not None or isinstance(result.outputs, dict)


# ---------------------------------------------------------------------------
# 2. ticket_id 透传给 runner → skill_runs.ticket_id
# ---------------------------------------------------------------------------
def test_registry_execute_passes_ticket_id(skill_registry_gate_open, temp_db):
    """ticket_id 经 registry → runner → skill_runs 落库."""
    result = BUILTIN.execute(
        "source-health-scan", {}, ticket_id="ticket-b23-test"
    )
    row = BUILTIN.execute.__self__  # noqa - 改用 repo
    from backend.services.skill_runner import SkillRunRepo
    row = SkillRunRepo().get(result.run_id)
    assert row is not None
    assert row["ticket_id"] == "ticket-b23-test"


# ---------------------------------------------------------------------------
# 3. 未知 skill_id → SkillNotFoundError (gate 之前就应拦截)
# ---------------------------------------------------------------------------
def test_registry_execute_unknown_skill_raises(skill_registry_gate_open, temp_db):
    """get() 找不到 id → SkillNotFoundError, 不应调到 gate 检查."""
    with pytest.raises(SkillNotFoundError):
        BUILTIN.execute("nonexistent-skill-xyz", {})


# ---------------------------------------------------------------------------
# 4. gate 关 → PermissionError (fail loud; 调用方应在派发前过滤)
# ---------------------------------------------------------------------------
def test_registry_execute_gate_closed_raises(temp_db):
    """is_skill_enabled=False → PermissionError (gate 真实状态, 默认全关)."""
    # 不开 gate, builtin 20 个全部 default_enabled=False → 读数全关
    with pytest.raises(PermissionError) as exc_info:
        BUILTIN.execute("source-health-scan", {})
    assert "source-health-scan" in str(exc_info.value)
    assert "停用" in str(exc_info.value) or "未注册" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. runner 注入参数: 自定义 runner 替换默认 (便于 B5 派发层注入 hooks/llm)
# ---------------------------------------------------------------------------
def test_registry_execute_uses_injected_runner(skill_registry_gate_open, temp_db, monkeypatch):
    """runner 参数允许调用方注入 (B6 SSE 推送需要注入 hooks)."""
    from backend.services.skill_runner import SkillRunner, SkillRunnerSettings

    calls: list[str] = []
    original_run = SkillRunner.run

    def tracking_run(self, skill, inputs, *, ticket_id=None):
        calls.append(skill.id)
        return original_run(self, skill, inputs, ticket_id=ticket_id)

    monkeypatch.setattr(SkillRunner, "run", tracking_run)

    custom_runner = SkillRunner(settings=SkillRunnerSettings(persist_runs=True))
    result = BUILTIN.execute(
        "source-health-scan", {}, runner=custom_runner
    )
    assert result.status == "succeeded"
    assert calls == ["source-health-scan"]
