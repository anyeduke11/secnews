"""S3 验证 — ImageGenerationService 复用 Batch ⑥ 凭据链 (v0.7.4-image).

测试重点:
- 凭据空 → ImageGenerationError 含 key_source
- 200 → 完整 dict (ok/images/provider/model/latency_ms)
- 401 → 异常 + record_llm_call ok=False 落
- 超时 → 异常
- 理解路径返回 text
- b64 超限 → 异常
- watermark 入参正确进 payload
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.ai_hub.image_service import (
    ImageGenerationError,
    ImageGenerationService,
)
from backend.services.ai_hub.scenarios import Scenario


def _mock_ai_resolve_key(return_value: str = "test-key", key_source: str = "env"):
    """mock AIService._resolve_api_key + _key_source (Batch ⑥ 单点)."""
    ai = MagicMock()
    ai._resolve_api_key.return_value = return_value
    ai._key_source.return_value = key_source
    ai._base_url.return_value = "https://token.sensenova.cn/v1"
    ai._config_source.return_value = "default"
    return ai


def test_generate_empty_prompt_raises():
    svc = ImageGenerationService()
    with patch.object(svc, "_ai", _mock_ai_resolve_key()):
        with pytest.raises(ImageGenerationError, match="prompt 不能为空"):
            asyncio.run(svc.generate(""))


def test_generate_no_key_raises_with_key_source(monkeypatch):
    """凭据空 + key_source='none' → 异常信息含 key_source 提示。"""
    monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
    svc = ImageGenerationService()
    with patch.object(svc, "_ai", _mock_ai_resolve_key(return_value="", key_source="none")):
        with pytest.raises(ImageGenerationError, match=r"key_source=none"):
            asyncio.run(svc.generate("a cat"))


def test_generate_200_returns_images(monkeypatch):
    """200 → dict 含 ok=True / images / provider / model / latency_ms."""
    svc = ImageGenerationService()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"url": "https://img.example/x.png"}, {"b64_json": "abc"}],
    }

    async def fake_post(*_args, **_kw):
        return mock_resp

    with patch.object(svc, "_ai", _mock_ai_resolve_key()), \
         patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = asyncio.run(svc.generate("a cat"))

    assert result["ok"] is True
    assert len(result["images"]) == 2
    assert result["images"][0]["url"] == "https://img.example/x.png"
    assert result["provider"] == "sensenova"
    assert result["model"] == "sensenova-u1.5-lite"
    assert result["latency_ms"] > 0
    assert isinstance(result["latency_ms"], int)


def test_generate_401_raises(monkeypatch):
    """401 → ImageGenerationError, record_llm_call ok=False 落。"""
    svc = ImageGenerationService()

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "invalid api key"

    async def fake_post(*_args, **_kw):
        return mock_resp

    with patch.object(svc, "_ai", _mock_ai_resolve_key()), \
         patch.object(httpx.AsyncClient, "post", new=fake_post), \
         patch("backend.services.ai_hub.image_service.ImageGenerationService._record") as mock_record:
        with pytest.raises(ImageGenerationError, match=r"sensenova 401"):
            asyncio.run(svc.generate("a cat"))
        # 验证 audit 落了一次 ok=False
        assert mock_record.called
        kwargs = mock_record.call_args.kwargs
        assert kwargs["ok"] is False
        assert "401" in kwargs["error"]


def test_generate_timeout_raises(monkeypatch):
    """TimeoutException → ImageGenerationError 含 '上游超时'."""
    svc = ImageGenerationService()

    async def fake_post(*_args, **_kw):
        raise httpx.TimeoutException("read timed out")

    with patch.object(svc, "_ai", _mock_ai_resolve_key()), \
         patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(ImageGenerationError, match=r"上游超时"):
            asyncio.run(svc.generate("a cat"))


def test_understand_returns_text(monkeypatch):
    """understand 200 → dict.text 含 LLM 输出。"""
    svc = ImageGenerationService()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "图中是一只猫"}}],
    }

    async def fake_post(*_args, **_kw):
        return mock_resp

    with patch.object(svc, "_ai", _mock_ai_resolve_key()), \
         patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = asyncio.run(svc.understand("aGVsbG8=", "描述这张图"))

    assert result["ok"] is True
    assert result["text"] == "图中是一只猫"
    assert result["provider"] == "sensenova"
    assert result["model"] == "sensenova-u1.5-lite"
    assert result["latency_ms"] > 0


def test_understand_oversize_b64_raises():
    """image_b64 > 8MB → ImageGenerationError 限上限。"""
    svc = ImageGenerationService()
    big_b64 = "x" * (8 * 1024 * 1024 + 1)  # 1 byte over
    with patch.object(svc, "_ai", _mock_ai_resolve_key()):
        with pytest.raises(ImageGenerationError, match=r"超 8MB 上限"):
            asyncio.run(svc.understand(big_b64, "描述"))


def test_watermark_true_passed_to_payload(monkeypatch):
    """watermark=True → payload.watermark=True (sensenova 计费开关)."""
    svc = ImageGenerationService()
    captured_payload: list[dict] = []

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}

    async def fake_post(self_or_url, url=None, **kw):
        # 兼容不同 httpx 签名: 既可能 self.post(url, json=...) 也可能 client.post(url, ...)
        if isinstance(self_or_url, str) and url is None:
            # client.post(url, json=payload) 的 url 参数
            captured_payload.append(kw.get("json", {}))
        else:
            captured_payload.append(kw.get("json", {}))
        return mock_resp

    with patch.object(svc, "_ai", _mock_ai_resolve_key()), \
         patch.object(httpx.AsyncClient, "post", new=fake_post):
        asyncio.run(svc.generate("a cat", watermark=True))

    assert len(captured_payload) == 1
    assert captured_payload[0]["watermark"] is True
    assert captured_payload[0]["model"] == "sensenova-u1.5-lite"
    assert captured_payload[0]["prompt"] == "a cat"
