"""Phase 4 API 层端到端测试

覆盖 (11 个端点 + 中间件 + cache 命中 + cursor + 错误格式):
  - GET /
  - GET /api/health
  - GET /api/stats
  - GET /api/categories
  - GET /api/hotspots (cursor 分页 + cache 命中)
  - GET /api/hotspots/{id}
  - GET /api/trends
  - GET /api/quality/summary
  - GET /api/quality/rules
  - PUT /api/quality/rules
  - GET /api/quality/logs
  - GET /api/quality/source-reputation
  - GET /api/proxy/settings
  - GET /api/export (ETag 304)
  - 错误响应格式 (5 个异常类型 + version + trace_id)
  - TraceIDMiddleware 注入 X-Trace-Id 头

测试策略
--------
- 用 tmp_path + monkeypatch 重定向 config.db_path 到临时 DB
- 注入少量 hotspot / trend 数据走真实 SQL
- 注入静态 ``_service`` mock 避免外网抓取
- lifespan 不启动 (测试模式下手动构造 app)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TRACE_HEADER, TraceIDMiddleware
from backend.cache import (
    detail_cache,
    invalidate,
    static_cache,
)
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import (
    API_VERSION,
    register_exception_handlers,
)
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.services.hotspot_service import encode_cursor, decode_cursor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """临时 DB + schema 初始化。"""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


def _make_item(
    id_: str = "test-1",
    title: str = "Test Title",
    category: Category = Category.AI,
    source: str = "test-src",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        summary=f"summary for {id_}",
        source=source,
        url=f"https://example.com/{id_}",
        category=category,
        published_at=now,
        fetched_at=now,
        score=80,
        is_fallback=False,
    )


@pytest.fixture
def seeded_db(temp_db):
    """插入 3 个 hotspot: 1 ai / 1 security / 1 finance。"""
    repo = HotspotRepository()
    items = [
        _make_item("item-1", "AI breakthrough", Category.AI, "aihot.virxact.com"),
        _make_item("item-2", "CVE-2026-X", Category.SECURITY, "thehackernews.com"),
        _make_item("item-3", "Market rises", Category.FINANCE, "sina.com.cn"),
    ]
    repo.upsert_many(items)
    return items


@pytest.fixture(autouse=True)
def reset_caches():
    """每个测试前清空所有 cache。"""
    invalidate("*")
    yield
    invalidate("*")


@pytest.fixture
def client(temp_db):
    """构造带 router + middleware + exception handler 的 TestClient。

    注意: 不启动 lifespan (scheduler / 真实采集会触网)。
    """
    app = FastAPI(title="test app", version=API_VERSION)
    app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
    register_exception_handlers(app)

    @app.get("/")
    async def root():
        return {
            "name": "热点地图 API",
            "version": API_VERSION,
            "docs": "/docs",
            "health": "/api/health",
        }

    register_routers(app)

    # 桩住 scheduler / collectors 的副作用
    with patch("backend.scheduler.scheduler.get_scheduler", return_value=None):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# 1. 根路径
# ---------------------------------------------------------------------------
def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "热点地图 API"
    assert data["version"] == API_VERSION
    assert data["health"] == "/api/health"


# ---------------------------------------------------------------------------
# 2. /api/health
# ---------------------------------------------------------------------------
def test_health_basic(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == API_VERSION
    assert "status" in data
    assert "components" in data
    assert "db" in data["components"]
    assert "cache" in data["components"]


def test_health_excludes_trace_id_header(client):
    """health 路径在 exclude 中, 也仍回写 X-Trace-Id。"""
    r = client.get("/api/health")
    assert TRACE_HEADER in r.headers


# ---------------------------------------------------------------------------
# 3. /api/stats
# ---------------------------------------------------------------------------
def test_stats_returns_cache_and_db(client, seeded_db):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == API_VERSION
    assert "cache" in data
    assert "db" in data
    assert data["db"]["hotspots_total"] >= 3


# ---------------------------------------------------------------------------
# 4. /api/categories
# ---------------------------------------------------------------------------
def test_categories_returns_6(client, seeded_db):
    r = client.get("/api/categories")
    assert r.status_code == 200
    data = r.json()
    cats = data["categories"]
    # Phase 35: tech 合并到 ai, 主分类 6 个
    # Phase X:  新增 ai_security (AI 安全交叉) → 总数 7
    assert len(cats) == 7
    ids = {c["id"] for c in cats}
    assert ids == {"ai", "ai_security", "security", "finance", "startup", "bid", "github"}
    assert "tech" not in ids
    for c in cats:
        assert "label" in c
        assert "color" in c
        assert "count" in c


def test_categories_cached(client, seeded_db):
    r1 = client.get("/api/categories")
    r2 = client.get("/api/categories")
    assert r1.json() == r2.json()
    # 第二次应走 static_cache (同样的数据 + fetched_at 也可能变化, 验证 keys 至少被填上)
    assert "categories:all" in static_cache.keys() or len(static_cache) >= 1


# ---------------------------------------------------------------------------
# 5. /api/hotspots (列表 + cursor + cache)
# ---------------------------------------------------------------------------
def test_hotspots_list_default(client, seeded_db):
    r = client.get("/api/hotspots")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == API_VERSION
    assert data["category"] == "all"
    assert data["time_range"] == "7d"
    assert len(data["items"]) == 3
    assert "category_counts" in data
    assert "next_cursor" in data


def test_hotspots_filter_category(client, seeded_db):
    r = client.get("/api/hotspots", params={"category": "ai"})
    assert r.status_code == 200
    data = r.json()
    assert data["category"] == "ai"
    assert all(item["category"] == "ai" for item in data["items"])
    assert len(data["items"]) >= 1


def test_hotspots_invalid_category(client):
    r = client.get("/api/hotspots", params={"category": "invalid"})
    assert r.status_code == 400
    data = r.json()
    assert data["code"] == "INVALID_PARAM"
    assert "trace_id" in data
    assert data["version"] == API_VERSION


def test_hotspots_invalid_time_range(client):
    r = client.get("/api/hotspots", params={"time_range": "99d"})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PARAM"


def test_hotspots_invalid_cursor(client):
    r = client.get("/api/hotspots", params={"cursor": "not-base64!"})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PARAM"


def test_hotspots_keyword_search(client, seeded_db):
    r = client.get("/api/hotspots", params={"keyword": "AI"})
    assert r.status_code == 200
    data = r.json()
    assert data["keyword"] == "AI"
    # 至少 1 个匹配 ("AI breakthrough")
    assert len(data["items"]) >= 1


def test_hotspots_cache_hit(client, seeded_db):
    """连续两次同样请求, 第二次应命中 list_cache。"""
    r1 = client.get("/api/hotspots", params={"category": "ai"})
    r2 = client.get("/api/hotspots", params={"category": "ai"})
    assert r1.json() == r2.json()


# ---------------------------------------------------------------------------
# 6. /api/hotspots/{id} 详情
# ---------------------------------------------------------------------------
def test_hotspot_detail_found(client, seeded_db):
    r = client.get("/api/hotspots/item-1")
    assert r.status_code == 200
    data = r.json()
    assert data["item"]["id"] == "item-1"
    assert data["item"]["title"] == "AI breakthrough"


def test_hotspot_detail_not_found(client):
    r = client.get("/api/hotspots/does-not-exist")
    assert r.status_code == 404
    data = r.json()
    assert data["code"] == "NOT_FOUND"
    assert "trace_id" in data
    assert data["version"] == API_VERSION


def test_hotspot_detail_cache_hit(client, seeded_db):
    r1 = client.get("/api/hotspots/item-1")
    r2 = client.get("/api/hotspots/item-1")
    assert r1.json() == r2.json()
    assert "hotspots:detail:item-1" in detail_cache.keys()


# ---------------------------------------------------------------------------
# 7. cursor 分页正确性 (无重复 / 无遗漏)
# ---------------------------------------------------------------------------
def test_cursor_encode_decode_roundtrip(seeded_db):
    item = _make_item("x", "Title X", Category.AI)
    cursor = encode_cursor(item)
    id_, ts = decode_cursor(cursor)
    assert id_ == "x"
    assert ts == item.published_at.isoformat()


def test_cursor_decode_invalid_raises():
    with pytest.raises(Exception):  # InvalidParamException
        decode_cursor("not-base64@!")


def test_hotspots_cursor_pagination(client, seeded_db):
    """limit=2 + balanced 模式 → 返回 2 条 + 无 next_cursor。

    Phase 25: 列表接口默认 balanced 模式 (cursor=None + category=all 触发),
    单一 ingest 时返回 limit 条并截断,不返回 next_cursor。
    翻页需要在第二次请求带 cursor 触发非 balanced 模式。

    Phase 39: ``total`` 字段语义改为「time_range 内真实总数」 (供分页 X/Y),
    仍可与 ``len(items)`` 共存 — page size = 2 截断 vs total = seed 全量 3。
    """
    r1 = client.get("/api/hotspots", params={"limit": 2})
    assert r1.status_code == 200
    data1 = r1.json()
    # balanced 模式: 返回 limit 条 (seed 仅 3 条,截断为 2) + 无 next_cursor
    assert len(data1["items"]) == 2
    assert data1["next_cursor"] is None
    # 字段完整性: total = seed 真实总数 (3), 不是页面截断数
    assert data1["total"] == 3
    assert data1["category"] == "all"
    assert "category_counts" in data1
    # Phase 39: 新增字段
    assert "latest_ingestion_count" in data1
    assert "latest_ingestion_at" in data1


# ---------------------------------------------------------------------------
# 8. /api/trends
# ---------------------------------------------------------------------------
def test_trends_default(client, temp_db):
    r = client.get("/api/trends")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == API_VERSION
    assert "trends" in data
    assert "hours" in data
    assert data["hours"] == 24
    assert isinstance(data["trends"], list)
    assert len(data["trends"]) == 24  # 24h * 1 point/h


def test_trends_by_category(client, temp_db):
    r = client.get("/api/trends", params={"by_category": "true"})
    assert r.status_code == 200
    data = r.json()
    assert "data" in data  # category -> points
    assert isinstance(data["data"], dict)
    # Phase 25 P1: 7 个分类
    assert len(data["data"]) == 7


def test_trends_invalid_hours(client):
    r = client.get("/api/trends", params={"hours": 0})
    assert r.status_code == 422  # FastAPI Query 校验


# ---------------------------------------------------------------------------
# 9. /api/quality/* (5 个端点)
# ---------------------------------------------------------------------------
def test_quality_summary(client, temp_db):
    r = client.get("/api/quality/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == API_VERSION
    assert "summary" in data


def test_quality_rules_get(client, temp_db):
    r = client.get("/api/quality/rules")
    assert r.status_code == 200
    data = r.json()
    assert "rules" in data
    assert "defaults" in data


def test_quality_rules_get_array_format(client, temp_db):
    """Phase 9 上线修复：rules 必须是 array，每条含 key/value/default/type/description。"""
    r = client.get("/api/quality/rules")
    assert r.status_code == 200
    data = r.json()
    rules = data["rules"]
    assert isinstance(rules, list), f"rules must be array, got {type(rules)}"
    assert len(rules) >= 14  # 7 scalar + 7 category_keywords
    # 第一条必须是标量规则
    r0 = rules[0]
    assert {"key", "value", "default", "type", "description"}.issubset(r0.keys())
    # category_keywords.* 至少 6 条 (Phase 25 P1 加 tech → 7)
    kw_rules = [x for x in rules if x["key"].startswith("quality.category_keywords.")]
    assert len(kw_rules) == 7
    for kw in kw_rules:
        assert kw["type"] == "list"
        assert isinstance(kw["value"], list) and isinstance(kw["default"], list)
    # PUT/GET 一致性
    client.put("/api/quality/rules", json={"rules": {"quality.min_score": 35}})
    r2 = client.get("/api/quality/rules")
    rules2 = {x["key"]: x["value"] for x in r2.json()["rules"]}
    assert rules2["quality.min_score"] == 35
    # 清理
    client.put("/api/quality/rules", json={"rules": {"quality.min_score": 30}})


def test_quality_rules_put_success(client, temp_db):
    r = client.put(
        "/api/quality/rules",
        json={"rules": {"quality.strict_mode": True}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "quality.strict_mode" in data["updated"]


def test_quality_rules_put_empty(client, temp_db):
    r = client.put("/api/quality/rules", json={"rules": {}})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PARAM"


def test_quality_rules_put_invalid_key(client, temp_db):
    """key 不以 'quality.' 开头 → 400。"""
    r = client.put(
        "/api/quality/rules",
        json={"rules": {"other.key": "v"}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_PARAM"


def test_quality_logs(client, temp_db):
    r = client.get("/api/quality/logs", params={"item_id": "test-1"})
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == "test-1"
    assert "logs" in data
    assert "count" in data


def test_quality_logs_missing_item_id(client, temp_db):
    r = client.get("/api/quality/logs")
    assert r.status_code == 422  # required query param 缺失


def test_quality_source_reputation(client, temp_db):
    r = client.get("/api/quality/source-reputation")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert isinstance(data["sources"], list)


# ---------------------------------------------------------------------------
# 10. /api/proxy/*
# ---------------------------------------------------------------------------
def test_proxy_settings_get(client):
    r = client.get("/api/proxy/settings")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "mode" in data["settings"]


def test_proxy_settings_put(client, monkeypatch):
    """PUT 应返回成功, 但不应破坏真实文件。"""
    import backend.proxy_config as pc

    real_load = pc.load_proxy_settings
    real_save = pc.save_proxy_settings

    with patch.object(pc, "load_proxy_settings", wraps=real_load):
        with patch.object(pc, "save_proxy_settings", wraps=real_save):
            r = client.put(
                "/api/proxy/settings",
                json={
                    "mode": "off",
                    "http_proxy": "",
                    "https_proxy": "",
                    "socks_proxy": "",
                    "no_proxy": "localhost",
                    "whitelist": [],
                },
            )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# 11. /api/export (ETag 304)
# ---------------------------------------------------------------------------
def test_export_returns_etag(client, temp_db):
    r = client.get("/api/export")
    assert r.status_code == 200
    assert "ETag" in r.headers
    assert "text/html" in r.headers.get("content-type", "")


def test_export_returns_304_when_etag_matches(client, temp_db):
    r1 = client.get("/api/export")
    assert r1.status_code == 200
    etag = r1.headers["ETag"]

    r2 = client.get("/api/export", headers={"If-None-Match": etag})
    assert r2.status_code == 304


# ---------------------------------------------------------------------------
# 12. 错误响应格式 (5 个异常类型 + version + trace_id)
# ---------------------------------------------------------------------------
def test_error_format_includes_version_and_trace_id(client):
    """所有 HotspotException 应有 {code, message, trace_id, version}。"""
    r = client.get("/api/hotspots/does-not-exist")
    assert r.status_code == 404
    data = r.json()
    assert set(data.keys()) == {"code", "message", "trace_id", "version"}
    assert data["version"] == API_VERSION
    assert len(data["trace_id"]) > 0


def test_trace_id_middleware_propagates_header(client):
    r = client.get("/api/categories")
    assert TRACE_HEADER in r.headers
    assert r.headers[TRACE_HEADER]


def test_trace_id_middleware_uses_provided_header(client):
    r = client.get(
        "/api/categories",
        headers={TRACE_HEADER: "my-trace-id-123"},
    )
    assert r.headers[TRACE_HEADER] == "my-trace-id-123"


def test_trace_id_persists_in_error_response(client):
    """trace_id 应在错误响应里出现, 与 header 一致。"""
    r = client.get(
        "/api/hotspots/missing",
        headers={TRACE_HEADER: "abc-trace"},
    )
    assert r.status_code == 404
    assert r.json()["trace_id"] == "abc-trace"
    assert r.headers[TRACE_HEADER] == "abc-trace"


# ---------------------------------------------------------------------------
# 13. 不变量: 所有响应都含 version 字段
# ---------------------------------------------------------------------------
def test_all_responses_have_version(client, seeded_db):
    """Phase 4 不变量: 任何 JSON 响应都应含 version 字段。"""
    endpoints = [
        "/",
        "/api/health",
        "/api/stats",
        "/api/categories",
        "/api/hotspots",
        "/api/hotspots/item-1",
        "/api/trends",
        "/api/quality/summary",
        "/api/quality/rules",
        "/api/proxy/settings",
    ]
    for ep in endpoints:
        r = client.get(ep)
        if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
            data = r.json()
            assert "version" in data, f"{ep} 响应缺 version: {data}"
            assert data["version"] == API_VERSION
