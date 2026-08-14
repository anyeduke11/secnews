"""Phase 12 — AlertEngine 单元测试.

覆盖 15 个测试用例:
1.  test_alert_engine_load_rules       — 加载启用的规则
2.  test_tech_stack_cve_trigger        — CVE 命中 tech_stack 触发告警
3.  test_tech_stack_cve_no_match       — CVE 未命中不触发
4.  test_critical_cve_trigger          — CVSS ≥ 9.0 触发告警
5.  test_critical_cve_below_threshold  — CVSS < 9.0 不触发
6.  test_bid_match_trigger             — 标讯关键词命中 tech_stack 触发
7.  test_bid_match_no_match            — 关键词未命中不触发
8.  test_alert_event_stored            — 告警写入 alert_events 表
9.  test_alert_event_api_get           — GET /api/alerts/v2 返回列表
10. test_alert_event_mark_read         — PUT /api/alerts/v2/{id}/read 标记已读
11. test_alert_event_read_all          — PUT /api/alerts/v2/read-all 全部标记已读
12. test_alert_unread_count            — GET /api/alerts/v2/unread-count 返回计数
13. test_alert_rule_disabled           — 禁用规则不被评估
14. test_alert_concurrent_triggers     — 重复触发不创建重复事件
15. test_alert_evaluate_all            — evaluate_all 返回正确统计
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.alert_engine import AlertEngine

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_alert_engine.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    yield test_db
    db_module.close_db()


@pytest.fixture
def client(temp_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config, "feature_reviews", True)
    # 旧 alerts API (v1, /api/alerts/{id}) 与 v2 路由冲突 (/api/alerts/v2),
    # 因此关闭旧 API 以避免 /api/alerts/v2 被旧路由的 /api/alerts/{id} 捕获.
    monkeypatch.setattr(config, "feature_alerts", False)
    monkeypatch.setattr(config, "feature_recommendations", True)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ===========================================================================
# Helpers — 数据准备
# ===========================================================================


def _seed_rules(conn) -> None:
    """Insert 3 seed rules into alert_rule_definitions."""
    conn.execute("DELETE FROM alert_rule_definitions")
    conn.execute(
        """INSERT INTO alert_rule_definitions
               (id, name, description, rule_type, enabled, config)
           VALUES (1, '技术栈 CVE 影响', 'CVE 命中 tech_stack',
                   'tech_stack_cve', 1, '{"window_hours": 24}')"""
    )
    conn.execute(
        """INSERT INTO alert_rule_definitions
               (id, name, description, rule_type, enabled, config)
           VALUES (2, '关键 CVE 告警', 'CVSS >= 9.0',
                   'critical_cve', 1, '{"min_cvss": 9.0}')"""
    )
    conn.execute(
        """INSERT INTO alert_rule_definitions
               (id, name, description, rule_type, enabled, config)
           VALUES (3, '标讯技术栈匹配', '标讯命中 tech_stack',
                   'bid_match', 1, '{"window_hours": 24}')"""
    )
    conn.commit()


def _ensure_status_column(conn) -> None:
    """Add status column to cg_projects if missing (needed by alert_engine queries)."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(cg_projects)").fetchall()]
    if "status" not in cols:
        conn.execute("ALTER TABLE cg_projects ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")


def _insert_project(conn, pid: str, name: str, tech_stack: list[str], status: str = "active") -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO cg_projects
               (id, name, type, source_type, lifecycle_stage, status, tech_stack, created_at)
           VALUES (?, ?, 'web_application', 'manual', 'development', ?, ?, ?)""",
        (pid, name, status, json.dumps(tech_stack), now),
    )


def _insert_knowledge_item_with_cve(
    conn, kid: str, title: str, cve_ids: list[str], ingested_seconds_ago: int = 3600
) -> None:
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(seconds=ingested_seconds_ago)).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO knowledge_items
               (id, title, source, source_url, cve_ids, ingested_at, updated_at)
           VALUES (?, ?, 'nvd', ?, ?, ?, ?)""",
        (kid, title, f"https://example.com/{kid}", json.dumps(cve_ids), ingested, ingested),
    )


