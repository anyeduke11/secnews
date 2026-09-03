"""BackendSession — httpx 统一 HTTP 客户端。

内置 proxy / retry / rate-limit / timeout / SSRF 校验 支持。

Usage::

    async with BackendSession() as session:
        text = await session.get("https://example.com")

v0.7.x P0: 加 SSRF 校验 — 所有 GET 入口经 ``url_safety.validate_url`` 阻断
localhost / 私有 IP / 非法 scheme。
"""

from __future__ import annotations

import asyncio

from backend.logging_config import logger
from backend.utils.url_safety import UrlSafetyError, validate_url

try:
    import httpx

    HAS_HTTPX = True
except ImportError:  # pragma: no cover
    HAS_HTTPX = False
    httpx = None  # type: ignore[assignment]


RETRY_DELAYS = [1, 3, 10]
"""指数退避延迟（秒），最多重试 3 次"""


class BackendSession:
    """httpx 统一 HTTP 客户端。

    在 async with 上下文中创建 httpx.AsyncClient，自动注入代理、
    指数退避重试、信号量限速和超时配置。

    Args:
        rate_limit: 每秒最大并发请求数（默认 5）。
        connect_timeout: 连接超时秒数（默认 10）。
        read_timeout: 读取超时秒数（默认 30）。
        headers: 默认请求头。
    """

    def __init__(
        self,
        rate_limit: int = 5,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for BackendSession. "
                "Install it with: pip install httpx"
            )

        self._semaphore = asyncio.Semaphore(rate_limit)
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BackendSession:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                self._read_timeout,
                connect=self._connect_timeout,
            ),
            headers=self._headers,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, **kwargs: object) -> str:
        """发送 GET 请求，返回响应文本。

        Args:
            url: 请求 URL。
            **kwargs: 传递给 ``httpx.AsyncClient.get`` 的额外参数。

        Returns:
            响应文本。

        Raises:
            RuntimeError: 未在 ``async with`` 上下文内调用。
            httpx.HTTPError: 所有重试均失败后抛出。
            UrlSafetyError: URL 是 localhost / 私有 IP / 非 http(s) (v0.7.x P0 SSRF 防护)。
        """
        if self._client is None:
            raise RuntimeError(
                "BackendSession must be used as async context manager"
            )

        # v0.7.x P0: SSRF 防护 — 拒绝 localhost / 私有 IP / 非法 scheme
        validate_url(url)

        # 延迟导入避免循环依赖
        from backend.proxy_config import get_proxy_url, should_use_proxy

        last_exc: Exception | None = None

        for attempt in range(len(RETRY_DELAYS) + 1):
            async with self._semaphore:
                try:
                    # 按 URL 决定是否走代理
                    proxies: dict[str, str] | None = None
                    if should_use_proxy(url):
                        proxy_url = get_proxy_url(url)
                        if proxy_url:
                            proxies = {"all://": proxy_url}

                    resp = await self._client.get(
                        url, proxies=proxies, **kwargs
                    )

                    # 5xx / 429 → 重试
                    if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                        if attempt < len(RETRY_DELAYS):
                            delay = RETRY_DELAYS[attempt]
                            logger.warning(
                                f"HTTP {resp.status_code} for {url}, "
                                f"retrying in {delay}s "
                                f"(attempt {attempt + 1}/{len(RETRY_DELAYS)})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        resp.raise_for_status()

                    return resp.text

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exc = e
                    if attempt < len(RETRY_DELAYS):
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            f"Request error for {url}: "
                            f"{type(e).__name__}: {e!s}, "
                            f"retrying in {delay}s "
                            f"(attempt {attempt + 1}/{len(RETRY_DELAYS)})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise

        # 所有重试耗尽（仅当 5xx/429 且 raise_for_status 未抛出时到达此处，
        # 但该路径理论上不会执行，因为 raise_for_status 会抛出异常）
        if last_exc is not None:
            raise last_exc
        raise httpx.HTTPError(f"All retries exhausted for {url}")


__all__ = [
    "HAS_HTTPX",
    "RETRY_DELAYS",
    "BackendSession",
]