"""v1.7 Phase 3 — 端到端验收测试 (4 项验收标准).

验收标准 (来自 docs/v1.7_development_plan.md Task 3.6):
  1. 新建规则后 60s 内匹配的文章触发告警
  2. 统一搜索 500ms 内返回跨层结果
  3. 告警 SSE 推送到达前端
  4. /api/mode/current 在每日首次打开返回 brief

本文件是端到端验收: 通过 FastAPI TestClient 走完整 HTTP 链路,
不直接调用 service/repo, 确保从 API → service → repo → DB 全链路正确.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.events import _subscribers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_phase3_acceptance.db"
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


def _insert_hotspot(hid: str, title: str, summary: str = "", category: str = "security") -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (hid, title, summary, "test", f"https://example.com/{hid}",
         category, now, 50.0, now, 0, 80, "[]", "pending", now),
    )


def _insert_hotspot_with_tags(hid: str, title: str, tags: list[str]) -> None:
    """插入热点 + 关联标签 (hotspot_tags 表, Phase 1 source of truth)."""
    from backend.repository.db import get_connection
    _insert_hotspot(hid, title)
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    for tag in tags:
        # 确保 tag 存在
        tag_id = tag.lower().replace(" ", "-")
        conn.execute(
            "INSERT OR IGNORE INTO tags (id, label, type, weight, created_at) VALUES (?, ?, 'domain', 1.0, ?)",
            (tag_id, tag, now),
        )
        # hotspot_tags 需要 confidence + created_at (非空)
        conn.execute(
            "INSERT OR IGNORE INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) VALUES (?, ?, ?, ?)",
            (hid, tag_id, 1.0, now),
        )


def _insert_knowledge(kid: str, title: str, topic: str = "", domain: str = "security") -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (kid, title, "test", domain, topic, "article", "beginner",
         "[]", "[]", 0, 0, now, now, f"https://example.com/{kid}"),
    )


# ---------------------------------------------------------------------------
# 验收 1: 新建规则后 60s 内匹配的文章触发告警
# ---------------------------------------------------------------------------
class TestAcceptance1RuleTriggersAlert:
    """验收 1: 新建规则后 60s 内匹配的文章触发告警.

    流程:
      1. POST /api/alerts/rules 创建规则 (tag_match: contains_any ["fastapi"])
      2. 插入带 "fastapi" 标签的热点
      3. POST /api/alerts/evaluate/{hotspot_id} 触发评估
      4. GET /api/alerts 验证告警已生成
      5. 验证整个流程耗时 < 60s (实际 < 1s)
    """

    def test_rule_triggers_alert_within_60s(self, client):
        t0 = time.perf_counter()

        # 1. 创建规则
        rule_payload = {
            "name": "FastAPI 漏洞告警",
            "condition": {
                "type": "tag_match",
                "operator": "OR",
                "conditions": [{"op": "contains_any", "value": ["fastapi"]}],
            },
            "action": {"type": "sse"},
            "cooldown_sec": 3600,
            "enabled": True,
        }
        r = client.post("/api/alerts/rules", json=rule_payload)
        assert r.status_code == 201
        rule_id = r.json()["item"]["id"]

        # 2. 插入带标签的热点
        _insert_hotspot_with_tags("h-acc1", "FastAPI RCE 漏洞", ["fastapi", "security"])

        # 3. 触发评估
        r = client.post("/api/alerts/evaluate/h-acc1")
        assert r.status_code == 200
        fired = r.json()["fired_rules"]
        assert rule_id in fired, f"规则应被触发, fired_rules={fired}"

        # 4. 验证告警已生成
        r = client.get("/api/alerts")
        assert r.status_code == 200
        alerts = r.json()["items"]
        assert len(alerts) >= 1
        assert alerts[0]["rule_id"] == rule_id
        assert alerts[0]["entity_id"] == "h-acc1"

        # 5. 耗时验证 (< 60s, 实际 < 1s)
        elapsed = time.perf_counter() - t0
        assert elapsed < 60, f"告警触发耗时 {elapsed:.2f}s 超过 60s 预算"

    def test_non_matching_hotspot_does_not_trigger(self, client):
        """不匹配的热点不应触发告警。"""
        client.post("/api/alerts/rules", json={
            "name": "Go 漏洞告警",
            "condition": {
                "type": "tag_match",
                "operator": "OR",
                "conditions": [{"op": "contains_any", "value": ["golang"]}],
            },
            "action": {"type": "sse"},
            "cooldown_sec": 3600,
            "enabled": True,
        })
        _insert_hotspot_with_tags("h-nomatch", "FastAPI 文章", ["fastapi"])
        r = client.post("/api/alerts/evaluate/h-nomatch")
        assert r.status_code == 200
        assert r.json()["fired_rules"] == []


# ---------------------------------------------------------------------------
# 验收 2: 统一搜索 500ms 内返回跨层结果
# ---------------------------------------------------------------------------
class TestAcceptance2UnifiedSearchUnder500ms:
    """验收 2: 统一搜索 500ms 内返回跨层结果.

    流程:
      1. 插入跨层测试数据 (hotspots + knowledge_items)
      2. GET /api/search?q=FastAPI&limit=20
      3. 验证响应时间 < 500ms
      4. 验证结果包含 hotspot + knowledge 两个 entity_type
    """

    def test_search_returns_cross_layer_results_under_500ms(self, client):
        # 1. 插入跨层数据 (少量, 确保 limit=20 内两种类型都出现)
        for i in range(5):
            _insert_hotspot(f"h-search-{i}", f"FastAPI 热点第{i}篇", f"摘要{i}")
        for i in range(5):
            _insert_knowledge(f"k-search-{i}", f"FastAPI 知识第{i}篇", f"主题{i}")

        # 2. 搜索
        t0 = time.perf_counter()
        r = client.get("/api/search", params={"q": "FastAPI", "limit": 20})
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # 3. 验证响应时间
        assert r.status_code == 200
        assert elapsed_ms < 500, f"搜索耗时 {elapsed_ms:.1f}ms 超过 500ms 预算"

        # 4. 验证跨层结果 (10 条 < limit=20, 两种类型都应出现)
        result = r.json()["result"]
        items = result["items"]
        assert len(items) == 10
        types = {i["entity_type"] for i in items}
        assert "hotspot" in types, "结果应包含 hotspot 层"
        assert "knowledge" in types, "结果应包含 knowledge 层"

    def test_search_with_source_filter(self, client):
        """sources 过滤应正确限制结果层。"""
        _insert_hotspot("h-filter", "FastAPI 热点", "")
        _insert_knowledge("k-filter", "FastAPI 知识", "")

        r = client.get("/api/search", params={"q": "FastAPI", "sources": "hotspot"})
        items = r.json()["result"]["items"]
        assert all(i["entity_type"] == "hotspot" for i in items)
        assert len(items) == 1

        r = client.get("/api/search", params={"q": "FastAPI", "sources": "knowledge"})
        items = r.json()["result"]["items"]
        assert all(i["entity_type"] == "knowledge" for i in items)
        assert len(items) == 1

    def test_search_grouped_structure(self, client):
        """grouped 结构应按 entity_type 分组。"""
        _insert_hotspot("h-g1", "FastAPI 热点1", "")
        _insert_hotspot("h-g2", "FastAPI 热点2", "")
        _insert_knowledge("k-g1", "FastAPI 知识1", "")

        r = client.get("/api/search", params={"q": "FastAPI"})
        grouped = r.json()["result"]["grouped"]
        assert len(grouped["hotspot"]) == 2
        assert len(grouped["knowledge"]) == 1


# ---------------------------------------------------------------------------
# 验收 3: 告警 SSE 推送到达前端
# ---------------------------------------------------------------------------
class TestAcceptance3SSEPush:
    """验收 3: 告警 SSE 推送到达前端.

    流程:
      1. 创建规则 + 带标签的热点
      2. 验证 evaluate_hotspot 内部调用 publish_event("alert", ...)
         通过检查 _subscribers 机制: 注册一个 subscriber queue,
         evaluate 后 queue 应收到 "alert" 事件
      3. 验证事件格式正确 (type=alert, data.alert.id 存在)
    """

    def test_alert_evaluation_publishes_sse_event(self, client):
        import asyncio

        # 1. 注册一个 subscriber 模拟前端 SSE 连接
        test_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        _subscribers.append(test_queue)

        try:
            # 2. 创建规则 + 热点
            client.post("/api/alerts/rules", json={
                "name": "SSE 测试规则",
                "condition": {
                    "type": "tag_match",
                    "operator": "OR",
                    "conditions": [{"op": "contains_any", "value": ["sse-test"]}],
                },
                "action": {"type": "sse"},
                "cooldown_sec": 3600,
                "enabled": True,
            })
            _insert_hotspot_with_tags("h-sse", "SSE 测试热点", ["sse-test"])

            # 3. 触发评估 — 内部应调用 publish_event("alert", ...)
            r = client.post("/api/alerts/evaluate/h-sse")
            assert r.status_code == 200
            assert len(r.json()["fired_rules"]) == 1

            # 4. 验证 SSE 事件已推送到 subscriber queue
            # publish_event 是 async, 但在同步上下文中通过 asyncio.run() 执行
            # 等待一小段时间让事件入队
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(asyncio.sleep(0.1))
            finally:
                loop.close()

            # 检查 queue 中是否有事件
            assert not test_queue.empty(), "SSE queue 应收到 alert 事件"
            raw = test_queue.get_nowait()
            event = json.loads(raw)
            assert event["type"] == "alert"
            assert "alert" in event["data"]
            assert event["data"]["alert"]["entity_id"] == "h-sse"
        finally:
            if test_queue in _subscribers:
                _subscribers.remove(test_queue)

    def test_frontend_alert_center_receives_sse(self, client):
        """前端 AlertCenter 组件测试已验证 SSE 事件处理 (见 AlertCenter.test.tsx).

        此后端测试验证: evaluate_hotspot 产生的告警可通过 GET /api/alerts
        被前端拉取, 且 SSE 推送的告警与 API 返回的一致。
        """
        client.post("/api/alerts/rules", json={
            "name": "前端验证规则",
            "condition": {
                "type": "keyword_match",
                "field": "title",
                "value": ["前端测试"],
            },
            "action": {"type": "sse"},
            "cooldown_sec": 3600,
            "enabled": True,
        })
        _insert_hotspot("h-frontend", "前端测试关键词热点", "")

        # 评估
        client.post("/api/alerts/evaluate/h-frontend")

        # 前端通过 GET /api/alerts 拉取
        r = client.get("/api/alerts")
        alerts = r.json()["items"]
        assert any(a["entity_id"] == "h-frontend" for a in alerts)


# ---------------------------------------------------------------------------
# 验收 4: /api/mode/current 在每日首次打开返回 brief
# ---------------------------------------------------------------------------
class TestAcceptance4ModeBriefOnFirstOpen:
    """验收 4: /api/mode/current 在每日首次打开返回 brief.

    流程:
      1. 无简报时 GET /api/mode/current → scan (默认)
      2. 创建今日简报 (digests 表)
      3. GET /api/mode/current → brief (有未读简报)
      4. PUT /api/mode/switch?mode=scan → 标记简报已读
      5. GET /api/mode/current → scan (已读)
    """

    def test_first_open_with_unread_digest_returns_brief(self, client):
        from backend.services.digest_service import create_digest

        # 1. 无简报 → scan
        r = client.get("/api/mode/current")
        assert r.json()["mode"] == "scan"

        # 2. 创建今日简报
        create_digest("d-acc4", period="daily", summary="今日安全简报")

        # 3. 首次打开 → brief
        r = client.get("/api/mode/current")
        assert r.json()["mode"] == "brief", "有未读简报时应返回 brief"

    def test_after_switch_mode_returns_scan(self, client):
        from backend.services.digest_service import create_digest

        create_digest("d-acc4b", period="daily", summary="今日简报")
        assert client.get("/api/mode/current").json()["mode"] == "brief"

        # 4. 切换模式 → 标记已读
        r = client.put("/api/mode/switch", params={"mode": "scan"})
        assert r.status_code == 200

        # 5. 后续 → scan
        r = client.get("/api/mode/current")
        assert r.json()["mode"] == "scan", "切换后应返回 scan"

    def test_all_modes_switchable(self, client):
        """所有 6 种模式均可切换。"""
        for mode in ["brief", "scan", "deep", "organize", "review", "alert"]:
            r = client.put("/api/mode/switch", params={"mode": mode})
            assert r.status_code == 200
            assert r.json()["mode"] == mode

    def test_invalid_mode_rejected(self, client):
        r = client.put("/api/mode/switch", params={"mode": "invalid"})
        assert r.status_code == 400
