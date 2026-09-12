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


# ---------------------------------------------------------------------------
# R2 (DEV-0183): 漂移检测 / 摘要 composite / repo 审计函数
# ---------------------------------------------------------------------------
from backend.domain.enums import Category as _Cat  # noqa: E402
from backend.repository.hotspot_repo import (  # noqa: E402
    interest_audit_recent_titles,
    interest_audit_signal_stats,
    interest_audit_stored_weights,
    interest_audit_w30_weight_sum,
)
from backend.services.digest_service import _sort_by_composite  # noqa: E402


def _seed_domains_with_signals() -> InterestEngineService:
    """3 个域各产行为证据 (favorite)。

    注意: 同 item+type 有 30min 去重 — 每 item 多次 favorite 只落 1 条,
    故每域恰好 1 条信号、独立条目 3 个。
    """
    svc = InterestEngineService()
    seeds = [
        ("h-ai-1", "大模型提示注入攻防实战"),
        ("h-th-1", "威胁狩猎方法论入门"),
        ("h-ir-1", "应急响应演练实战复盘"),
    ]
    for hid, title in seeds:
        _seed_ai_item(item_id=hid, title=title)
        svc.record_signal(hid, "favorite")
    return svc


class TestDriftDetection:
    def test_full_overlap_not_detected(self, temp_db, monkeypatch):
        _seed_domains_with_signals()
        monkeypatch.setattr(
            SettingsRepository, "get",
            lambda self, key, default=None: (
                ["ai_security", "threat_hunting", "incident_response"]
                if key == "interest.practice_domains" else default
            ),
        )
        drift = InterestEngineService().detect_drift()
        assert drift["detected"] is False
        assert drift["overlap"] == 3

    def test_overlap_below_min_detected(self, temp_db, monkeypatch):
        _seed_domains_with_signals()
        monkeypatch.setattr(
            SettingsRepository, "get",
            lambda self, key, default=None: (
                ["ai_security"] if key == "interest.practice_domains" else default
            ),
        )
        drift = InterestEngineService().detect_drift()
        assert drift["detected"] is True
        assert drift["overlap"] == 1
        assert len(drift["behavioral_top"]) == 3

    def test_insufficient_evidence_no_drift(self, temp_db):
        """行为域不足 3 个不构成 top3 — 单一已勾选域集中行为不算偏离。"""
        _seed_ai_item(item_id="h-ai-9", title="大模型提示注入攻防实战")
        svc = InterestEngineService()
        svc.record_signal("h-ai-9", "favorite")
        drift = svc.detect_drift()
        assert len(drift["behavioral_top"]) == 1
        assert drift["detected"] is False

    def test_no_explicit_no_drift(self, temp_db):
        _seed_domains_with_signals()
        drift = InterestEngineService().detect_drift()
        assert drift["explicit_domains"] == []
        assert drift["detected"] is False

    def test_weights_api_includes_drift(self, client, temp_db):
        r = client.get("/api/interest/weights")
        assert r.status_code == 200
        drift = r.json()["drift"]
        assert drift["detected"] is False
        assert drift["overlap_min"] == 2


def _mk_item(hid: str, title: str, score: int | None) -> HotspotItem:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid, title=title, source="test", url=f"https://example.com/{hid}",
        category=_Cat.AI, published_at=now - timedelta(hours=2), fetched_at=now,
        ingested_at=now, quality_flags=[], score=score,
    )


class TestDigestComposite:
    def test_empty_map_pure_score_desc(self, temp_db, monkeypatch):
        """乘子表空 (gate 关/引擎异常) → 纯 score DESC, 与现状逐序一致。"""
        monkeypatch.setattr(
            "backend.extensions.is_extension_enabled", lambda _g: False,
        )
        a = _mk_item("d-a", "大模型提示注入攻防实战", 9)     # ai_security
        b = _mk_item("d-b", "威胁狩猎方法论入门", 12)        # threat_hunting
        assert _sort_by_composite([a, b])[0].id == "d-b"
        assert _sort_by_composite([b, a])[0].id == "d-b"

    def test_multiplier_reorders_by_composite(self, temp_db, monkeypatch):
        """勾选 ai_security: A(9 分, ai) 反超 B(12 分, threat) — 温和重排不删。"""
        monkeypatch.setattr(
            SettingsRepository, "get",
            lambda self, key, default=None: (
                ["ai_security"] if key == "interest.practice_domains" else default
            ),
        )
        a = _mk_item("d-a", "大模型提示注入攻防实战", 9)     # m≈1.06 → 9.54
        b = _mk_item("d-b", "威胁狩猎方法论入门", 12)        # m≈0.754 → 9.05
        assert _sort_by_composite([a, b])[0].id == "d-a"
        assert _sort_by_composite([b, a])[0].id == "d-a", "与输入顺序无关"
        out = _sort_by_composite([a, b])
        assert [i.id for i in out] == ["d-a", "d-b"], "两条都保留 (降权不删)"


class TestRepoAuditFunctions:
    def test_shapes_after_signals(self, temp_db):
        _seed_domains_with_signals()
        from datetime import datetime, timedelta, timezone

        # repo 语义: cutoff = 窗口起点 (过去), 统计 created_at >= cutoff 的信号
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stats = interest_audit_signal_stats(cutoff)
        assert stats["total"] == 3
        assert stats["distinct_items"] == 3
        assert stats["by_type"] == {"favorite": 3}
        assert stats["by_domain"]["ai_security"] == 1
        assert interest_audit_w30_weight_sum(cutoff) == 9.0  # 3 条 × 3.0
        InterestEngineService().aggregate(force=True)  # 权重表是聚合快照, 先触发聚合落盘
        stored = interest_audit_stored_weights()
        assert "ai_security" in stored
        assert stored["ai_security"]["behavioral_score"] > 0
        titles = interest_audit_recent_titles(10)
        assert any("大模型提示注入攻防实战" in t for t in titles)

    def test_empty_db_zero_shapes(self, temp_db):
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stats = interest_audit_signal_stats(cutoff)
        assert stats == {"total": 0, "distinct_items": 0, "by_type": {}, "by_domain": {}}
        assert interest_audit_w30_weight_sum(cutoff) == 0.0
        assert interest_audit_stored_weights() == {}
        assert interest_audit_recent_titles(5) == []