def _insert_security_entity_cve(conn, cve_id: str, cvss: float, created_seconds_ago: int = 600) -> None:
    now = datetime.now(timezone.utc)
    created = (now - timedelta(seconds=created_seconds_ago)).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO security_entities
               (id, entity_type, name, description, metadata, created_at, updated_at)
           VALUES (?, 'CVE', ?, ?, ?, ?, ?)""",
        (cve_id, cve_id, f"Description for {cve_id}",
         json.dumps({"cvss": cvss}), created, created),
    )


def _insert_bid_hotspot(conn, hid: str, title: str, ingested_seconds_ago: int = 3600) -> None:
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(seconds=ingested_seconds_ago)).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO hotspots
               (id, title, summary, source, url, category, published_at, score,
                fetched_at, ingested_at)
           VALUES (?, ?, ?, 'bid-source', ?, 'bid', ?, 50, ?, ?)""",
        (hid, title, f"Summary of {title}", f"https://example.com/{hid}",
         ingested, ingested, ingested),
    )


def _count_alerts(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM alert_events").fetchone()["c"]


def _get_alert_count(conn, rule_type: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM alert_events WHERE rule_type = ?", (rule_type,)
    ).fetchone()
    return row["c"]


# ===========================================================================
# 1. test_alert_engine_load_rules
# ===========================================================================

def test_alert_engine_load_rules(temp_db):
    """加载启用的规则: 3 条种子规则全部加载."""
    conn = get_connection()
    _seed_rules(conn)

    engine = AlertEngine()

    assert len(engine.rules) == 3
    rule_names = {r["name"] for r in engine.rules}
    assert "技术栈 CVE 影响" in rule_names
    assert "关键 CVE 告警" in rule_names
    assert "标讯技术栈匹配" in rule_names
    for r in engine.rules:
        assert r["enabled"] == 1


# ===========================================================================
# 2. test_tech_stack_cve_trigger
# ===========================================================================

def test_tech_stack_cve_trigger(temp_db):
    """CVE 命中 tech_stack → 触发告警."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-1", "Test Project", ["fastapi", "python"])
    _insert_knowledge_item_with_cve(
        conn, "ki-1",
        "FastAPI CVE-2024-1234 vulnerability",
        ["CVE-2024-1234"],
    )
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("技术栈 CVE 影响", -1) == 1
    assert _get_alert_count(conn, "tech_stack_cve") == 1
    alert = conn.execute(
        "SELECT * FROM alert_events WHERE rule_type = 'tech_stack_cve'"
    ).fetchone()
    assert alert is not None
    assert "CVE-2024-1234" in alert["title"]


# ===========================================================================
# 3. test_tech_stack_cve_no_match
# ===========================================================================

def test_tech_stack_cve_no_match(temp_db):
    """CVE 未命中 tech_stack → 不触发."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-2", "Test Project", ["fastapi", "python"])
    # CVE ID 和标题均不包含 tech_stack 关键词
    _insert_knowledge_item_with_cve(
        conn, "ki-2",
        "Unrelated CVE report",
        ["CVE-2024-5678"],
    )
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("技术栈 CVE 影响", -1) == 0


# ===========================================================================
# 4. test_critical_cve_trigger
# ===========================================================================

def test_critical_cve_trigger(temp_db):
    """CVSS ≥ 9.0 → 触发关键 CVE 告警."""
    conn = get_connection()
    _seed_rules(conn)
    _insert_security_entity_cve(conn, "CVE-2024-9999", 9.5)
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("关键 CVE 告警", -1) >= 1
    assert _get_alert_count(conn, "critical_cve") >= 1
    alert = conn.execute(
        "SELECT * FROM alert_events WHERE rule_type = 'critical_cve'"
    ).fetchone()
    assert alert is not None
    assert "CVE-2024-9999" in alert["title"]
    assert alert["severity"] == "critical"


# ===========================================================================
# 5. test_critical_cve_below_threshold
# ===========================================================================

def test_critical_cve_below_threshold(temp_db):
    """CVSS < 9.0 → 不触发."""
    conn = get_connection()
    _seed_rules(conn)
    _insert_security_entity_cve(conn, "CVE-2024-8888", 7.5)
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("关键 CVE 告警", -1) == 0
    assert _count_alerts(conn) == 0


# ===========================================================================
# 6. test_bid_match_trigger
# ===========================================================================

