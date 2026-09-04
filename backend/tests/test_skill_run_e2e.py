"""v0.8 B5 — skill_registry → skill_runner 端到端 e2e (skill_runs 历史可查).

设计:
- 入口: registry.execute(skill_id, inputs, ticket_id=...)
- 覆盖: 真实 run_id / skill_runs 落库 / C 类产物落 wiki / 历史列表 / 失败兜底
- 不依赖真实 LLM / 后端服务; A/B 类 zero-LLM, C 类用 builtin mock wiki target
"""
from __future__ import annotations

import json

import pytest

from backend.services.skill_registry import BUILTIN
from backend.services.skill_registry.core import SkillNotFoundError
from backend.services.skill_runner import SkillRunRepo


@pytest.fixture
def e2e_gate_open(monkeypatch, tmp_path):
    """开 skill_registry gate + 切 wiki 根到 tmp (C 类产物隔离)."""
    from backend.services.skill_registry import gate as gate_mod

    monkeypatch.setattr(gate_mod, "is_extension_enabled", lambda name: True)
    from backend.repository.settings_repo import SettingsRepository

    monkeypatch.setattr(
        SettingsRepository, "get", lambda self, key, default=None: True
    )
    # wiki_fs root 切 tmp — C 类 write_content 产物落此目录
    monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(tmp_path))
    from backend.wiki_fs import root as wf_root

    wf_root.WIKI_ROOT = tmp_path
    return gate_mod


# ---------------------------------------------------------------------------
# 1. A 类 fast-path 写 skill_runs, 结果可查
# ---------------------------------------------------------------------------
def test_e2e_a_class_run_persists_to_skill_runs(e2e_gate_open):
    result = BUILTIN.execute("source-health-scan", {})
    assert result.status == "succeeded", result.error
    assert result.run_id

    row = SkillRunRepo().get(result.run_id)
    assert row is not None
    assert row["skill_id"] == "source-health-scan"
    assert row["status"] == "succeeded"
    assert row["ticket_id"] is None


# ---------------------------------------------------------------------------
# 2. ticket_id 透传 + 列表按 skill 可查
# ---------------------------------------------------------------------------
def test_e2e_ticket_id_and_list_by_skill(e2e_gate_open):
    BUILTIN.execute("source-health-scan", {}, ticket_id="ticket-e2e-1")
    BUILTIN.execute("source-health-scan", {}, ticket_id="ticket-e2e-2")

    rows = SkillRunRepo().list_for_skill("source-health-scan")
    tickets = [r["ticket_id"] for r in rows if r["ticket_id"]]
    assert "ticket-e2e-1" in tickets
    assert "ticket-e2e-2" in tickets


# ---------------------------------------------------------------------------
# 3. C 类 pipeline 产物落 wiki (write_content target → tmp wiki fs)
# ---------------------------------------------------------------------------
def test_e2e_c_class_writes_wiki_artifact(e2e_gate_open, tmp_path):
    result = BUILTIN.execute("weekly-top-events", {"top_n": 3})
    assert result.status == "succeeded"

    # builtin weekly-top-events pipeline 最后一个 step 是 wiki write_content
    files = [p for p in tmp_path.rglob("*.md") if p.is_file()]
    assert files, "C 类 skill 应在 wiki fs 下落产物 md 文件"


# ---------------------------------------------------------------------------
# 4. 失败兜底: 缺失 target → skill_runs status=failed, 不抛异常
# ---------------------------------------------------------------------------
def test_e2e_missing_target_succeeds_as_failed_run(e2e_gate_open):
    # 构造一个 minimal C 类 skill 描述, 指向不存在 module
    bad_skill = {
        "id": "bad-e2e-skill",
        "name": "bad",
        "desc": "bad skill for e2e test",
        "category": "C",
        "skill_type": "pipeline",
        "target": {"kind": "module", "name": "nonexistent.module"},
        "pipeline": {"steps": [{"kind": "service", "target": "nonexistent.module.fn"}]},
        "prompt_template": "test",
        "feature_gate": "test",
        "default_enabled": True,
    }
    from backend.services.skill_registry.core import SkillDef
    from backend.services.skill_runner import SkillRunner

    skill = SkillDef(**bad_skill)
    runner = SkillRunner()
    result = runner.run(skill, {"x": 1})
    assert result.status == "failed"
    assert result.run_id


# ---------------------------------------------------------------------------
# 5. 同 skill 多次执行隔离 (run_id 唯一)
# ---------------------------------------------------------------------------
def test_e2e_multiple_runs_isolated(e2e_gate_open):
    r1 = BUILTIN.execute("source-health-scan", {})
    r2 = BUILTIN.execute("source-health-scan", {})
    assert r1.run_id != r2.run_id
    assert SkillRunRepo().get(r1.run_id) is not None
    assert SkillRunRepo().get(r2.run_id) is not None


# ---------------------------------------------------------------------------
# 6. 未知 skill_id → SkillNotFoundError (e2e 入口)
# ---------------------------------------------------------------------------
def test_e2e_unknown_skill_raises(e2e_gate_open):
    with pytest.raises(SkillNotFoundError):
        BUILTIN.execute("nonexistent-e2e-skill", {})


# ---------------------------------------------------------------------------
# 7. 不同 skill 历史互不干扰 (list_for_skill 维度隔离)
# ---------------------------------------------------------------------------
def test_e2e_history_isolated_per_skill(e2e_gate_open):
    BUILTIN.execute("source-health-scan", {}, ticket_id="ticket-a")
    BUILTIN.execute("weekly-top-events", {"top_n": 1}, ticket_id="ticket-c")

    a_rows = SkillRunRepo().list_for_skill("source-health-scan")
    c_rows = SkillRunRepo().list_for_skill("secnews-daily-digest")
    assert all(r["skill_id"] == "source-health-scan" for r in a_rows)
    assert all(r["skill_id"] == "secnews-daily-digest" for r in c_rows)


# ---------------------------------------------------------------------------
# 8. A 类 fast_path 阶段计数=3 (INTENT→EXECUTE→COMMIT, PLAN/REFLECT SKIPPED)
# ---------------------------------------------------------------------------
def test_e2e_a_class_phase_count_is_3(e2e_gate_open):
    result = BUILTIN.execute("source-health-scan", {})
    assert result.fast_path is True
    assert result.metrics.get("phase_count") == 3


# ---------------------------------------------------------------------------
# 9. SkillRunResult 持久化 result JSON 可反序列化
# ---------------------------------------------------------------------------
def test_e2e_run_result_json_round_trip(e2e_gate_open):
    result = BUILTIN.execute("source-health-scan", {})
    row = SkillRunRepo().get(result.run_id)
    stored = row.get("result")
    assert stored is not None, "succeeded run 必须写 result"
    assert isinstance(stored, dict)
    assert "stats" in stored
    assert stored.get("running_count") is not None
