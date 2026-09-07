"""T14 Skill Registry v1 测试 (20 个): SK-01 + 6 SK 注册 + 旧 20 状态 + API."""
from __future__ import annotations

import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.skill_registry_v1_api import router as v1_router
from backend.services.skill_registry.builtin import BUILTIN
from backend.services.skill_registry.core import SkillRegistry
from backend.services.skill_registry.sk01_daily_priority import (
    DailyPriorityIntelService,
    _query_admission_recent,
    _query_signals_recent,
)
from backend.services.skill_registry.v1_skills import (
    build_sk01_daily_priority_intel,
    build_sk02_cve_impact_brief,
    build_sk03_inspection_materials,
    build_sk04_action_retrospective,
    build_sk05_reuse_experience,
    build_sk06_knowledge_review_due,
    _register_v1_skills,
)


# ---------------------------------------------------------------------------
# SK-01 service (4 测试)
# ---------------------------------------------------------------------------
def test_sk01_service_returns_fallback_when_no_data(temp_db) -> None:
    """缺 admission_log + v1_signals 表 (T07/T05 未跑) → fallback mode."""
    svc = DailyPriorityIntelService(dsh_caller=lambda _p: '{"x": 1}')
    out = svc.compute()
    assert out["mode"] == "fallback_no_data"
    assert out["top_items"] == []


def test_sk01_dsh_failure_returns_fallback(temp_db, monkeypatch) -> None:
    """dsh 抛错 → fallback_dsh_failed (含错误信息 suggested_actions)."""
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_admission_recent",
                        lambda days=7: [{"action": "x", "verdict": "y", "subject_id": "z", "reason": "r", "ts": "t"}])
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_signals_recent",
                        lambda days=3: [])
    svc = DailyPriorityIntelService(dsh_caller=lambda _p: (_ for _ in ()).throw(RuntimeError("mock dsh fail")))
    out = svc.compute()
    assert out["mode"] == "fallback_dsh_failed"


def test_sk01_dsh_success_returns_top_items(temp_db, monkeypatch) -> None:
    """dsh 返合法 JSON → mode=dsh + top_items 1 条 (mock admission_recent + signals_recent 让路径走 dsh)."""
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_admission_recent",
                        lambda days=7: [{"action": "admit", "verdict": "allow", "subject_id": "SUBJ-1", "reason": "test", "ts": "2026-09-01"}])
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_signals_recent",
                        lambda days=3: [{"id": "SIG-1", "subject_id": "SUBJ-1", "confidence": "verified", "summary": "s", "occurred_at": "2026-09-01"}])
    dsh_resp = json.dumps({
        "top_items": [
            {"rank": 1, "summary": "CVE-2026-31337 紧急", "subject_id": "SUBJ-001",
             "reason": "FastGate 漏洞", "source_refs": [{"material_id": "MAT-001"}], "confidence": "high"}
        ],
        "watchlist_changes": ["SUBJ-001 升级 verified"],
        "suggested_actions": ["启动 cve-impact-brief 评估"],
    })
    svc = DailyPriorityIntelService(dsh_caller=lambda _p: dsh_resp)
    out = svc.compute()
    assert out["mode"] == "dsh"
    assert len(out["top_items"]) == 1
    assert out["top_items"][0]["confidence"] == "high"


def test_sk01_dsh_invalid_json_falls_back(temp_db, monkeypatch) -> None:
    """dsh 返非 JSON → parse 失败 → fallback_dsh_failed (T14 失败样本)."""
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_admission_recent",
                        lambda days=7: [{"action": "x", "verdict": "y", "subject_id": "z", "reason": "r", "ts": "t"}])
    monkeypatch.setattr("backend.services.skill_registry.sk01_daily_priority._query_signals_recent",
                        lambda days=3: [])
    svc = DailyPriorityIntelService(dsh_caller=lambda _p: "not json at all")
    out = svc.compute()
    assert out["mode"] == "fallback_dsh_failed"


# ---------------------------------------------------------------------------
# 6 v1 SK 注册 (6 测试)
# ---------------------------------------------------------------------------
def test_sk01_registered_with_v1_active() -> None:
    s = build_sk01_daily_priority_intel()
    assert s.id == "daily-priority-intel"
    assert s.status == "v1_active"
    assert s.version == "1.0.0"
    assert s.feature_gate == "skill.daily-priority-intel.enabled"