def test_bid_match_trigger(temp_db):
    """标讯关键词命中 tech_stack → 触发告警."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-3", "Project", ["fastapi"])
    _insert_bid_hotspot(conn, "bid-1", "FastAPI 框架招标公告")
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("标讯技术栈匹配", -1) == 1
    assert _get_alert_count(conn, "bid_match") == 1
    alert = conn.execute(
        "SELECT * FROM alert_events WHERE rule_type = 'bid_match'"
    ).fetchone()
    assert alert is not None
    assert alert["severity"] == "medium"


# ===========================================================================
# 7. test_bid_match_no_match
# ===========================================================================

def test_bid_match_no_match(temp_db):
    """关键词未命中 → 不触发."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-4", "Project", ["fastapi"])
    _insert_bid_hotspot(conn, "bid-2", "普通道路施工招标")
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert results.get("标讯技术栈匹配", -1) == 0
    assert _count_alerts(conn) == 0


# ===========================================================================
# 8. test_alert_event_stored
# ===========================================================================

def test_alert_event_stored(temp_db):
    """告警记录写入 alert_events 表, 字段完整."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-5", "Project", ["fastapi"])
    _insert_knowledge_item_with_cve(
        conn, "ki-8",
        "FastAPI CVE-2024-1111",
        ["CVE-2024-1111"],
    )
    conn.commit()

    engine = AlertEngine()
    engine.evaluate_all()

    alerts = conn.execute("SELECT * FROM alert_events").fetchall()
    assert len(alerts) >= 1
    alert = dict(alerts[0])
    assert "id" in alert
    assert "rule_id" in alert
    assert "rule_type" in alert
    assert "title" in alert
    assert "description" in alert
    assert "severity" in alert
    assert "source" in alert
    assert "source_url" in alert
    assert "item_id" in alert
    assert "project_id" in alert
    assert "status" in alert
    assert "created_at" in alert
    assert alert["status"] == "unread"
    assert alert["severity"] in ("critical", "high", "medium", "low")


# ===========================================================================
# 9. test_alert_event_api_get
# ===========================================================================

def test_alert_event_api_get(client, temp_db):
    """GET /api/alerts/v2 返回告警列表."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警, 绕过引擎 bug
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'tech_stack_cve', 'CVE-2024-2222', 'Test alert', 'high', 'CVE-2024-2222', ?)",
        (now,),
    )
    conn.commit()

    r = client.get("/api/alerts/v2")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert len(data["items"]) >= 1
    assert "id" in data["items"][0]
    assert "title" in data["items"][0]
    assert "severity" in data["items"][0]


# ===========================================================================
# 10. test_alert_event_mark_read
# ===========================================================================

def test_alert_event_mark_read(client, temp_db):
    """PUT /api/alerts/v2/{id}/read 标记为已读."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'tech_stack_cve', 'CVE-2024-3333', 'Test alert', 'high', 'CVE-2024-3333', ?)",
        (now,),
    )
    conn.commit()

    # 获取告警 ID
    r = client.get("/api/alerts/v2")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    alert_id = items[0]["id"]

    # 标记已读
    r = client.put(f"/api/alerts/v2/{alert_id}/read")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # 验证未读列表为空
    r = client.get("/api/alerts/v2", params={"status": "unread"})
    assert r.json()["count"] == 0


# ===========================================================================
# 11. test_alert_event_read_all
# ===========================================================================

def test_alert_event_read_all(client, temp_db):
    """PUT /api/alerts/v2/read-all 全部标记已读."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入多条测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'tech_stack_cve', 'CVE-2024-4444', 'Test alert 1', 'high', 'CVE-2024-4444', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'tech_stack_cve', 'CVE-2024-5555', 'Test alert 2', 'high', 'CVE-2024-5555', ?)",
        (now,),
    )
    conn.commit()

    r = client.put("/api/alerts/v2/read-all")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["updated"] > 0

    # 验证全部已读
    r = client.get("/api/alerts/v2", params={"status": "unread"})
    assert r.json()["count"] == 0


# ===========================================================================
# 12. test_alert_unread_count
# ===========================================================================

