"""dsh_api 契约测试 (v0.6 P0).

覆盖:
  1. GET /api/dsh/health — DSH 不可达时返回 disconnected + llm_direct fallback
  2. POST /api/dsh/task — DSH 不可达时降级 LLM, 返回 agent=llm_direct
  3. GET /api/dsh/session/{id} — 查询不存在/存在的会话
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api import dsh_api
from backend.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """DSH 不可达的 TestClient."""
    # 确保 dsh extension gate 开启 (conftest autouse 已全开, 显式再保一遍)
    monkeypatch.setenv("HOTSPOT_FEATURE_GATES", '{"extensions": {"dsh": true}}')
    with TestClient(app) as c:
        yield c


def test_health_disconnected(client: TestClient):
    """DSH 不可达 → status=disconnected, fallback=llm_direct."""
    with patch.object(dsh_api._dsh_client, "health_check", return_value=False):
        r = client.get("/api/dsh/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "disconnected"
    assert data["fallback"] == "llm_direct"


def test_health_connected(client: TestClient):
    """DSH 可达 → status=connected, fallback=none."""
    with patch.object(dsh_api._dsh_client, "health_check", return_value=True):
        r = client.get("/api/dsh/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "connected"
    assert data["fallback"] == "none"


def test_task_fallback_llm(client: TestClient):
    """DSH 不可达 → POST /task 降级 LLM, agent=llm_direct."""
    with patch.object(dsh_api._dsh_client, "send_task", side_effect=ConnectionError("DSH down")):
        with patch("backend.services.dsh.task_router.llm_service") as mock_llm:
            mock_llm.score = AsyncMock(return_value=7.5)
            r = client.post("/api/dsh/task", json={"task_type": "chat", "payload": {"content": "hi"}})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["agent"] == "llm_direct"
    assert data["result"] == 7.5


def test_session_not_found(client: TestClient):
    """查询不存在的会话."""
    r = client.get("/api/dsh/session/nonexistent")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"] == "session not found"
