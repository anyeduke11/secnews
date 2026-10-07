"""S6 验证 — /api/llm/evaluate 加 scenario 入参 (v0.7.4-image).

重点:
- scenario=None → 走老路径, 零回归
- scenario=deep → resolve_scenario_model(DEEP) → model 注入 result
- scenario=light → resolve_scenario_model(LIGHT) → model 注入 result
- scenario=foo → 200 ok=false error (非法值不抛 500)
- 响应含 provider + model 字段
"""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

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
    """scenario=deep → model 走 yaml t3_summary (e620b20: deepseek-v4.1-flash)."""
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
    assert d["model"] == "deepseek-v4.1-flash", (
        f"scenario=deep 应得 yaml t3_summary.model, 实际 {d.get('model')!r}"
    )
    assert d["provider"] == "sensenova"


def test_evaluate_with_scenario_light_picks_flash_lite(client, monkeypatch):
    """scenario=light → model 走 yaml t1_score (DEV-0180 接线后为 pi/claude-sonnet-4-5)。"""
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
    # 期望值动态取自 llm.yaml t1_score.model — 契约是 "light 跟随 t1_score
    # override", 模型名随 llm.yaml 演进, 写死会随配置切换碎掉。
    # P0-1 后 t1_score.model='' (pi 空串语义: 不下传 --model) — 空串时
    # resolve 合法回落 provider.models.score, 只断言 ok 不断言具体模型。
    from pathlib import Path

    import yaml
    yaml_path = Path(__file__).resolve().parents[2] / "config" / "llm.yaml"
    expected = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))[
        "task_overrides"
    ]["t1_score"]["model"]
    if expected:
        assert d["model"] == expected, (
            f"scenario=light 应得 yaml t1_score.model={expected!r}, 实际 {d.get('model')!r}"
        )
    else:
        assert d.get("model"), (
            "scenario=light 在 yaml 空 model 下应回落 provider.models.score (非空)"
        )


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