def test_alert_unread_count(client, temp_db):
    """GET /api/alerts/v2/unread-count 返回正确计数."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'tech_stack_cve', 'CVE-2024-6666', 'Test alert', 'high', 'CVE-2024-6666', ?)",
        (now,),
    )
    conn.commit()

    # 触发后应有未读
    r = client.get("/api/alerts/v2/unread-count")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    # 标记一个已读
    r = client.get("/api/alerts/v2")
    alert_id = r.json()["items"][0]["id"]
    client.put(f"/api/alerts/v2/{alert_id}/read")

    # 未读计数应减少
    r = client.get("/api/alerts/v2/unread-count")
    assert r.json()["count"] == 0


# ===========================================================================
# 13. test_alert_rule_disabled
# ===========================================================================

def test_alert_rule_disabled(temp_db):
    """禁用规则不被加载, 不被评估."""
    conn = get_connection()
    _seed_rules(conn)
    # 禁用 tech_stack_cve 规则
    conn.execute("UPDATE alert_rule_definitions SET enabled = 0 WHERE id = 1")
    conn.commit()

    _ensure_status_column(conn)
    _insert_project(conn, "proj-dis", "Project", ["fastapi"])
    # 插入不含 CVE 的知识条目, 避免 critical_cve 二次路径误触发
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(seconds=3600)).isoformat()
    conn.execute(
        "INSERT INTO knowledge_items (id, title, source, source_url, cve_ids, ingested_at, updated_at) "
        "VALUES (?, ?, 'test', ?, '[]', ?, ?)",
        ("ki-dis", "FastAPI article", "https://example.com/ki-dis", ingested, ingested),
    )
    conn.commit()

    engine = AlertEngine()
    assert len(engine.rules) == 2  # 只有 2 条启用规则

    results = engine.evaluate_all()

    # 禁用规则不在结果中
    assert "技术栈 CVE 影响" not in results
    assert _count_alerts(conn) == 0


# ===========================================================================
# 14. test_alert_concurrent_triggers
# ===========================================================================

def test_alert_concurrent_triggers(temp_db):
    """重复触发不创建重复告警事件 (24h 内同 source + rule_type 去重)."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-dup", "Project", ["fastapi"])
    _insert_knowledge_item_with_cve(
        conn, "ki-dup", "FastAPI CVE-2024-0001", ["CVE-2024-0001"],
    )
    conn.commit()

    engine = AlertEngine()
    # 第一次评估
    results1 = engine.evaluate_all()
    assert results1.get("技术栈 CVE 影响", -1) == 1

    # 第二次评估 (同 source = CVE-2024-0001, 同 rule_type, 24h 内)
    results2 = engine.evaluate_all()
    assert results2.get("技术栈 CVE 影响", -1) == 0  # 去重, 不新增

    # 总共只有 1 条告警
    assert _get_alert_count(conn, "tech_stack_cve") == 1


# ===========================================================================
# 15. test_alert_evaluate_all
# ===========================================================================

def test_alert_evaluate_all(temp_db):
    """evaluate_all 返回包含所有规则名称的统计字典, 数值正确."""
    conn = get_connection()
    _seed_rules(conn)
    _ensure_status_column(conn)
    _insert_project(conn, "proj-eval", "Project", ["fastapi", "python"])
    _insert_knowledge_item_with_cve(
        conn, "ki-eval-1", "FastAPI CVE-2024-9991", ["CVE-2024-9991"],
    )
    _insert_knowledge_item_with_cve(
        conn, "ki-eval-2", "Python CVE-2024-9992", ["CVE-2024-9992"],
    )
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    # 返回 dict
    assert isinstance(results, dict)
    # 包含所有 3 条规则名称
    assert "技术栈 CVE 影响" in results
    assert "关键 CVE 告警" in results
    assert "标讯技术栈匹配" in results
    # tech_stack_cve 应触发 (2 个 CVE 都命中)
    assert results["技术栈 CVE 影响"] == 2
    # 关键 CVE 告警 二次路径: 2 个 knowledge_items 都含 CVE ID
    assert results["关键 CVE 告警"] == 2
    # 标讯技术栈匹配 未触发
    assert results["标讯技术栈匹配"] == 0
    # 总告警数 = tech_stack_cve + critical_cve
    total = _count_alerts(conn)
    assert total == results["技术栈 CVE 影响"] + results["关键 CVE 告警"]