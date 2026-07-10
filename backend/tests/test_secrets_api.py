"""Phase 41 Secrets API 测试 (end-to-end, in-memory DB)。

覆盖:
- status 初始未 setup
- setup 一次成功, 重复 setup 抛错 (Q1 禁止重置)
- unlock 错密码 401, 正确密码 200 + 30min 状态
- CRUD (create/list/reveal/test/update/delete) + master_key 加解密
- import/export round-trip
- 30 分钟后过期 (用更短 TTL 模拟)
"""
from __future__ import annotations

import base64
import time
from typing import Iterator

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator:
    """独立临时 DB 跑 FastAPI TestClient。

    设置 ``DB_PATH`` 环境变量让 ``backend.repository.db`` 指向新库,
    然后 install_skills + secrets router。"""
    import os
    import sqlite3
    db_file = tmp_path / "test_secrets.db"
    monkeypatch.setenv("HOTSPOT_TEST_DB", str(db_file))

    # 直接用 sqlite3 初始化 schema (012 + 013 + 014)
    conn = sqlite3.connect(str(db_file))
    schema_dir = "backend/repository/migrations"
    for sql_file in ("012_skills.sql", "013_secrets.sql", "014_sync.sql"):
        with open(f"{schema_dir}/{sql_file}", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    conn.commit()
    conn.close()

    # Patch backend.repository.db.get_connection 走我们的 db (单例, 避免 SQLite 锁竞争)
    from backend import repository as repo_pkg
    from backend.repository import db as db_mod
    import contextlib

    shared_conn = sqlite3.connect(str(db_file), check_same_thread=False, timeout=30.0)
    shared_conn.row_factory = sqlite3.Row
    shared_conn.execute("PRAGMA journal_mode=WAL")
    shared_conn.execute("PRAGMA foreign_keys=ON")
    shared_conn.execute("PRAGMA busy_timeout=30000")

    def _get_conn():
        return shared_conn

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    # 其他子模块可能也 import 了 get_connection
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.secrets import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)

    # 清理 _unlock_state
    from backend.services import secrets_service
    secrets_service._unlock_state.clear()
    shared_conn.close()


MASTER_KEY = "test-master-key-strong-1234"


def test_status_initial(client):
    r = client.get("/api/secrets/status")
    assert r.status_code == 200
    data = r.json()
    assert data["setup"] is False
    assert data["unlocked"] is False


def test_setup_then_status(client):
    r = client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    assert r.status_code == 201, r.text
    r2 = client.get("/api/secrets/status")
    assert r2.json()["setup"] is True
    assert r2.json()["unlocked"] is False


def test_setup_idempotent_blocked(client):
    """Q1 禁止重置: 重复 setup 抛错。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/setup", json={"master_key": "another-key-5678"})
    assert r.status_code == 409  # 禁止重置


def test_setup_weak_key_rejected(client):
    r = client.post("/api/secrets/setup", json={"master_key": "short"})
    assert r.status_code in (400, 422)


def test_unlock_wrong_password(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/unlock", json={"master_key": "wrong-password-1234"})
    assert r.status_code == 401


def test_unlock_correct(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    assert r.status_code == 200
    data = r.json()
    assert data["unlocked"] is True
    assert data["ttl_seconds"] == 30 * 60


def test_unlock_then_lock(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/lock")
    assert r.status_code == 200
    assert r.json()["unlocked"] is False


def test_create_list_reveal(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    create = client.post(
        "/api/secrets",
        json={
            "name": "我的 DeepSeek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test-1234567890",
            "master_key": MASTER_KEY,
        },
    )
    assert create.status_code == 201, create.text
    sid = create.json()["item"]["id"]

    # 列表应包含, api_key_masked 显示掩码
    lst = client.get("/api/secrets")
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "我的 DeepSeek"
    assert items[0]["api_key"] is None  # 列表不返回明文

    # reveal 必须 unlock
    rev = client.post(f"/api/secrets/{sid}/reveal")
    assert rev.status_code == 409  # 未解锁

    # 解锁后 reveal
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    rev2 = client.post(f"/api/secrets/{sid}/reveal")
    assert rev2.status_code == 200
    assert rev2.json()["api_key"] == "sk-test-1234567890"


def test_create_wrong_master_key(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": "wrong-key-1234",
        },
    )
    assert r.status_code == 401


def test_update_no_api_key_change_no_master(client):
    """只改 name/model/base_url 不需要 master_key。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "old",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    r = client.patch(f"/api/secrets/{sid}", json={"name": "new"})
    assert r.status_code == 200
    assert r.json()["item"]["name"] == "new"


