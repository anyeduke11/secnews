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
from backend.services.interest_engine_service import (
    SIGNAL_WEIGHTS,
    InterestEngineService,
    evaluate_recalibration_rules,
)


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


def _seed_ai_item(
    item_id: str = "h-ai-1",
    title: str = "大模型提示注入攻防实战",
    category: Category = Category.AI,
) -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    HotspotRepository().upsert_many([
        HotspotItem(
            id=item_id,
            title=title,
            source="test",
            url=f"https://example.com/{item_id}",
            category=category,
            published_at=now - timedelta(hours=1),
            fetched_at=now,
            ingested_at=now,
            quality_flags=[],
        )
    ])


def _set_hotspot_tags(item_id: str, tags: list[str]) -> None:
    """直写 tags 列 (HotspotItem 模型无 tags 字段, DEV-0313 归因测试专用)。"""
    import json

    from backend.repository.db import get_connection

    get_connection().execute(
        "UPDATE hotspots SET tags = ? WHERE id = ?",
        (json.dumps(tags, ensure_ascii=False), item_id),
    )


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


class TestAttribution:
    """DEV-0313 三层归因 (tags → 标题关键词 → category 粗兜底) — no_domain 补归因契约。"""

    def test_tags_beat_title(self, temp_db):
        """tags 优先于标题关键词 (与 density T1/T3 同口径) — 旧实现传空 tags 的漂移守卫。"""
        _seed_ai_item("h-attr-tags", "大模型提示注入攻防实战")  # 标题独立可判 ai_security
        _set_hotspot_tags("h-attr-tags", ["合规"])
        result = InterestEngineService().record_signal("h-attr-tags", "view")
        assert result == {"status": "recorded", "domain": "compliance"}

    def test_security_category_fallback(self, temp_db):
        """无关键词的 security 类目条目 → network_security 泛化桶 (此前静默 no_domain)。"""
        _seed_ai_item(
            "h-attr-sec",
            "打满补丁的 Windows 也能拿到 SYSTEM：MiniPlasma 与 cldflt.sys",
            Category.SECURITY,
        )
        result = InterestEngineService().record_signal("h-attr-sec", "like")
        assert result == {"status": "recorded", "domain": "network_security"}

    def test_ai_security_category_fallback(self, temp_db):
        _seed_ai_item("h-attr-aisec", "某厂商发布新推理芯片与端侧模型", Category.AI_SECURITY)
        result = InterestEngineService().record_signal("h-attr-aisec", "like")
        assert result == {"status": "recorded", "domain": "ai_security"}

    def test_non_security_category_keeps_no_domain(self, temp_db):
        """非安全类目补归因不蔓延: tech 裸条仍 no_domain (非安全内容不入权重)。"""
        _seed_ai_item("h-attr-tech", "荣耀 WIN 2 手机外观首曝：横向矩阵 Deco", Category.TECH)
        result = InterestEngineService().record_signal("h-attr-tech", "like")
        assert result["status"] == "no_domain"


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
    # DEV-0311: reaction 扩展后白名单 7 型 (like/dislike 进表)
    assert set(SIGNAL_WEIGHTS) == {
        "view", "read", "dwell", "deep_read", "favorite", "like", "dislike",
    }


