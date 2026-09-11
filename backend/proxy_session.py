"""代理感知的 aiohttp session 包装器 — 所有采集器的代理兜底层统一入口。

用法与 aiohttp.ClientSession 相同; ``get()`` / ``post()`` 返回可 ``async with`` 的对象::

    async with ProxySession(headers=..., timeout=...) as session:
        async with session.get("https://github.com/trending", ssl=False) as resp:
            html = await resp.text()

cadence 修正批 T5 (代理内置可选项 + 失效自动切回直连):
- 修正导入: 此前 ``from proxy_config import ...`` 裸导入在包内 ModuleNotFoundError,
  ``collectors.base.ProxySession`` 因此永远是 None, fetchers/bid/github 的"代理兜底"
  在代码层面就不存在 (与 proxy_config.json mode=off 叠加成双重失效)。
- 请求级回退: 按 ``should_use_proxy(url)`` 决定是否注入 proxy; 经代理的请求若因
  **代理链路** 失败 (连不上代理 / 代理拒绝 CONNECT / 经代理超时或断连) → 立刻摘掉
  proxy 用同一 session **直连重试一次**, 并 ``mark_proxy_failure`` 回写熔断器;
  代理请求成功则 ``mark_proxy_success``。目标站自身的 4xx/5xx 是正常响应, 不触发回退。
- 熔断期 (``proxy_circuit_open``) ``should_use_proxy`` 直接为 False → 第一跳就是直连,
  零额外开销; 窗口过后半开, 下一次代理请求即探测。
- SSRF: 进入本层的 URL 先过 ``validate_url`` (与 fetchers/BackendSession 同门)。
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import aiohttp

from backend.logging_config import logger
from backend.proxy_config import (
    get_proxy_url,
    mark_proxy_failure,
    mark_proxy_success,
    should_use_proxy,
)
from backend.utils.url_safety import validate_url

_log = logger.bind(component="proxy_session")

# 视为"代理链路失败"的异常。目标站返回的 HTTP 状态不在此列 (那是正常响应)。
PROXY_FAILURE_EXC: tuple[type[BaseException], ...] = (
    aiohttp.ClientProxyConnectionError,
    aiohttp.ClientHttpProxyError,
    aiohttp.ClientConnectorError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ServerTimeoutError,
    asyncio.TimeoutError,
)


class _ProxyAwareRequest:
    """``async with`` 上下文: 先经代理请求, 代理链路失败 → 摘掉 proxy 直连重试一次。"""

    def __init__(self, session: aiohttp.ClientSession, method: str, url: str,
                 proxy_url: str | None, kwargs: dict) -> None:
        self._session = session
        self._method = method
        self._url = url
        self._proxy_url = proxy_url
        self._kwargs = kwargs
        self._cm = None
        self.via_proxy = False
        self.fell_back = False

    async def __aenter__(self) -> aiohttp.ClientResponse:
        if self._proxy_url:
            cm = self._session.request(self._method, self._url, proxy=self._proxy_url, **self._kwargs)
            try:
                resp = await cm.__aenter__()
            except PROXY_FAILURE_EXC as e:
                opened = mark_proxy_failure(e)
                host = urlparse(self._url).hostname or self._url[:60]
                _log.warning(
                    f"proxy request failed for {host} ({type(e).__name__}: {str(e)[:80]}), "
                    f"falling back to direct" + (" [proxy circuit OPENED → all direct]" if opened else "")
                )
                self.fell_back = True
            else:
                mark_proxy_success()
                self.via_proxy = True
                self._cm = cm
                return resp
        self._cm = self._session.request(self._method, self._url, **self._kwargs)
        return await self._cm.__aenter__()

    async def __aexit__(self, *exc) -> bool:
        if self._cm is None:
            return False
        return await self._cm.__aexit__(*exc)

    def __await__(self):
        return self.__aenter__().__await__()


class ProxySession:
    """代理感知的 HTTP session 包装器 (直连优先架构下的兜底层)。"""

    def __init__(self, headers: dict | None = None, timeout: aiohttp.ClientTimeout | None = None):
        self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)

    def request(self, method: str, url: str, **kwargs) -> _ProxyAwareRequest:
        """返回可 ``async with`` 的请求对象; 代理注入 + 失败回退见模块 docstring。"""
        validate_url(url)
        proxy_url = None
        if "proxy" in kwargs:
            # 调用方显式指定 (如 /api/proxy/test 对照实验): 尊重, 但仍走回退逻辑
            proxy_url = kwargs.pop("proxy") or None
        elif should_use_proxy(url):
            proxy_url = get_proxy_url(url)
        return _ProxyAwareRequest(self._session, method, url, proxy_url, kwargs)

    def get(self, url: str, **kwargs) -> _ProxyAwareRequest:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> _ProxyAwareRequest:
        return self.request("POST", url, **kwargs)

    async def close(self):
        await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()


__all__ = ["PROXY_FAILURE_EXC", "ProxySession"]
