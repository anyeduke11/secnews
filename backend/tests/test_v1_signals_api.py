"""T15 v1_signals API 端到端测试 (2 个)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1_signals_api import router as v1_signals_router


@pytest.fixture()
def client(temp_db):
    app = FastAPI()
    app.include_router(v1_signals_router)
    return TestClient(app)


def test_list_signals_returns_200_with_empty_items(client) -> None:
    """v1_signals 表空 → 200 + items=[] + total=0 (T15 §通过证据第 1 点 '待办数字可追到实际对象')."""
    r = client.get("/api/v1/signals")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["days"] == 7  # 默认 7


def test_list_signals_with_query_params(client) -> None:
    """?days=30&limit=5 → 参数透传."""
    r = client.get("/api/v1/signals?days=30&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 30
    assert isinstance(body["items"], list)