# ---------------------------------------------------------------------------
# DEV-0311 — reaction (赞/踩): 互斥切换 / 可取消 / 负向归一双向 / 回读
# ---------------------------------------------------------------------------
class TestReaction:
    def test_like_recorded_and_dedup_idempotent(self, temp_db):
        """同 type 30min 内重复 = 幂等 (deduped), 表内仍 1 行 (UI 双击防噪)。"""
        _seed_ai_item()
        svc = InterestEngineService()
        assert svc.record_signal("h-ai-1", "like")["status"] == "recorded"
        assert svc.record_signal("h-ai-1", "like")["status"] == "deduped"
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT signal_type FROM interest_signals WHERE item_id = 'h-ai-1'"
        ).fetchall()
        assert [r["signal_type"] for r in rows] == ["like"]

    def test_switch_mutual_exclusion(self, temp_db):
        """like → dislike 切换: 删旧写新, 表内只余 dislike (不叠加净 +0.5)。"""
        _seed_ai_item()
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "like")
        assert svc.record_signal("h-ai-1", "dislike")["status"] == "recorded"
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT signal_type, weight FROM interest_signals WHERE item_id = 'h-ai-1'"
        ).fetchall()
        assert [(r["signal_type"], r["weight"]) for r in rows] == [("dislike", -1.5)]

    def test_clear_reaction_deletes(self, temp_db):
        _seed_ai_item()
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "like")
        assert svc.clear_reaction("h-ai-1") == {"status": "ok", "deleted": 1}
        assert svc.clear_reaction("h-ai-1") == {"status": "ok", "deleted": 0}

    def test_clear_then_like_again_not_blocked(self, temp_db):
        """取消后重新点赞: 行已删 → dedup 自然放行 (不误判 30min 内重复)。"""
        _seed_ai_item()
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "like")
        svc.clear_reaction("h-ai-1")
        assert svc.record_signal("h-ai-1", "like")["status"] == "recorded"

    def test_reactions_map_readback(self, temp_db):
        _seed_ai_item("h-ai-1", "大模型提示注入攻防实战")
        _seed_ai_item("h-th-1", "威胁狩猎方法论入门")
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "like")
        svc.record_signal("h-th-1", "dislike")
        assert svc.reactions_map() == {"h-ai-1": "like", "h-th-1": "dislike"}

    def test_like_raises_dislike_lowers_multiplier(self, temp_db):
        """混合域双向归一: like 域 b_norm=+1 抬乘子; dislike 域 b_norm=-1 压乘子。

        数值: like=+2.0, dislike=-1.5, 未勾选 e=0.15;
        pos_max=2.0/neg_max=1.5, w30=|2.0|+|-1.5|=3.5 → β_eff=0.4·3.5/30≈0.0467
        S(ai)≈0.09+0.0467=0.1367 → m≈0.782; S(th)≈0.09-0.0467=0.0433 → m≈0.726
        """
        _seed_ai_item("h-ai-1", "大模型提示注入攻防实战")
        _seed_ai_item("h-th-1", "威胁狩猎方法论入门")
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "like")
        svc.record_signal("h-th-1", "dislike")
        agg = svc.aggregate()
        assert agg["ai_security"]["behavioral_score"] == pytest.approx(1.0, abs=0.01)
        assert agg["threat_hunting"]["behavioral_score"] == pytest.approx(-1.0, abs=0.01)
        boost = svc.get_boost_map()
        baseline = 0.7 + 0.6 * (0.15 * 0.6)  # 无信号基线 m=0.754
        assert boost["ai_security"] > baseline
        assert boost["threat_hunting"] < baseline
        assert boost["compliance"] == pytest.approx(baseline, abs=0.001)
        assert boost["ai_security"] == pytest.approx(0.7 + 0.6 * (0.09 + 0.4 * 3.5 / 30), abs=0.01)

    def test_clear_reaction_restores_multiplier(self, temp_db):
        """取消后乘子回落 (invalidate_cache 生效)。"""
        _seed_ai_item()
        svc = InterestEngineService()
        svc.record_signal("h-ai-1", "dislike")
        boosted = svc.get_boost_map()
        svc.clear_reaction("h-ai-1")
        after = svc.get_boost_map()
        assert after["ai_security"] > boosted["ai_security"], "撤踩后降权应消失"


