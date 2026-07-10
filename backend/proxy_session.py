# 代理感知的 aiohttp session 包装器
# 所有采集器统一通过此模块创建 HTTP session，自动应用代理配置
#
# 重要：get()/post() 返回的是 aiohttp 的 _RequestContextManager，
# 可直接用于 async with，不要 await 返回值。

import aiohttp
from typing import Optional
from proxy_config import get_proxy_url, should_use_proxy


class ProxySession:
    """
    代理感知的 HTTP session 包装器。
    用法与 aiohttp.ClientSession 相同，自动根据全局代理配置注入 proxy 参数。

    示例:
        async with ProxySession() as session:
            async with session.get('http://example.com') as resp:
                text = await resp.text()
    """

    def __init__(self, headers: Optional[dict] = None, timeout: Optional[aiohttp.ClientTimeout] = None):
        self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)

    def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """返回 _RequestContextManager，可直接用于 async with"""
        if should_use_proxy(url):
            proxy = get_proxy_url(url)
            if proxy:
                kwargs["proxy"] = proxy
        return self._session.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """返回 _RequestContextManager，可直接用于 async with"""
        if should_use_proxy(url):
            proxy = get_proxy_url(url)
            if proxy:
                kwargs["proxy"] = proxy
        return self._session.post(url, **kwargs)

    async def close(self):
        await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
