"""S4 验证 — api/image.py 两端点 (v0.7.4-image).

测试重点:
- 200 + 字段完整 (ok/images/provider/model/latency_ms)
- 空 prompt → 422 (Pydantic min_length=1)
- n=5 → 422 (Pydantic le=4)
- ImageGenerationError → 200 ok=false error 字段 (非 500, 严格模式同 /api/llm/evaluate)
- understand 200 + text
- b64 > 8MB → 422
- audit_log 写入 (mock)
"""
from __future__ import annotations

from typing import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(temp_db, monkeypatch) -> Iterator:
    """FastAPI TestClient (含 image router)。"""
    from backend.api.image import router as image_router

    app = FastAPI()
    app.include_router(image_router)
    yield TestClient(app)

    from backend.repository import db as _db
    try:
        _db.close_db()
    except Exception:
        pass


def test_generate_200(client, monkeypatch):
    """mock ImageGenerationService.generate → 200 + 完整字段。"""
    fake_result = {
        "ok": True,
        "images": [{"url": "https://img.example/x.png"}],
        "provider": "sensenova",
        "model": "sensenova-u1.5-lite",
        "latency_ms": 1234,
    }

    async def fake_generate(*_a, **_kw):
        return fake_result

    monkeypatch.setattr(
        "backend.api.image.ImageGenerationService.generate", fake_generate,
    )

    r = client.post(
        "/api/image/generate",
        json={"prompt": "a cat", "actor": "test"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["images"][0]["url"] == "https://img.example/x.png"
    assert d["provider"] == "sensenova"
    assert d["model"] == "sensenova-u1.5-lite"
    assert d["latency_ms"] == 1234


def test_generate_validation_empty_prompt(client):
    """空 prompt → 422 (Pydantic min_length=1)."""
    r = client.post("/api/image/generate", json={"prompt": "", "actor": "test"})
    assert r.status_code == 422


def test_generate_validation_n_too_large(client):
    """n=5 → 422 (Pydantic le=4)."""
    r = client.post(
        "/api/image/generate",
        json={"prompt": "a cat", "n": 5, "actor": "test"},
    )
    assert r.status_code == 422


def test_generate_image_error_returns_ok_false(client, monkeypatch):
    """ImageGenerationError → 200 {ok: false, error} (严格模式同 /api/llm/evaluate)."""

    async def fake_generate(*_a, **_kw):
        from backend.services.ai_hub.image_service import ImageGenerationError
        raise ImageGenerationError("sensenova 401: invalid api key")

    monkeypatch.setattr(
        "backend.api.image.ImageGenerationService.generate", fake_generate,
    )

    r = client.post("/api/image/generate", json={"prompt": "a cat", "actor": "test"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert "401" in d["error"]


def test_understand_200(client, monkeypatch):
    """understand 200 + text 字段。"""
    fake_result = {
        "ok": True,
        "text": "图中是一只橘猫",
        "provider": "sensenova",
        "model": "sensenova-u1.5-lite",
        "latency_ms": 800,
    }

    async def fake_understand(*_a, **_kw):
        return fake_result

    monkeypatch.setattr(
        "backend.api.image.ImageGenerationService.understand", fake_understand,
    )

    r = client.post(
        "/api/image/understand",
        json={"image_b64": "aGVsbG8gd29ybGQ=", "prompt": "描述", "actor": "test"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["text"] == "图中是一只橘猫"
    assert d["provider"] == "sensenova"


def test_understand_oversize_b64_422(client):
    """b64 > 8MB → 422 (Pydantic max_length)."""
    big_b64 = "x" * (8 * 1024 * 1024 + 1)
    r = client.post(
        "/api/image/understand",
        json={"image_b64": big_b64, "prompt": "描述", "actor": "test"},
    )
    assert r.status_code == 422


def test_audit_recorded_on_image_generate(client, monkeypatch):
    """成功 + 失败路径都写 record_audit。"""

    async def fake_generate(*_a, **_kw):
        return {
            "ok": True, "images": [], "provider": "sensenova",
            "model": "sensenova-u1.5-lite", "latency_ms": 100,
        }

    monkeypatch.setattr(
        "backend.api.image.ImageGenerationService.generate", fake_generate,
    )

    with patch("backend.api.image._audit") as mock_audit:
        r = client.post("/api/image/generate", json={"prompt": "a cat", "actor": "alice"})
        assert r.status_code == 200
        assert mock_audit.called
        # 调用形如 _audit("image.generate", "alice", {"ok": True, "model": "..."})
        args, _ = mock_audit.call_args
        assert args[0] == "image.generate"
        assert args[1] == "alice"
        assert args[2]["ok"] is True
