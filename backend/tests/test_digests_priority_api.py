"""DEV-0177 — GET /api/digests/priority (SK-01 T0.5 收敛) API 测试。

覆盖:
- 正常返回: compute 结果透传 + cached=False + practice_partitions 在响应里
- TTL 缓存: TTL 内二次请求命中缓存 (service 只被调用一次), force=True 强制重算
- 优雅降级: compute 抛异常 → 200 + fallback 错误态 (不 500)
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import digests as digests_api
from backend.api import register_routers
from backend.exceptions import register_exception_handlers

_FAKE_RESULT = {
    "top_items": [
        {"title": "CVE-2026-1234 漏洞复现与分析", "practice_domain": "vuln_research"},
        {"title": "等保 2.0 测评要点", "practice_domain": "compliance"},
    ],
    "watchlist_changes": [],
    "suggested_actions": [],
    "generated_at": "2026-09-12T00:00:00Z",
    "mode": "dsh",
    "interest_domains": ["vuln_research"],
    "practice_partitions": {
        "vuln_research": [{"title": "CVE-2026-1234 漏洞复现与分析", "practice_domain": "vuln_research"}],
        "compliance": [{"title": "等保 2.0 测评要点", "practice_domain": "compliance"}],
    },
}


@pytest.fixture
def client():
    app = FastAPI()
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_cache():
    digests_api._priority_cache["ts"] = 0.0
    digests_api._priority_cache["data"] = {}
    yield
    digests_api._priority_cache["ts"] = 0.0
    digests_api._priority_cache["data"] = {}


def _patch_compute(monkeypatch: pytest.MonkeyPatch, counter: list[int], result=None, exc: Exception | None = None):
    class _FakeService:
        def compute(self):
            counter[0] += 1
            if exc is not None:
                raise exc
            return result

    monkeypatch.setattr(digests_api, "_priority_service", lambda: _FakeService())


class TestPriorityDigestAPI:
    def test_returns_compute_result(self, client, monkeypatch):
        counter = [0]
        _patch_compute(monkeypatch, counter, result=_FAKE_RESULT)
        r = client.get("/api/digests/priority")
        assert r.status_code == 200
        body = r.json()
        assert body["cached"] is False
        assert body["mode"] == "dsh"
        assert body["interest_domains"] == ["vuln_research"]
        assert "vuln_research" in body["practice_partitions"]
        assert counter[0] == 1

    def test_ttl_cache_hits_and_force_bypasses(self, client, monkeypatch):
        counter = [0]
        _patch_compute(monkeypatch, counter, result=_FAKE_RESULT)
        client.get("/api/digests/priority")
        r2 = client.get("/api/digests/priority")
        assert r2.json()["cached"] is True
        assert counter[0] == 1, "TTL 内二次请求不得重算"
        r3 = client.get("/api/digests/priority?force=true")
        assert r3.json()["cached"] is False
        assert counter[0] == 2

    def test_compute_failure_degrades_gracefully(self, client, monkeypatch):
        counter = [0]
        _patch_compute(monkeypatch, counter, exc=RuntimeError("dsh + ai_hub both failed"))
        r = client.get("/api/digests/priority")
        assert r.status_code == 200, "降级不得 500"
        body = r.json()
        assert body["mode"] == "fallback_error"
        assert body["top_items"] == []
        assert body["practice_partitions"] is None