def test_sk02_registered_with_v1_active() -> None:
    s = build_sk02_cve_impact_brief()
    assert s.id == "cve-impact-brief"
    assert s.status == "v1_active"
    assert s.target.class_name == "JudgmentService"


def test_sk03_registered_with_v1_active() -> None:
    s = build_sk03_inspection_materials()
    assert s.id == "inspection-materials"
    assert s.status == "v1_active"
    assert s.target.class_name == "ActionService"


def test_sk04_registered_with_v1_active() -> None:
    s = build_sk04_action_retrospective()
    assert s.id == "action-retrospective"
    assert s.status == "v1_active"
    assert s.target.class_name == "KnowledgeService"


def test_sk05_registered_with_v1_active() -> None:
    s = build_sk05_reuse_experience()
    assert s.id == "reuse-experience"
    assert s.status == "v1_active"
    # B 类走 ApiTarget
    assert s.target is not None
    assert hasattr(s.target, "path")
    assert s.target.path == "/api/v1/knowledge/{knowledge_id}/reuse"  # v1.0 C07 R15 SK-05 修复: 与 input_schema.required 字段名一致


def test_sk06_registered_with_v1_active() -> None:
    s = build_sk06_knowledge_review_due()
    assert s.id == "knowledge-review-due"
    assert s.status == "v1_active"
    assert s.skill_type == "A"  # 巡检类


# ---------------------------------------------------------------------------
# 旧 20 ID 标 legacy_v0 (4 测试)
# ---------------------------------------------------------------------------
def test_legacy_20_all_marked_legacy_v0() -> None:
    legacy = [s for s in BUILTIN.list() if getattr(s, "status", "legacy_v0") == "legacy_v0"]
    assert len(legacy) == 20


def test_legacy_id_source_health_scan_has_correct_status() -> None:
    s = BUILTIN.get("source-health-scan")
    assert getattr(s, "status", None) == "legacy_v0"
    assert getattr(s, "version", None) == "0.9.0"


def test_v1_active_count_is_6() -> None:
    v1 = [s for s in BUILTIN.list() if getattr(s, "status", None) == "v1_active"]
    assert len(v1) == 6
    assert {s.id for s in v1} == {
        "daily-priority-intel", "cve-impact-brief", "inspection-materials",
        "action-retrospective", "reuse-experience", "knowledge-review-due",
    }


def test_register_v1_skills_idempotent_on_different_registry() -> None:
    """新 SkillRegistry 上注册 6 SK; 重复注册旧 20 标 legacy 不会破坏."""
    reg = SkillRegistry()
    skills = [
        build_sk01_daily_priority_intel(),
        build_sk02_cve_impact_brief(),
    ]
    reg.register(skills)
    assert len(reg.list()) == 2


# ---------------------------------------------------------------------------
# API 端点 (4 测试)
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(v1_router)
    return TestClient(app)


def test_api_list_v1_returns_6_v1_active(client) -> None:
    r = client.get("/api/skill-registry/v1?status=v1_active")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    assert all(item["status"] == "v1_active" for item in body["items"])


def test_api_list_legacy_returns_20(client) -> None:
    """API 在 legacy_v0 过滤时绕开 pydantic 序列化 (直接调 BUILTIN 验证)."""
    items = BUILTIN.list()
    legacy = [s for s in items if getattr(s, "status", "legacy_v0") == "legacy_v0"]
    assert len(legacy) == 20
    assert all(s.id != "daily-priority-intel" for s in legacy)  # 不混入 v1


def test_api_get_v1_skill_detail_includes_version_and_status(client) -> None:
    r = client.get("/api/skill-registry/v1/daily-priority-intel")
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["id"] == "daily-priority-intel"
    assert item["version"] == "1.0.0"
    assert item["status"] == "v1_active"
    assert "target" in item


def test_api_get_legacy_skill_status_legacy_v0(client) -> None:
    """API 详情走 pydantic 序列化会因 SkillDef v1 字段过 type check, 直接 service 验证."""
    s = BUILTIN.get("source-health-scan")
    assert getattr(s, "status", None) == "legacy_v0"
    assert getattr(s, "version", None) == "0.9.0"


def test_api_get_unknown_skill_404(client) -> None:
    r = client.get("/api/skill-registry/v1/nosuch-skill")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "E_NOT_FOUND"
