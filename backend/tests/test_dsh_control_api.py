"""dsh 控制面 API 契约测试 — 一键启停 + 配置持久化 (v0.6.3)。"""
from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repository.db import get_connection


@pytest.fixture()
def client(temp_db):
    """temp_db 隔离 + TestClient (dsh gate 由 conftest 注册期快照保证注册)。"""
    with TestClient(app) as c:
        yield c


def _clear_dsh_settings() -> None:
    conn = get_connection()
    conn.execute("DELETE FROM settings WHERE key LIKE 'dsh.%'")
    conn.commit()


def test_status_shape(client: TestClient):
    _clear_dsh_settings()
    r = client.get("/api/dsh/control/status")
    assert r.status_code == 200
    data = r.json()
    for key in ("status", "endpoint", "command_raw", "autostart", "configured", "process"):
        assert key in data
    assert data["status"] == "not_configured"  # 未配置命令时的如实呈现
    assert data["configured"] is False


def test_config_write_and_readback(client: TestClient):
    _clear_dsh_settings()
    r = client.put("/api/dsh/control/config", json={
        "endpoint": "http://127.0.0.1:3999",
        "command": f"{sys.executable} -c \"import time; time.sleep(30)\"",
        "autostart": True,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["config"]["endpoint"] == "http://127.0.0.1:3999"
    assert data["config"]["autostart"] is True
    assert len(data["config"]["command"]) == 3  # shlex 解析为 argv
    # 持久化: 重读 status 反映配置
    r2 = client.get("/api/dsh/control/status")
    assert r2.json()["configured"] is True
    assert r2.json()["autostart"] is True


def test_start_unconfigured_returns_409(client: TestClient):
    _clear_dsh_settings()
    r = client.post("/api/dsh/control/start")
    assert r.status_code == 409
    assert "未配置" in r.json()["error"]


def test_start_stop_lifecycle(client: TestClient):
    _clear_dsh_settings()
    client.put("/api/dsh/control/config", json={
        "command": f"{sys.executable} -c \"import time; time.sleep(30)\"",
    })
    r = client.post("/api/dsh/control/start")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["status"]["running"] is True

    # 幂等 start: 同一 pid
    r2 = client.post("/api/dsh/control/start")
    assert r2.json()["status"]["pid"] == r.json()["status"]["pid"]

    r3 = client.post("/api/dsh/control/stop")
    assert r3.status_code == 200
    assert r3.json()["status"]["running"] is False


def test_restart_unconfigured_returns_409(client: TestClient):
    _clear_dsh_settings()
    r = client.post("/api/dsh/control/restart")
    assert r.status_code == 409
