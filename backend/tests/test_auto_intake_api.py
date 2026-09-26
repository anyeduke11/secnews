"""自动入管配置 API 测试 (2026-09-26, design docs/superpowers/specs/2026-09-26-auto-intake-design.md §3.1)。

覆盖:
- GET /api/settings/auto-intake 默认配置 + today_intaken=0
- PATCH 部分更新 → GET 回读一致 (R3: api 经 service 写 kv)
- PATCH 校验: min_quality_score 0-100 / daily_limit 1-100, 越界 400
- PATCH 落 audit_log (action=auto_intake.config.set, 经 /api/observability/audit 断言)
- today_intaken 反映 source='secnews_auto' 实时计数 (收藏通道不计入)

执行: .venv/bin/python3 -m pytest backend/tests/test_auto_intake_api.py -v
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.knowledge_repo import knowledge_repo

_AUDIT_ACTION = "auto_intake.config.set"


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_auto_intake_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestAutoIntakeAPI:
    def test_get_default_config(self, client):
        """GET 默认: 关闭 / 85 / 20 / 要求域命中 / 今日 0。"""
        r = client.get("/api/settings/auto-intake")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "enabled": False,
            "min_quality_score": 85,
            "daily_limit": 20,
            "require_domain_hit": True,
            "today_intaken": 0,
        }

    def test_patch_partial_then_get_roundtrip(self, client):
        """PATCH 部分字段 → GET 回读一致 (未传字段不动)。"""
        r = client.patch(
            "/api/settings/auto-intake",
            json={"enabled": True, "min_quality_score": 90, "actor": "test"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["min_quality_score"] == 90
        assert body["daily_limit"] == 20  # 未传 → 保持默认
        assert body["require_domain_hit"] is True

        r2 = client.get("/api/settings/auto-intake")
        assert r2.json()["enabled"] is True
        assert r2.json()["min_quality_score"] == 90

    def test_patch_rejects_score_out_of_range(self, client):
        """越界 → 422 (FastAPI/Pydantic 校验契约, 与 refresh-interval 同)。"""
        r = client.patch(
            "/api/settings/auto-intake", json={"min_quality_score": 101}
        )
        assert r.status_code == 422
        r2 = client.patch(
            "/api/settings/auto-intake", json={"min_quality_score": -1}
        )
        assert r2.status_code == 422

    def test_patch_rejects_limit_out_of_range(self, client):
        r = client.patch("/api/settings/auto-intake", json={"daily_limit": 0})
        assert r.status_code == 422
        r2 = client.patch("/api/settings/auto-intake", json={"daily_limit": 101})
        assert r2.status_code == 422

    def test_patch_writes_audit_log(self, client):
        client.patch(
            "/api/settings/auto-intake",
            json={"enabled": True, "actor": "audit-test"},
        )
        r = client.get(
            "/api/observability/audit", params={"action": _AUDIT_ACTION, "limit": 5}
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "audit_log 未写入 auto_intake.config.set"
        latest = items[0]
        assert latest["actor"] == "audit-test"
        assert latest["target"] == "enabled"

    def test_today_intaken_counts_auto_source_only(self, client):
        """today_intaken = 实时 COUNT source='secnews_auto'; 收藏通道不计入。"""
        now = now_iso()
        knowledge_repo.upsert_item(
            KnowledgeItem(
                id="auto-1", title="A", source="secnews_auto",
                ingested_at=now, updated_at=now,
            )
        )
        knowledge_repo.upsert_item(
            KnowledgeItem(
                id="fav-1", title="B", source="secnews",
                ingested_at=now, updated_at=now,
            )
        )
        r = client.get("/api/settings/auto-intake")
        assert r.status_code == 200
        assert r.json()["today_intaken"] == 1
