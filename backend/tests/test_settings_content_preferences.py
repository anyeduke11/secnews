"""DEV-0315 — 内容偏好 (类目/来源) 第二轴 API + 排序测试 (A+B 整合, 归拢设置)。

覆盖:
- GET 默认空偏好 + valid_categories/levels/available_sources 结构
- PATCH → GET 回读一致; normal 不落库 (等价缺省)
- PATCH 未知类目 → 400; 非法 level → 400
- PATCH 落 audit_log (经 /api/observability/audit 只读端点断言)
- 复合排序: 类目 less 下沉 / more 上浮; 来源 less 下沉; 无配置时顺序不变 (兼容铁律)
"""
from __future__ import annotations

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
from backend.services.hotspot_service import (
    HotspotService,
    _norm_content_preferences,
    content_preference_signature,
)

_AUDIT_ACTION = "feed.content_prefs.set"


@pytest.fixture(autouse=True)
def _clear_list_cache():
    """list_cache 是模块级共享 TTL 缓存, 同 key 跨测试会命中脏结果 (同 test_hotspots_api 先例)。

    排序用例尤其敏感: 缓存键含偏好指纹, 但基线 (无偏好) 键跨测试相同。
    """
    from backend.cache import list_cache as _list_cache

    _list_cache.clear()
    yield
    _list_cache.clear()


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_content_prefs.db"
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


def _mk(
    hid: str,
    category: Category,
    source: str = "test",
    hours_ago: int = 1,
) -> HotspotItem:
    """标题刻意不含任何实践域关键词 — 隔离出「类目/来源」这一根轴。"""
    now = datetime.now(timezone.utc)
    t = now - timedelta(hours=hours_ago)
    return HotspotItem(
        id=hid,
        title=f"常规事项 {hid}",
        source=source,
        url=f"https://example.com/{hid}",
        category=category,
        published_at=t,
        fetched_at=t,
        ingested_at=t,
        quality_flags=[],
    )


def _seed_three(temp_db):
    """h1(tech,1h) h2(security,2h) h3(tech,3h) — 基准时序 h1 > h2 > h3。"""
    HotspotRepository().upsert_many([
        _mk("h1", Category.TECH, source="IT之家", hours_ago=1),
        _mk("h2", Category.SECURITY, source="FreeBuf", hours_ago=2),
        _mk("h3", Category.TECH, source="FreeBuf", hours_ago=3),
    ])


def _order(prefs: dict | None = None) -> list[str]:
    """以 cursor='' 关闭 balanced 模式, 拿到纯时序基线后可断言偏好重排。"""
    res = HotspotService().list_hotspots(
        category="all",
        time_range="30d",
        cursor="",
        limit=50,
        content_preferences=prefs,
    )
    return [i["id"] for i in res["items"]]


class TestContentPreferencesAPI:
    def test_get_default_empty(self, client):
        r = client.get("/api/settings/content-preferences")
        assert r.status_code == 200
        body = r.json()
        assert body["preferences"] == {"categories": {}, "sources": {}}
        assert set(body["valid_categories"]) == {c.value for c in Category}
        assert body["levels"] == ["more", "normal", "less"]
        assert body["available_sources"] == []

    def test_patch_then_get_roundtrip(self, client):
        payload = {"categories": {"tech": "less"}, "sources": {"IT之家": "more"}}
        r = client.patch("/api/settings/content-preferences", json=payload)
        assert r.status_code == 200
        assert r.json()["preferences"] == payload

        got = client.get("/api/settings/content-preferences").json()["preferences"]
        assert got == payload

    def test_patch_strips_normal(self, client):
        r = client.patch(
            "/api/settings/content-preferences",
            json={"categories": {"tech": "normal", "ai": "more"}, "sources": {}},
        )
        assert r.status_code == 200
        # normal = 等价缺省 → 不落库
        assert r.json()["preferences"] == {"categories": {"ai": "more"}}

    def test_patch_unknown_category_rejected(self, client):
        r = client.patch(
            "/api/settings/content-preferences",
            json={"categories": {"crypto_trading": "less"}},
        )
        assert r.status_code == 400
        assert "unknown categories" in str(r.json())

    def test_patch_invalid_level_rejected(self, client):
        r = client.patch(
            "/api/settings/content-preferences",
            json={"categories": {"tech": "banish"}},
        )
        assert r.status_code == 400
        assert "invalid levels" in str(r.json())

    def test_patch_writes_audit_log(self, client, temp_db):
        client.patch(
            "/api/settings/content-preferences",
            json={"categories": {"tech": "less"}, "actor": "audit-test"},
        )
        r = client.get("/api/observability/audit", params={"action": _AUDIT_ACTION, "limit": 5})
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "audit_log 未写入 feed.content_prefs.set"
        assert items[0]["actor"] == "audit-test"
        assert items[0]["target"] == "interest.content_preferences"


class TestNormHelpers:
    def test_norm_strips_normal_and_bad_levels(self):
        raw = {
            "categories": {"tech": "less", "ai": "normal", "x": "bogus"},
            "sources": {"IT之家": "more", "": "less"},
            "other": {"ignored": "more"},
        }
        assert _norm_content_preferences(raw) == {
            "categories": {"tech": "less"},
            "sources": {"IT之家": "more"},
        }

    def test_norm_handles_garbage(self):
        assert _norm_content_preferences(None) == {}
        assert _norm_content_preferences("nope") == {}
        assert _norm_content_preferences({"categories": []}) == {}

    def test_signature_stable_and_order_insensitive(self):
        a = {"categories": {"ai": "more", "tech": "less"}}
        b = {"categories": {"tech": "less", "ai": "more"}}
        assert content_preference_signature(a) == content_preference_signature(b)
        assert content_preference_signature({}) == ""
        assert content_preference_signature(a) != content_preference_signature(
            {"categories": {"ai": "less", "tech": "more"}}
        )