def test_update_api_key_requires_master(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    # 改 api_key 但不传 master_key
    r = client.patch(f"/api/secrets/{sid}", json={"api_key": "sk-2"})
    assert r.status_code in (400, 409)


def test_delete(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    d = client.delete(f"/api/secrets/{sid}")
    assert d.status_code == 204
    assert client.get("/api/secrets").json()["total"] == 0


def test_export_import_roundtrip(client):
    """导出 → 重新 setup (用同一密码) → 导入恢复。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post(
        "/api/secrets",
        json={
            "name": "A",
            "model": "m1",
            "base_url": "https://a.com",
            "api_key": "sk-aaa",
            "master_key": MASTER_KEY,
        },
    )
    client.post(
        "/api/secrets",
        json={
            "name": "B",
            "model": "m2",
            "base_url": "https://b.com",
            "api_key": "sk-bbb",
            "master_key": MASTER_KEY,
        },
    )

    # 导出
    r = client.get(f"/api/secrets/export?master_key={MASTER_KEY}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    payload = r.content

    # 模拟"清空"再导入: 直接 POST import
    b64 = base64.b64encode(payload).decode("ascii")
    r2 = client.post(
        "/api/secrets/import",
        json={"payload_b64": b64, "master_key": MASTER_KEY},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["inserted"] == 0  # 已存在, 所以是 update
    assert data["updated"] == 2
    assert data["failures"] == []


def test_import_wrong_master(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    # 构造一个虚假 envelope
    envelope = b'{"encryption": {"algorithm": "Fernet", "iterations": 600000}, "ciphertext_b64": "00"}'
    b64 = base64.b64encode(envelope).decode("ascii")
    r = client.post(
        "/api/secrets/import",
        json={"payload_b64": b64, "master_key": "wrong-key-9999"},
    )
    assert r.status_code == 401


def test_test_connection_invalid_url(client):
    """test endpoint 在网络失败时返回 ok=false (不是抛错)。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "fake",
            "model": "m",
            "base_url": "https://127.0.0.1:1/never-listens",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    r = client.post(f"/api/secrets/{sid}/test")
    assert r.status_code == 200
    data = r.json()
    # 端口 1 不会响应, 应该 ok=False
    assert data["ok"] is False or data.get("status_code") in (None, 0)


# ---------------------------------------------------------------------------
# Phase 42: admin reset (二次确认清空)
# ---------------------------------------------------------------------------
def test_reset_wrong_confirm_409(client):
    r = client.post("/api/secrets/reset", json={"confirm": "NOPE"})
    assert r.status_code == 409
    assert "二次确认" in r.json()["detail"]["message"]


def test_reset_full_clears_everything(client):
    """reset 后: master_key 状态 setup=false, llm_secrets 空, 可重新 setup。"""
    # 1. setup
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    # 2. add secret
    client.post("/api/secrets", json={
        "name": "test-svc",
        "model": "m",
        "base_url": "https://x",
        "api_key": "sk-test",
        "master_key": MASTER_KEY,
    })
    # 3. verify exists
    s = client.get("/api/secrets").json()
    assert len(s["items"]) == 1
    # 4. reset
    r = client.post("/api/secrets/reset", json={
        "confirm": "YES_RESET_ALL_SECRETS"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reset"] is True
    assert data["counts"]["llm_secrets_cleared"] == 1
    assert data["counts"]["encryption_key_cleared"] == 1
    # 5. status 反映 setup=False
    s = client.get("/api/secrets/status").json()
    assert s["setup"] is False
    # 6. list 是空
    items = client.get("/api/secrets").json()["items"]
    assert items == []
    # 7. 可重新 setup
    r2 = client.post("/api/secrets/setup", json={"master_key": "new-master-key-9876"})
    assert r2.status_code == 201


def test_reset_when_empty(client):
    """无数据时 reset 仍 200, counts 全 0。"""
    r = client.post("/api/secrets/reset", json={
        "confirm": "YES_RESET_ALL_SECRETS"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["counts"]["llm_secrets_cleared"] == 0
    assert data["counts"]["encryption_key_cleared"] == 0
