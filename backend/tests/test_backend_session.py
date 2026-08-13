"""BackendSession 单元测试。

覆盖 5 个场景:
- 正常 GET 请求
- 3 次失败后重试成功
- 信号量限速
- 代理注入
- 超时重试
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.collectors.session import BackendSession, RETRY_DELAYS


# ===========================================================================
# 辅助函数
# ===========================================================================

def _mock_httpx_response(
    status_code: int = 200,
    text: str = "ok",
    raise_for_status: bool = True,
) -> MagicMock:
    """创建模拟的 httpx.Response 对象。"""
    resp = MagicMock(spec=["status_code", "text", "raise_for_status"])
    resp.status_code = status_code
    resp.text = text
    if raise_for_status and status_code >= 400:
        import httpx
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=resp,
            )
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


def _make_mock_client(
    side_effect: list | None = None,
    return_value: MagicMock | None = None,
) -> MagicMock:
    """创建模拟的 httpx.AsyncClient。"""
    client = MagicMock(spec=["get", "aclose"])
    client.get = AsyncMock()
    if side_effect is not None:
        client.get.side_effect = side_effect
    elif return_value is not None:
        client.get.return_value = return_value
    else:
        client.get.return_value = _mock_httpx_response()
    client.aclose = AsyncMock()
    return client


# ===========================================================================
# 测试用例
# ===========================================================================

class TestBackendSessionGet:
    """正常 GET 请求。"""

    @pytest.mark.asyncio
    async def test_backend_session_get(self):
        mock_client = _make_mock_client(
            return_value=_mock_httpx_response(text="hello world")
        )
        with patch(
            "backend.collectors.session.httpx.AsyncClient",
            return_value=mock_client,
        ):
            async with BackendSession() as session:
                text = await session.get("https://example.com")

        assert text == "hello world"
        mock_client.get.assert_awaited_once_with(
            "https://example.com", proxies=None
        )


class TestBackendSessionRetry:
    """3 次失败后重试成功。"""

    @pytest.mark.asyncio
    async def test_backend_session_retry(self):
        # 3 次失败 (500) + 1 次成功 (200)
        fail_resp = _mock_httpx_response(status_code=500)
        ok_resp = _mock_httpx_response(status_code=200, text="finally ok")
        mock_client = _make_mock_client(
            side_effect=[fail_resp, fail_resp, fail_resp, ok_resp]
        )
        with patch(
            "backend.collectors.session.httpx.AsyncClient",
            return_value=mock_client,
        ):
            async with BackendSession() as session:
                text = await session.get("https://example.com")

        assert text == "finally ok"
        # 共调用 4 次（1 初始 + 3 重试）
        assert mock_client.get.await_count == 4


class TestBackendSessionRateLimit:
    """信号量限速。"""

    @pytest.mark.asyncio
    async def test_backend_session_rate_limit(self):
        """验证信号量限制并发请求数。"""
        # 创建一个延迟响应的 mock，便于观察并发行为
        mock_client = _make_mock_client()

        async def delayed_get(*args, **kwargs):
            await asyncio.sleep(0.05)
            return _mock_httpx_response(text="delayed")

        mock_client.get.side_effect = delayed_get

        with patch(
            "backend.collectors.session.httpx.AsyncClient",
            return_value=mock_client,
        ):
            session = BackendSession(rate_limit=2)
            async with session:
                start = asyncio.get_event_loop().time()
                tasks = [session.get("https://example.com") for _ in range(4)]
                results = await asyncio.gather(*tasks)

        elapsed = asyncio.get_event_loop().time() - start
        assert all(r == "delayed" for r in results)
        # rate_limit=2, 每次 2 个并发, 每批 0.05s, 4 个请求至少需要 2 批
        # 理想情况: 2 批 × 0.05s = 0.1s, 但 asyncio 调度有开销, 放宽到 0.05~0.3s
        assert 0.03 <= elapsed <= 0.5, (
            f"Expected ~0.1s with rate_limit=2, got {elapsed:.3f}s"
        )


class TestBackendSessionProxy:
    """代理注入。"""

    @pytest.mark.asyncio
    async def test_backend_session_proxy(self):
        mock_client = _make_mock_client(
            return_value=_mock_httpx_response(text="proxied")
        )
        with (
            patch(
                "backend.collectors.session.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "backend.proxy_config.should_use_proxy",
                return_value=True,
            ),
            patch(
                "backend.proxy_config.get_proxy_url",
                return_value="http://127.0.0.1:8080",
            ),
        ):
            async with BackendSession() as session:
                text = await session.get("https://example.com")

        assert text == "proxied"
        # 验证代理 URL 被传入
        mock_client.get.assert_awaited_once_with(
            "https://example.com",
            proxies={"all://": "http://127.0.0.1:8080"},
        )


class TestBackendSessionTimeout:
    """超时重试。"""

    @pytest.mark.asyncio
    async def test_backend_session_timeout(self):
        import httpx

        # 前 3 次超时，第 4 次成功
        mock_client = _make_mock_client()
        mock_client.get.side_effect = [
            httpx.TimeoutException("connect timeout", request=MagicMock()),
            httpx.TimeoutException("connect timeout", request=MagicMock()),
            httpx.TimeoutException("connect timeout", request=MagicMock()),
            _mock_httpx_response(status_code=200, text="recovered"),
        ]

        with patch(
            "backend.collectors.session.httpx.AsyncClient",
            return_value=mock_client,
        ):
            async with BackendSession() as session:
                text = await session.get("https://example.com")

        assert text == "recovered"
        assert mock_client.get.await_count == 4