class TestCompositeOrdering:
    def test_no_prefs_keeps_base_order(self, temp_db):
        _seed_three(temp_db)
        assert _order(None) == ["h1", "h2", "h3"]

    def test_category_less_sinks(self, temp_db):
        _seed_three(temp_db)
        # tech(h1,h3) 降到 0.78; security(h2) 保持 1.0 → h2 上浮
        assert _order({"categories": {"tech": "less"}}) == ["h2", "h1", "h3"]

    def test_category_more_floats(self, temp_db):
        _seed_three(temp_db)
        # tech 升到 1.15 → tech 两条(h1,h3)领先, 段内保原序
        assert _order({"categories": {"tech": "more"}}) == ["h1", "h3", "h2"]

    def test_source_less_sinks(self, temp_db):
        _seed_three(temp_db)
        # IT之家(h1) 降到 0.78 → 两条 FreeBuf(h2,h3) 上浮
        assert _order({"sources": {"IT之家": "less"}}) == ["h2", "h3", "h1"]

    def test_category_and_source_compose(self, temp_db):
        _seed_three(temp_db)
        # tech×less(0.78) 且 IT之家×more(1.15): h1=0.78*1.15=0.897; h3=0.78; h2=1.0
        assert _order({
            "categories": {"tech": "less"},
            "sources": {"IT之家": "more"},
        }) == ["h2", "h1", "h3"]

    def test_prefs_cache_key_isolated(self, temp_db):
        """不同偏好 → 不同缓存键, 不互相污染 (同进程连续两次调用)。"""
        _seed_three(temp_db)
        assert _order({"categories": {"tech": "less"}}) == ["h2", "h1", "h3"]
        assert _order({"categories": {"tech": "more"}}) == ["h1", "h3", "h2"]


class TestBalancedSelection:
    """DEV-0315 核心: 偏好必须影响**切片前**的候选排序, 否则 balanced 首页≈无效果。

    (首版只做页内重排, 实弹计数 5→5 未变 = 假通过; 本用例锁死"参与选页"这一语义。)
    """

    def _seed_two_buckets(self, temp_db, seed: int = 20):
        """AI 20 条 + SECURITY 20 条 (两桶均在 balanced 配额内), 时序交错。"""
        items = []
        for i in range(1, seed + 1):
            items.append(_mk(f"ai{i:02d}", Category.AI, hours_ago=i))
            items.append(_mk(f"sec{i:02d}", Category.SECURITY, hours_ago=i))
        HotspotRepository().upsert_many(items)

    def _balanced_page(self, temp_db, limit: int, prefs: dict | None = None) -> list[str]:
        """cursor=None → balanced 模式 (首页路径)。"""
        res = HotspotService().list_hotspots(
            category="all",
            time_range="30d",
            cursor=None,
            limit=limit,
            content_preferences=prefs,
        )
        return [i["id"] for i in res["items"]]

    def test_balanced_without_prefs_is_mixed(self, temp_db):
        self._seed_two_buckets(temp_db)
        page = self._balanced_page(temp_db, limit=10)
        assert len(page) == 10
        # 无偏好: 混排 (两桶都有) — 不是全 AI 或全 SECURITY
        assert any(i.startswith("ai") for i in page)
        assert any(i.startswith("sec") for i in page)

    def test_pref_less_reduces_category_in_page(self, temp_db):
        """ai=less → AI 条目沉到页尾/出页, 首页 SECURITY 占比显著上升。"""
        self._seed_two_buckets(temp_db)
        base_ai = sum(1 for i in self._balanced_page(temp_db, 10) if i.startswith("ai"))
        less_ai = sum(1 for i in self._balanced_page(temp_db, 10, {"categories": {"ai": "less"}}) if i.startswith("ai"))
        assert less_ai < base_ai, f"ai=less 未减少页内 AI 条目: {base_ai} → {less_ai}"
        assert less_ai == 0, f"AI 应全部沉底: 实际仍有 {less_ai} 条"

    def test_pref_more_increases_category_in_page(self, temp_db):
        self._seed_two_buckets(temp_db)
        base_ai = sum(1 for i in self._balanced_page(temp_db, 10) if i.startswith("ai"))
        more_ai = sum(1 for i in self._balanced_page(temp_db, 10, {"categories": {"ai": "more"}}) if i.startswith("ai"))
        assert more_ai > base_ai, f"ai=more 未增加页内 AI 条目: {base_ai} → {more_ai}"

    def test_pref_source_affects_page(self, temp_db):
        """来源轴同样参与选页 (不只类目轴)。"""
        items = [
            _mk(f"ita{i:02d}", Category.AI, source="IT之家", hours_ago=i) for i in range(1, 11)
        ] + [
            _mk(f"bfb{i:02d}", Category.AI, source="FreeBuf", hours_ago=i) for i in range(1, 11)
        ]
        HotspotRepository().upsert_many(items)
        base_ita = sum(1 for i in self._balanced_page(temp_db, 10) if i.startswith("ita"))
        less_ita = sum(1 for i in self._balanced_page(temp_db, 10, {"sources": {"IT之家": "less"}}) if i.startswith("ita"))
        assert less_ita < base_ita, f"来源 less 未生效: {base_ita} → {less_ita}"
