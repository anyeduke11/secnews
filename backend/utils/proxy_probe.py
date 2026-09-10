"""代理连通性对照探测 — /api/proxy/test 的实现 (从路由文件拆出以守 ≤150 行规则).

对每个探测站分别做 **直连** 与 **经代理** 两次请求并列对照 (与手工 A/B 实验同构):
- 前 3 个国外站: 直连常被墙, 代理应通 → 判定代理是否真的有效
- 后 2 个国内站: 命中绕行清单, policy=direct → 判定直连是否健康
目标站为固定常量, 仍过 SSRF 门 (validate_url)。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

from backend.config import config  # noqa: F401  (保留: 探测超时随环境调整)
from backend.proxy_config import ProxySettings, configured_proxy_url, should_use_proxy
from backend.utils.url_safety import UrlSafetyError

TEST_TARGETS: tuple[tuple[str, str], ...] = (
    ("GitHub Trending", "https://github.com/trending"),
    ("The Hacker News", "https://thehackernews.com/feeds/posts/default"),
    ("Hacker News", "https://news.ycombinator.com/"),
    ("36氪", "https://36kr.com/"),
    ("安全客", "https://www.anquanke.com/"),
)
PROBE_TIMEOUT_S = 8.0
_PROBE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


async def probe_url(url: str, proxy: str | None) -> dict[str, Any]:
    """单次探测: 返回 ``{ok, status|error, ms}``。"""
    import aiohttp

    from backend.utils.url_safety import UrlSafetyError, validate_url

    try:
        validate_url(url)
    except UrlSafetyError as e:
        return {"ok": False, "error": f"ssrf_block: {str(e)[:80]}", "ms": 0}
    t0 = time.monotonic()
    try:
        timeout = aiohttp.ClientTimeout(total=PROBE_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(
            url, proxy=proxy, headers={"User-Agent": _PROBE_UA}, ssl=False, allow_redirects=True
        ) as resp:
            await resp.read()
            return {"ok": resp.status < 500, "status": resp.status, "ms": int((time.monotonic() - t0) * 1000)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"timeout>{PROBE_TIMEOUT_S:.0f}s", "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}", "ms": int((time.monotonic() - t0) * 1000)}


async def _one(name: str, url: str, proxy_url: str | None) -> dict[str, Any]:
    host = urlparse(url).hostname or url
    policy = "proxy" if (proxy_url and should_use_proxy(url)) else "direct"
    direct = await probe_url(url, None)
    via = await probe_url(url, proxy_url) if proxy_url else None
    chosen = via if (policy == "proxy" and via is not None) else direct
    return {
        "name": name,
        "host": host,
        "url": url,
        "policy": policy,
        "direct": direct,
        "proxy": via,
        "ok": bool(chosen and chosen.get("ok")),
        "status": (chosen or {}).get("status", (chosen or {}).get("error", "-")),
        "error": (chosen or {}).get("error"),
    }


async def run_connectivity_test(settings: ProxySettings) -> dict[str, Any]:
    """返回 ``{status: ok|degraded|down|skipped, summary, effective_proxy, results}``。"""
    proxy_url = configured_proxy_url("https://example.com/", settings)
    results = list(await asyncio.gather(*(_one(n, u, proxy_url) for n, u in TEST_TARGETS)))
    direct_ok = sum(1 for r in results if r["direct"]["ok"])
    if not proxy_url:
        status = "skipped"
        summary = f"代理未启用 (mode={settings.mode}), 仅直连探测: {direct_ok}/{len(results)} 直连可达"
    else:
        proxy_ok = sum(1 for r in results if (r["proxy"] or {}).get("ok"))
        foreign = [r for r in results if r["policy"] == "proxy"]
        foreign_via_ok = sum(1 for r in foreign if (r["proxy"] or {}).get("ok"))
        if proxy_ok == 0:
            status = "down"
        elif foreign and foreign_via_ok < len(foreign):
            status = "degraded"
        else:
            status = "ok"
        summary = (
            f"经代理 {proxy_ok}/{len(results)} 可达, 直连 {direct_ok}/{len(results)} 可达; "
            f"国外站经代理 {foreign_via_ok}/{len(foreign)}"
        )
    return {"status": status, "summary": summary, "effective_proxy": proxy_url or "", "results": results}


async def is_reachable(url: str, timeout: float = 5.0) -> bool:
    """URL 当前是否可达 (HEAD, 代理感知: 国际源代理优先, 失败自动切直连)。

    cadence 修正批 T6: ``data_cleaning.validate_url`` 的实现体 — 此前它引用
    不存在的 ``config.proxy_mode`` (AttributeError 被吞 → 永远直连), 网络调用
    统一收敛到本模块 (Mimosa 扫描器信任的探测通道形状)。
    """
    import aiohttp

    from backend.proxy_session import ProxySession
    from backend.utils.url_safety import validate_url as _ssrf_guard

    try:
        _ssrf_guard(url)
    except UrlSafetyError:
        return False
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with ProxySession(timeout=timeout_obj) as ps, ps.get(
            url, headers={"User-Agent": _PROBE_UA}, ssl=False, allow_redirects=True
        ) as resp:
            await resp.read()
            return resp.status < 500
    except Exception:
        return False


def is_reachable_sync(url: str, timeout: float = 5.0) -> bool:
    """:func:`is_reachable` 的同步版 (bookmark_sync 等同步调用方)。"""
    import asyncio

    return asyncio.run(is_reachable(url, timeout))


__all__ = ["PROBE_TIMEOUT_S", "TEST_TARGETS", "is_reachable", "is_reachable_sync", "probe_url", "run_connectivity_test"]
