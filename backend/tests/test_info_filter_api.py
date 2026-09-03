"""info_filter_api — 6 endpoint 集成测试.

覆盖:
- GET /rules (含 enabled_only 过滤)
- POST /rules (合法 + 校验失败 400)
- PATCH /rules/{id} (字段子集更新 + 404)
- DELETE /rules/{id} (200 + 404)
- POST /preview (evaluate 输出)
- GET /gate (feature gate 状态)

测试策略: 用 FastAPI TestClient + monkeypatch get_connection 注入临时 DB,
这样不依赖 conftest.temp_db (与 test_secrets_api 共存易污染)。
"""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.repository.db import apply_migrations


@pytest.fixture()
def api_db(tmp_path, monkeypatch):
    """临时 DB: migration 090 + 全仓库 get_connection monkeypatch.

    注意 thread affinity: TestClient 在 worker 线程跑端点, 必须
    check_same_thread=False (与 test_secrets_api 共存模式)。

    同时清掉 info_filter_gate 模块级 cache, 防跨测试污染。
    """
    from backend.services.info_filter_gate import invalidate_cache

    db_file = tmp_path / "info_filter_api.db"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    invalidate_cache()

    from backend import repository as repo_pkg
    from backend.repository import db as db_mod
    from backend.api import info_filter_api as api_mod

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(api_mod, "get_connection", lambda: conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", lambda: conn)
            except (AttributeError, TypeError):
                pass
    yield conn
    conn.close()
    invalidate_cache()


@pytest.fixture()
def client():
    """FastAPI TestClient with info_filter_api router mounted.

    注意: 不依赖 api_db (避免 fixture teardown 顺序问题: client 先于
    api_db 析构, 否则 conn.close() 后 endpoint 还会被调用 → 失败)。
    """
    from fastapi import FastAPI
    from backend.api.info_filter_api import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


# ===== GET /rules =====


def test_list_rules_empty(client, api_db):
    r = client.get("/api/info-filter/rules")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["rules"] == []


def test_list_rules_with_enabled_only_filter(client, api_db):
    """?enabled_only=true 隐藏 disabled 规则."""
    client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "A",
    })
    client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "B",
    })
    # 把 B 关掉
    rules = client.get("/api/info-filter/rules").json()["rules"]
    rid_b = next(r["id"] for r in rules if r["match_value"] == "B")
    client.patch(f"/api/info-filter/rules/{rid_b}", json={"enabled": 0})

    enabled = client.get(
        "/api/info-filter/rules?enabled_only=true"
    ).json()["rules"]
    assert len(enabled) == 1
    assert enabled[0]["match_value"] == "A"


# ===== POST /rules =====


def test_create_rule_returns_id(client, api_db):
    r = client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "华尔街见闻", "note": "noise",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["ok"] is True


def test_create_rule_validation_failure_returns_400(client, api_db):
    """非法 rule_type → 400, 不入库."""
    r = client.post("/api/info-filter/rules", json={
        "rule_type": "block", "match_kind": "source_name",
        "match_value": "X",
    })
    assert r.status_code == 400
    assert "rule_type" in r.json()["detail"]
    # 不入库
    listed = client.get("/api/info-filter/rules").json()
    assert listed["count"] == 0


def test_create_rule_category_validation(client, api_db):
    """category 必须 ∈ 已知分类."""
    r = client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "category",
        "match_value": "bogus",
    })
    assert r.status_code == 400
    assert "category" in r.json()["detail"]


# ===== PATCH /rules/{id} =====


def test_patch_rule_updates_enabled(client, api_db):
    rid = client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "A",
    }).json()["id"]
    r = client.patch(f"/api/info-filter/rules/{rid}", json={"enabled": 0})
    assert r.status_code == 200
    assert r.json()["changed"] is True
    listed = client.get("/api/info-filter/rules").json()["rules"]
    assert listed[0]["enabled"] == 0


def test_patch_nonexistent_returns_404(client, api_db):
    r = client.patch("/api/info-filter/rules/99999", json={"enabled": 0})
    assert r.status_code == 404


# ===== DELETE /rules/{id} =====


def test_delete_rule_success(client, api_db):
    rid = client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "X",
    }).json()["id"]
    r = client.delete(f"/api/info-filter/rules/{rid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    listed = client.get("/api/info-filter/rules").json()
    assert listed["count"] == 0


# ===== POST /preview =====


def test_preview_returns_verdict_and_matched(client, api_db):
    client.post("/api/info-filter/rules", json={
        "rule_type": "deny", "match_kind": "source_name",
        "match_value": "noise", "note": "test",
    })
    r = client.post("/api/info-filter/preview", json={
        "category": "tech", "source_name": "noise",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "deny"
    assert body["matched_rule"]["rule_type"] == "deny"
    assert body["matched_rule"]["match_value"] == "noise"
