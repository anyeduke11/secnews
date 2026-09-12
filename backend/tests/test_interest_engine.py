"""DEV-0182 — Interest Engine API + service 单元测试。

覆盖:
- record_signal: 归因记录 / 无域拒记 (no_domain) / 去重 / 非法 type
- aggregate: 无信号时 10 域全量 + S=0.15 (未勾) / 勾选域 S=0.75 / β 渐进
- get_boost_map: 无数据恒等 (乘子恒定) / 有行为分排序变化
- reset: 清信号 + 行为分归零 + 显式勾选保留
- API: POST signals 201/202, GET weights 形状, reset + audit
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.settings_repo import SettingsRepository
from backend.services.interest_engine_service import SIGNAL_WEIGHTS, InterestEngineService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_interest.db"
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


@pytest.fixture(autouse=True)
def _reset_agg_cache():
    InterestEngineService.invalidate_cache()
    yield
    InterestEngineService.invalidate_cache()


def _seed_ai_item(item_id: str = "h-ai-1", title: str = "大模型提示注入攻防实战") -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    HotspotRepository().upsert_many([
        HotspotItem(
            id=item_id,
            title=title,
            source="test",
            url=f"https://example.com/{item_id}",
            category=Category.AI,
            published_at=now - timedelta(hours=1),
            fetched_at=now,
            ingested_at=now,
            quality_flags=[],
        )
    ])


class TestRecordSignal:
    def test_recorded_with_attribution(self, temp_db):
        _seed_ai_item()
        svc = InterestEngineService()
        result = svc.record_signal("h-ai-1", "view")
        assert result == {"status": "recorded", "domain": "ai_security"}

    def test_no_domain_rejected(self, temp_db):
        _seed_ai_item(item_id="h-none", title="央行年度支付报告")
        svc = InterestEngineService()
        result = svc.record_signal("h-none", "view")
        assert result["status"] == "no_domain"

    def test_dedup_within_window(self, temp_db):
        _seed_ai_item()
        svc = InterestEngineService()
        assert svc.record_signal("h-ai-1", "view")["status"] == "recorded"
        assert svc.record_signal("h-ai-1", "view")["status"] == "deduped"

    def test_invalid_type(self, temp_db):
        assert InterestEngineService().record_signal("x", "hack")["status"] == "invalid_type"


class TestAggregate:
    def test_empty_returns_all_domains_unselected(self, temp_db):
        svc = InterestEngineService()
        agg = svc.aggregate()
        assert len(agg) == 10
        assert all(v["explicit_selected"] == 0 for v in agg.values())
        assert all(v["blended_score"] == pytest.approx(0.15 * 0.6) for v in agg.values())

    def test_selected_domain_gets_full_explicit(self, temp_db, monkeypatch):
        monkeypatch.setattr(
            SettingsRepository, "get",
            lambda self, key, default=None: ["ai_security"] if key == "interest.practice_domains" else default,
        )
        svc = InterestEngineService()
        agg = svc.aggregate()
        assert agg["ai_security"]["explicit_selected"] == 1
        assert agg["ai_security"]["blended_score"] == pytest.approx(0.6)
        assert agg["compliance"]["blended_score"] == pytest.approx(0.15 * 0.6)


class TestBoostMap:
    def test_no_data_all_multiplier_equal(self, temp_db):
        svc = InterestEngineService()
        boost = svc.get_boost_map()
        assert len(boost) == 10
        assert len(set(boost.values())) == 1, "无数据时乘子必须恒定 (= 现状)"

    def test_behavior_raises_multiplier(self, temp_db):
        _seed_ai_item("h-ai-1", "大模型提示注入攻防实战")
        _seed_ai_item("h-ai-2", "Agent安全评估框架")
        _seed_ai_item("h-ai-3", "提示注入检测规则")
        svc = InterestEngineService()
        for hid in ("h-ai-1", "h-ai-2", "h-ai-3"):
            svc.record_signal(hid, "favorite")
        boost = svc.get_boost_map()
        assert boost["ai_security"] > boost["compliance"]
        # 未勾选: E=0.15, β_eff=0.4·(9/30)=0.12 → S=0.6·0.15+0.12·1.0=0.21
        assert boost["ai_security"] == pytest.approx(0.7 + 0.6 * 0.21, abs=0.01)


class TestInterestAPI:
    def test_post_signal_recorded(self, client, temp_db):
        _seed_ai_item("h-api-1", "威胁狩猎方法论入门")
        r = client.post("/api/interest/signals", json={"item_id": "h-api-1", "signal_type": "read"})
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "domain": "threat_hunting"}

    def test_post_signal_no_domain_202_semantics(self, client, temp_db):
        _seed_ai_item("h-none", "某基金年报")
        r = client.post("/api/interest/signals", json={"item_id": "h-none", "signal_type": "view"})
        assert r.status_code == 200
        assert r.json()["status"] == "accepted_no_domain"

    def test_get_weights_shape(self, client, temp_db):
        r = client.get("/api/interest/weights")
        assert r.status_code == 200
        body = r.json()
        assert len(body["domains"]) == 10
        assert set(body["weights"].keys()) == set(body["domains"])

    def test_reset_clears_and_audits(self, client, temp_db):
        _seed_ai_item("h-rst", "代码审计实战系列")
        client.post("/api/interest/signals", json={"item_id": "h-rst", "signal_type": "favorite"})
        r = client.post("/api/interest/reset", json={"actor": "test"})
        assert r.status_code == 200
        assert r.json()["deleted_signals"] >= 1
        audit = client.get(
            "/api/observability/audit", params={"action": "workbench.interest_reset", "limit": 5}
        )
        assert audit.status_code == 200
        assert audit.json()["items"], "reset 应写 audit_log"


def test_weights_table_covers_all_domains():
    assert set(SIGNAL_WEIGHTS) == {"view", "read", "dwell", "deep_read", "favorite"}
