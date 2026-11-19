"""T17 收口测试 (3 个): audit_log 端点 + LegacyMigrate API.

2026-11-19: E2E-10 启停校验 (skill_runs.version) 与 5 SSE 事件源用例随技能域
整体删除退役 — skill_runs 表 + skill_registry + skill_runner 均已移除。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.repository import db
from backend.services.legacy_migrate_service import LegacyMigrateService


@pytest.fixture()
def app_client(temp_db):
    """FastAPI app + client + initialise DB."""
    db.init_db()
    app = FastAPI()
    from backend.api._registry import register_all
    register_all(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# T16 收口 — audit_log 端点
# ---------------------------------------------------------------------------
def test_audit_log_endpoint_lists_legacy_migrate_events(app_client) -> None:
    """T16 service 写完 audit_log 后, GET /api/observability/audit 返 ≥1 行."""
    # 直接走 service 写 audit_log
    svc = LegacyMigrateService()
    svc.run(apply=True)
    r = app_client.get("/api/observability/audit?action=knowledge.legacy_migrated&limit=50")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["action"] == "knowledge.legacy_migrated"
        # C13 起 T16 service 全权委托 legacy_migrate_v1.migrate_seed(),
        # audit actor 由委托方写入 — 故断言 c13_legacy_migrate (非 t16)
        assert item["actor"] == "c13_legacy_migrate"


def test_audit_log_endpoint_filters_by_action(app_client) -> None:
    """?action=knowledge.legacy_migrated 返知识迁移审计 (T16 apply 后 ≥ 15)."""
    svc = LegacyMigrateService()
    svc.run(apply=True)
    r = app_client.get("/api/observability/audit?action=knowledge.legacy_migrated&limit=50")
    assert r.status_code == 200
    assert r.json()["total"] >= 15


# ---------------------------------------------------------------------------
# T16 收口 — LegacyMigrate API
# ---------------------------------------------------------------------------
def test_legacy_migrate_api_dry_run(app_client) -> None:
    """POST /api/dsh/legacy/migrate/run?apply=false → dry-run 计数."""
    r = app_client.post("/api/dsh/legacy/migrate/run?apply=false")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "dry-run"
    assert body["result"]["knowledge_candidates"] == 15
