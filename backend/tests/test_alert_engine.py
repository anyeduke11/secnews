"""Phase 12 — AlertEngine 单元测试.

覆盖测试用例:
1.  test_alert_engine_load_rules       — 加载启用的规则
2.  test_critical_cve_trigger          — CVSS ≥ 9.0 触发告警
3.  test_critical_cve_below_threshold  — CVSS < 9.0 不触发
4.  test_alert_event_stored            — 告警写入 alert_events 表
5.  test_alert_event_api_get           — GET /api/alerts/v2 返回列表
6.  test_alert_event_mark_read         — PUT /api/alerts/v2/{id}/read 标记已读
7.  test_alert_event_read_all          — PUT /api/alerts/v2/read-all 全部标记已读
8.  test_alert_unread_count            — GET /api/alerts/v2/unread-count 返回计数
9.  test_alert_rule_disabled           — 禁用规则不被评估
10. test_alert_concurrent_triggers     — 重复触发不创建重复事件
11. test_alert_evaluate_all            — evaluate_all 返回正确统计

2026-11-19 (四域删除): tech_stack_cve 规则随 CodeGarden 域退役
(cg_projects 已 DROP) — 对应用例已删除, 引擎只保留 critical_cve。
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
    monkeypatch.setattr(config, "feature_review", True)
    # v1 (/api/alerts/{id}) 与 v2 (/api/alerts/v2) 按生产配置共存 —
    # 注册序契约 (v2 先注册, 见 _registry.py) 保证 /api/alerts/v2 不被
    # v1 的 /{alert_id} 捕获; 此处锁定该契约 (2026-10-01 前曾以关闭 v1 绕过,
    # 导致测试全绿而生产告警列表恒空).
    monkeypatch.setattr(config, "feature_alert", True)
    monkeypatch.setattr(config, "feature_recommendation", True)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ===========================================================================
# Helpers — 数据准备
# ===========================================================================


def _seed_rules(conn) -> None:
    """Insert the single live seed rule (critical_cve) into alert_rule_definitions.

    2026-11-19: tech_stack_cve 已退役, 种子只保留 critical_cve。
    """
    conn.execute("DELETE FROM alert_rule_definitions")
    conn.execute(
        """INSERT INTO alert_rule_definitions
               (id, name, description, rule_type, enabled, config)
           VALUES (1, '关键 CVE 告警', 'CVSS >= 9.0',
                   'critical_cve', 1, '{"min_cvss": 9.0}')"""
    )
    conn.commit()


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
    """加载启用的规则: 唯一存活种子 critical_cve 被加载."""
    conn = get_connection()
    _seed_rules(conn)

    engine = AlertEngine()

    assert len(engine.rules) == 1
    assert engine.rules[0]["name"] == "关键 CVE 告警"
    assert engine.rules[0]["enabled"] == 1


# ===========================================================================
# 2. test_critical_cve_trigger
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
# 3. test_critical_cve_below_threshold
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
# 4. test_alert_event_stored
# ===========================================================================

def test_alert_event_stored(temp_db):
    """告警记录写入 alert_events 表, 字段完整."""
    conn = get_connection()
    _seed_rules(conn)
    _insert_security_entity_cve(conn, "CVE-2024-1111", 9.8)
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
    # project_id 列随工坊域退役不再写入 (引擎不再传值), 列保留但为 NULL
    assert "project_id" in alert
    assert alert["project_id"] is None
    assert "status" in alert
    assert "created_at" in alert
    assert alert["status"] == "unread"
    assert alert["severity"] in ("critical", "high", "medium", "low")


# ===========================================================================
# 5. test_alert_event_api_get
# ===========================================================================

def test_alert_event_api_get(client, temp_db):
    """GET /api/alerts/v2 返回告警列表."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'critical_cve', 'CVE-2024-2222', 'Test alert', 'high', 'CVE-2024-2222', ?)",
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
# 6. test_alert_event_mark_read
# ===========================================================================

def test_alert_event_mark_read(client, temp_db):
    """PUT /api/alerts/v2/{id}/read 标记为已读."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'critical_cve', 'CVE-2024-3333', 'Test alert', 'high', 'CVE-2024-3333', ?)",
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
# 7. test_alert_event_read_all
# ===========================================================================

def test_alert_event_read_all(client, temp_db):
    """PUT /api/alerts/v2/read-all 全部标记已读."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入多条测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'critical_cve', 'CVE-2024-4444', 'Test alert 1', 'high', 'CVE-2024-4444', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'critical_cve', 'CVE-2024-5555', 'Test alert 2', 'high', 'CVE-2024-5555', ?)",
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
# 8. test_alert_unread_count
# ===========================================================================

def test_alert_unread_count(client, temp_db):
    """GET /api/alerts/v2/unread-count 返回正确计数."""
    conn = get_connection()
    _seed_rules(conn)
    # 直接插入测试告警
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alert_events (rule_id, rule_type, title, description, severity, source, created_at) "
        "VALUES (1, 'critical_cve', 'CVE-2024-6666', 'Test alert', 'high', 'CVE-2024-6666', ?)",
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
# 9. test_alert_rule_disabled
# ===========================================================================

def test_alert_rule_disabled(temp_db):
    """禁用规则不被加载, 不被评估."""
    conn = get_connection()
    _seed_rules(conn)
    conn.execute("UPDATE alert_rule_definitions SET enabled = 0 WHERE id = 1")
    _insert_security_entity_cve(conn, "CVE-2024-7777", 9.9)
    conn.commit()

    engine = AlertEngine()
    assert len(engine.rules) == 0

    results = engine.evaluate_all()

    assert results == {}
    assert _count_alerts(conn) == 0


# ===========================================================================
# 10. test_alert_concurrent_triggers
# ===========================================================================

def test_alert_concurrent_triggers(temp_db):
    """重复触发不创建重复告警事件 (24h 内同 source + rule_type 去重)."""
    conn = get_connection()
    _seed_rules(conn)
    _insert_security_entity_cve(conn, "CVE-2024-0001", 9.5)
    conn.commit()

    engine = AlertEngine()
    results1 = engine.evaluate_all()
    assert results1.get("关键 CVE 告警", -1) == 1

    # 第二次评估 (同 source = CVE-2024-0001, 同 rule_type, 24h 内)
    results2 = engine.evaluate_all()
    assert results2.get("关键 CVE 告警", -1) == 0  # 去重, 不新增

    assert _get_alert_count(conn, "critical_cve") == 1


# ===========================================================================
# 11. test_alert_evaluate_all
# ===========================================================================

def test_alert_evaluate_all(temp_db):
    """evaluate_all 返回包含所有规则名称的统计字典, 数值正确."""
    conn = get_connection()
    _seed_rules(conn)
    _insert_security_entity_cve(conn, "CVE-2024-9991", 9.5)
    _insert_security_entity_cve(conn, "CVE-2024-9992", 9.8)
    conn.commit()

    engine = AlertEngine()
    results = engine.evaluate_all()

    assert isinstance(results, dict)
    # 唯一存活规则 (2026-11-19: tech_stack_cve 已随工坊域退役)
    assert results["关键 CVE 告警"] == 2
    assert _count_alerts(conn) == results["关键 CVE 告警"]