class TestReactionAPI:
    def test_post_like_and_switch_via_api(self, client, temp_db):
        _seed_ai_item("h-api-1", "威胁狩猎方法论入门")
        r1 = client.post("/api/interest/signals", json={"item_id": "h-api-1", "signal_type": "like"})
        assert r1.status_code == 200 and r1.json() == {"status": "ok", "domain": "threat_hunting"}
        r2 = client.post("/api/interest/signals", json={"item_id": "h-api-1", "signal_type": "dislike"})
        assert r2.status_code == 200

    def test_delete_reaction_endpoint(self, client, temp_db):
        _seed_ai_item("h-api-1", "威胁狩猎方法论入门")
        client.post("/api/interest/signals", json={"item_id": "h-api-1", "signal_type": "like"})
        r = client.delete("/api/interest/reactions/h-api-1")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "deleted": 1}

    def test_get_reactions_endpoint_shape(self, client, temp_db):
        _seed_ai_item("h-api-1", "威胁狩猎方法论入门")
        client.post("/api/interest/signals", json={"item_id": "h-api-1", "signal_type": "dislike"})
        r = client.get("/api/interest/reactions")
        assert r.status_code == 200
        body = r.json()
        assert body == {"items": {"h-api-1": "dislike"}, "count": 1}


# ---------------------------------------------------------------------------
# R2 (DEV-0183): 漂移检测 / 摘要 composite / repo 审计函数
# ---------------------------------------------------------------------------
from backend.domain.enums import Category as _Cat
from backend.repository.hotspot_repo import (
    interest_audit_recent_titles,
    interest_audit_signal_stats,
    interest_audit_stored_weights,
    interest_audit_w30_weight_sum,
)
from backend.services.digest_service import _sort_by_composite


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


class TestRecalibrationRules:
    """T3 重校判定规则 — 纯函数, 合成分布覆盖正反例。"""

    def test_no_evidence_no_suggestions(self):
        assert evaluate_recalibration_rules({}, {}, 0.0, 0.0) == []

    def test_r1_deviation_triggers(self):
        # 锚 9:14≈0.64; 实际 favorite:deep = 20:5 = 4.0 → 偏离远超 30%
        out = evaluate_recalibration_rules(
            {"favorite": 20, "deep_read": 5, "view": 10}, {}, 5.0, 20.0,
        )
        r1 = [s for s in out if s["rule"] == "R1_deep_read_anchor"]
        assert r1 and r1[0]["proposed"] == round(3.0 * 4.0, 1)

    def test_r1_within_anchor_no_suggestion(self):
        # 实际比 9/14 ≈ 锚 → 不建议
        out = evaluate_recalibration_rules(
            {"favorite": 9, "deep_read": 14, "view": 30}, {}, 5.0, 20.0,
        )
        assert not [s for s in out if s["rule"] == "R1_deep_read_anchor"]

    def test_r2_view_flood_triggers(self):
        # view 占 100/150=67% (>60%), 独立条目/信号 30/100=30% (<50%) → 降权
        out = evaluate_recalibration_rules(
            {"view": 100, "favorite": 30, "deep_read": 20},
            {"view": 30}, 40.0, 20.0,
        )
        r2 = [s for s in out if s["rule"] == "R2_view_damp"]
        assert r2 and r2[0]["proposed"] == 0.3

    def test_r2_healthy_view_no_suggestion(self):
        # view 占比 40% → 不触发
        out = evaluate_recalibration_rules(
            {"view": 40, "favorite": 30, "deep_read": 30},
            {"view": 35}, 40.0, 20.0,
        )
        assert not [s for s in out if s["rule"] == "R2_view_damp"]

    def test_r3_slow_evidence_triggers(self):
        # 满 14 天 W30=5 (<10) → C 降半
        out = evaluate_recalibration_rules(
            {"view": 5, "favorite": 2, "deep_read": 2}, {}, 5.0, 20.0,
        )
        r3 = [s for s in out if s["rule"] == "R3_c_constant"]
        assert r3 and r3[0]["proposed"] == 15.0

    def test_r3_within_window_no_suggestion(self):
        # 未满 14 天 → 不建议 (即便 W30 低)
        out = evaluate_recalibration_rules({"view": 5}, {}, 5.0, 7.0)
        assert not [s for s in out if s["rule"] == "R3_c_constant"]
