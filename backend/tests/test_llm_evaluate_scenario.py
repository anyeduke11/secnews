"""S6 验证 — /api/llm/evaluate 加 scenario 入参 (v0.7.4-image).

重点:
- scenario=None → 走老路径, 零回归
- scenario=deep → resolve_scenario_model(DEEP) → model 注入 result
- scenario=light → resolve_scenario_model(LIGHT) → model 注入 result
- scenario=foo → 200 ok=false error (非法值不抛 500)
- 响应含 provider + model 字段
"""
from __future__ import annotations

from typing import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Iterator:
    from backend.api.llm_status import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def test_evaluate_without_scenario_uses_legacy_path(client):
    """scenario=None: 走老路径, evaluate_article 不被 scenario 解析链干扰."""
    fake = {
        "ok": True,
        "provider": "sensenova",
        "quality_score": 8.0,
        "verdict": "good",
        "key_points": ["a"],
        "summary": "ok",
    }

    async def fake_evaluate(*_a, **_kw):
        return fake

    with patch("backend.services.ai_hub.evaluate_article", new=fake_evaluate):
        r = client.post(
            "/api/llm/evaluate",
            json={"content": "x" * 20, "title": "t"},
        )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["provider"] == "sensenova"
    # 老路径不注入 model 字段 (yaml 自行决定, 由 _eval_model 拿)
    assert "model" not in d


def test_evaluate_with_scenario_deep_picks_deepseek(client, monkeypatch):
    """scenario=deep → model 走 yaml t3_summary = deepseek-v4-pro."""
    fake = {
        "ok": True,
        "provider": "sensenova",
        "quality_score": 8.5,
        "verdict": "deep",
        "key_points": ["a"],
        "summary": "ok",
    }

    async def fake_evaluate(*_a, **_kw):
        return fake

    monkeypatch.delenv("HOTSPOT_SCENARIO_DEEP_MODEL", raising=False)
    with patch("backend.services.ai_hub.evaluate_article", new=fake_evaluate):
        r = client.post(
            "/api/llm/evaluate",
            json={"content": "x" * 20, "scenario": "deep"},
        )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["model"] == "deepseek-v4-pro", (
        f"scenario=deep 应得 deepseek-v4-pro, 实际 {d.get('model')!r}"
    )
    assert d["provider"] == "sensenova"


def test_evaluate_with_scenario_light_picks_flash_lite(client, monkeypatch):
    """scenario=light → model 走 yaml t1_score = sensenova-6.8-flash-lite."""
    fake = {
        "ok": True, "provider": "sensenova", "quality_score": 7.0,
        "verdict": "ok", "key_points": ["a"], "summary": "ok",
    }

    async def fake_evaluate(*_a, **_kw):
        return fake

    monkeypatch.delenv("HOTSPOT_SCENARIO_LIGHT_MODEL", raising=False)
    with patch("backend.services.ai_hub.evaluate_article", new=fake_evaluate):
        r = client.post(
            "/api/llm/evaluate",
            json={"content": "x" * 20, "scenario": "light"},
        )
    assert r.status_code == 200
    d = r.json()
    assert d["model"] == "sensenova-6.8-flash-lite"


def test_evaluate_with_invalid_scenario_returns_ok_false(client):
    """scenario='foo' → 200 ok=false (严格模式, 不 500)."""
    r = client.post(
        "/api/llm/evaluate",
        json={"content": "x" * 20, "scenario": "foo"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert "invalid scenario" in d["error"]
