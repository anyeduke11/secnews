"""DEV-0316 — 内容偏好自动推导 (统计兜底) + 手动覆盖合并 + advisor 测试。

测试意图 (Rule 9):
- 自动推导是"零配置就有效果"的核心 — 用户信号 (赞/踩) 达阈值必须自动改变
  feed 排序, 不等用户去设置页动手;
- 手动优先于自动 — 用户显式覆盖 (含把自动降权的改回 more) 必须生效;
- 证据不足不自动设 — 单次误触不应产生偏好;
- advisor 建议不自动生效 (人主律) — LLM 输出经枚举/level 校验, 失败降级不抛。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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
from backend.services import content_pref_advisor as cpa
from backend.services import hotspot_service as hs


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_pref_auto.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def _clear_caches():
    from backend.cache import list_cache

    list_cache.clear()
    hs.invalidate_auto_content_preferences()
    yield
    list_cache.clear()
    hs.invalidate_auto_content_preferences()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


def _mk(
    hid: str, category: Category, source: str = "test",
    title: str | None = None, hours_ago: int = 0,
) -> HotspotItem:
    # 标题默认含安全关键词 — 保证 record_signal 域归因成功 (no_domain 会被丢弃)
    now = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return HotspotItem(
        id=hid, title=title or f"某组件曝出漏洞 {hid}", source=source,
        url=f"https://example.com/{hid}", category=category,
        published_at=now, fetched_at=now, ingested_at=now, quality_flags=[],
    )


def _seed(temp_db, items: list[HotspotItem]) -> None:
    HotspotRepository().upsert_many(items)


class TestStatsByAxis:
    def test_invalid_axis_raises(self, temp_db):
        from backend.repository.hotspot_repo import interest_signal_stats_by_axis

        with pytest.raises(ValueError, match="invalid axis"):
            interest_signal_stats_by_axis("drop TABLE", "2020-01-01")

    def test_aggregates_signed_net(self, temp_db):
        from backend.repository.hotspot_repo import interest_signal_stats_by_axis
        from backend.services.interest_engine_service import InterestEngineService

        _seed(temp_db, [
            _mk("t1", Category.TECH), _mk("t2", Category.TECH), _mk("t3", Category.TECH),
            _mk("s1", Category.SECURITY),
        ])
        svc = InterestEngineService()
        for hid in ("t1", "t2", "t3"):
            svc.record_signal(hid, "dislike")  # -1.5 × 3 = -4.5 tech
        svc.record_signal("s1", "like")        # +2.0 security
        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stats = interest_signal_stats_by_axis("category", since)
        assert stats["tech"]["net"] == pytest.approx(-4.5)
        assert stats["tech"]["events"] == 3
        assert stats["security"]["net"] == pytest.approx(2.0)

    def test_unattributed_reaction_excluded(self, temp_db):
        """DEV-0326 唯一泄漏面守卫: 无域条目 reaction (哨兵域 weight 0) 不得进 axis stats
        — 否则 weight=0 行会 +1 events, 凭"证据量"触发 more/less 门限、污染排序。"""
        from backend.repository.hotspot_repo import interest_signal_stats_by_axis
        from backend.services.interest_engine_service import InterestEngineService

        # 非安全标题 + TECH 类目 → 归因 None → reaction 落哨兵域
        _seed(temp_db, [
            _mk("u1", Category.TECH, title="荣耀 WIN 2 手机外观首曝：横向矩阵 Deco"),
            _mk("u2", Category.TECH, title="新款智能手表开箱图赏"),
        ])
        svc = InterestEngineService()
        for hid in ("u1", "u2"):
            assert svc.record_signal(hid, "dislike")["status"] == "recorded"

        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stats = interest_signal_stats_by_axis("category", since)
        assert "tech" not in stats, f"无域 reaction 不应进 axis stats: {stats}"


class TestAutoDerivation:
    def test_thresholds_more_and_less(self, temp_db, monkeypatch):
        # 直接测纯函数 (不依赖 DB): 净分越阈 + 证据下限
        stats = {
            "tech": {"net": -4.5, "events": 3},   # ≤ -1.5 → less
            "ai": {"net": 4.0, "events": 4},      # ≥ +3 → more
            "finance": {"net": 2.0, "events": 10},  # 净分未达 +3 → 不设
            "github": {"net": -9.0, "events": 2},  # 证据不足 (<3) → 不设
        }
        assert hs._level_from_stats(stats) == {"tech": "less", "ai": "more"}

    def test_derive_from_signals(self, temp_db):
        _seed(temp_db, [
            _mk("t1", Category.TECH), _mk("t2", Category.TECH), _mk("t3", Category.TECH),
            _mk("a1", Category.AI), _mk("a2", Category.AI),
        ])
        from backend.services.interest_engine_service import InterestEngineService

        svc = InterestEngineService()
        for hid in ("t1", "t2", "t3"):
            svc.record_signal(hid, "dislike")
        for hid in ("a1", "a2"):
            svc.record_signal(hid, "favorite")  # +3 × 2 = 6, events 2 < 3 → 证据不足
        prefs = hs.derive_auto_content_preferences(force=True)
        assert prefs.get("categories", {}).get("tech") == "less"
        assert "ai" not in prefs.get("categories", {}), "events=2 不足下限不该自动设"

    def test_effective_manual_overrides_auto(self, temp_db, monkeypatch):
        monkeypatch.setattr(hs, "derive_auto_content_preferences", lambda **kw: {
            "categories": {"tech": "less", "ai": "more"},
        })
        from backend.repository.settings_repo import SettingsRepository

        SettingsRepository().set(hs.CONTENT_PREF_KEY, {"categories": {"tech": "more"}})
        eff = hs.effective_content_preferences()
        # 手动 key 级覆盖: tech 以手动 more 为准; ai 沿用自动
        assert eff["categories"] == {"tech": "more", "ai": "more"}


class TestFeedIntegration:
    """零配置生效: 只有信号没有手动设置, feed 排序也必须变 (核心卖点)。"""

    def _balanced_ids(self, client, limit: int = 10) -> list[str]:
        r = client.get("/api/hotspots", params={"time_range": "30d", "limit": limit})
        assert r.status_code == 200
        return [i["id"] for i in r.json()["items"]]

    def test_signals_alone_rerank_feed(self, client, temp_db):
        items = (
            [_mk(f"ai{i:02d}", Category.AI, source="FreeBuf", title=f"大模型安全评估 ai{i:02d}", hours_ago=i) for i in range(1, 11)]
            + [_mk(f"se{i:02d}", Category.SECURITY, source="FreeBuf", hours_ago=i) for i in range(1, 11)]
        )
        _seed(temp_db, items)
        base_ai = sum(1 for i in self._balanced_ids(client) if i.startswith("ai"))
        assert base_ai > 0

        from backend.services.interest_engine_service import InterestEngineService

        svc = InterestEngineService()
        for i in range(1, 8):
            svc.record_signal(f"ai{i:02d}", "dislike")  # 7×-1.5=-10.5, events 7 → ai=less 自动
        hs.invalidate_auto_content_preferences()
        less_ai = sum(1 for i in self._balanced_ids(client) if i.startswith("ai"))
        assert less_ai < base_ai, f"仅凭信号未做任何设置, AI 也应被自动降权: {base_ai} → {less_ai}"


class TestAPI:
    def test_get_exposes_three_views(self, client, temp_db):
        from backend.repository.settings_repo import SettingsRepository

        SettingsRepository().set(hs.CONTENT_PREF_KEY, {"categories": {"tech": "more"}})
        hs.invalidate_auto_content_preferences()
        body = client.get("/api/settings/content-preferences").json()
        assert body["preferences"]["categories"] == {"tech": "more"}
        assert "auto_preferences" in body and "effective_preferences" in body
        assert body["effective_preferences"]["categories"]["tech"] == "more"

    def test_patch_invalidates_auto_cache(self, client, temp_db):
        r = client.patch(
            "/api/settings/content-preferences",
            json={"categories": {"tech": "less"}, "actor": "test"},
        )
        assert r.status_code == 200
        # 写后 effective 立即含手动项 (缓存已清, 重算反映覆盖)
        eff = client.get("/api/settings/content-preferences").json()["effective_preferences"]
        assert eff["categories"]["tech"] == "less"


class TestAdvisor:
    def test_parse_reply_json_fence(self):
        raw = '```json\n{"categories": {"tech": "less"}, "sources": {"IT之家": "less"}, "reasons": {"tech": "杂讯多"}}\n```'
        parsed = cpa._parse_reply(raw)
        assert parsed["categories"] == {"tech": "less"}
        assert parsed["reasons"]["tech"] == "杂讯多"

    def test_parse_reply_rejects_garbage(self):
        with pytest.raises(ValueError):
            cpa._parse_reply("not json at all")
        with pytest.raises(ValueError):
            cpa._parse_reply("")

    def test_clean_axis_enums_and_caps(self):
        valid_cats = {"tech", "ai"}
        # 越界类目丢弃 / 非法 level 丢弃 / normal 不算建议 / 每轴 ≤5
        table = {
            "tech": "less", "ai": "more", "bogus": "less",
            "x1": "normal", "x2": "banish",
            "a": "more", "b": "more", "c": "more", "d": "more", "e": "more", "f": "more",
        }
        out = cpa._clean_axis(table, valid_cats)
        assert out == {"tech": "less", "ai": "more"}
        out_src = cpa._clean_axis(
            {f"s{i}": "more" for i in range(10)}, None
        )
        assert len(out_src) == cpa._MAX_PER_AXIS

    def test_get_suggestions_llm_failure_degrades(self, temp_db, monkeypatch):
        async def _boom(*a, **kw):
            raise RuntimeError("llm down")

        monkeypatch.setattr(cpa._ai_hub_mod.llm_service, "generate", _boom)
        result = _run(cpa.get_suggestions(force=True))
        assert result["categories"] == {} and result["sources"] == {}
        assert "llm down" in result["note"]

    def test_get_suggestions_success_validates_and_caches(self, temp_db, monkeypatch):
        async def _ok(prompt, **kw):
            return json.dumps({
                "categories": {"tech": "less", "not_a_cat": "more"},
                "sources": {"IT之家": "less"},
                "reasons": {"tech": "杂讯", "IT之家": "重复转载"},
            })

        monkeypatch.setattr(cpa._ai_hub_mod.llm_service, "generate", _ok)
        result = _run(cpa.get_suggestions(force=True))
        assert result["categories"] == {"tech": "less"}  # 越界类目被校验丢弃
        assert result["sources"] == {"IT之家": "less"}
        assert result["note"] == ""
        # 二次调用命中缓存 (不再打 LLM)
        calls = {"n": 0}

        async def _count(prompt, **kw):
            calls["n"] += 1
            return "{}"

        monkeypatch.setattr(cpa._ai_hub_mod.llm_service, "generate", _count)
        again = _run(cpa.get_suggestions(force=False))
        assert again["categories"] == {"tech": "less"}
        assert calls["n"] == 0


def _run(coro):
    import asyncio

    return asyncio.run(coro)
