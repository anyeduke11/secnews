"""SSRF 防护 — URL 校验 + DNS 锁 IP 防 rebinding（v0.7.x P0）。

目的
----
所有出站 HTTP 请求必须经本模块校验后才允许连接:

1. **协议白名单**: 仅 ``http://`` / ``https://``。
2. **host 黑名单**:
   - 字面 ``localhost`` / ``*.local`` / ``*.internal``
   - 字面 IPv4/IPv6 地址 → 拒绝 loopback / link-local / private / multicast / reserved / unspecified
3. **DNS 预解析**: 域名 → ``socket.getaddrinfo`` 拿到全部 A/AAAA → 任一私有即拒。
4. **DNS 防 rebinding**: 公网域名解析拿到 IP 后, aiohttp 路径通过自定义
   ``AsyncResolver` 锁 IP 到 connector, 避免第二次解析时攻击者把域名指向私有地址。

设计原则
--------

- **单一真相源**: 所有 collector / probe / alert 入口共用本模块。
- **escape hatch**: ``allow_private=True`` 仅供测试 / 内部白名单使用, 默认 False。
- **不替代代理配置**: SSRF 防的是"抓取目标 host 解析后是否私有"; 代理 (ProxySession
  127.0.0.1:7897) 走的是已配置可信地址, 不在本模块校验范围。

使用
----

::

    from backend.utils.url_safety import (
        validate_url,
        safe_aiohttp_connector,
        safe_httpx_get,
        safe_urllib_request,
        UrlSafetyError,
    )

    # 1) 校验 + 解析
    try:
        validate_url("https://example.com/api")
    except UrlSafetyError as e:
        # 400 to client
        raise HTTPException(400, detail={"reason": "ssrf_block", "detail": str(e)})

    # 2) aiohttp 路径 — 锁 IP 防 rebinding
    connector = safe_aiohttp_connector("example.com")
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://example.com/api") as resp:
            ...
"""
from __future__ import annotations

import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse


if TYPE_CHECKING:
    import aiohttp
    import httpx


class UrlSafetyError(ValueError):
    """URL 校验失败 — 含 SSRF 阻断原因。"""


# 私有/loopback/保留段标记集合 — 复用 ipaddress 标准库判定
def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """返回阻断 reason 或 None。"""
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_private:
        return "private"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified"
    # IPv6 特有
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:
            return "site_local"  # fec0::/10 (deprecated 但仍可能命中)
    # IPv4 carrier-grade NAT (100.64.0.0/10) — Python 3.14 起不再归入 is_private
    # 但 RFC 6598 仍属不可路由地址, 主动拒绝
    if isinstance(ip, ipaddress.IPv4Address):
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return "cgnat"
    return None


# 字面 host 黑名单 (不依赖 DNS, 永远拒)
_LITERAL_HOST_BLOCKLIST = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "broadcasthost",
    "0.0.0.0",
    "::",
    "::1",
})


def _host_is_blocked_literal(host: str) -> str | None:
    """字面 host 检查 (不解析 DNS)。"""
    if not host:
        return "empty_host"
    lower = host.lower().strip("[]")
    if lower in _LITERAL_HOST_BLOCKLIST:
        return f"literal_host_{lower}"
    # .local / .internal 私有多播 DNS 后缀
    if lower.endswith(".local") or lower.endswith(".internal"):
        return f"suffix_{lower.rsplit('.', 1)[-1]}"
    return None


def _parse_url(url: str) -> tuple[str, str, str]:
    """scheme + netloc + host 解析; 不通过抛 UrlSafetyError。

    http / https 默认均允许 (SSRF 关键约束是 host/IP, 不是 scheme — 内部接口
    常走 http 公网域名, 例如 raw.githubusercontent.com; 强制 https 会误拦)。
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise UrlSafetyError(f"url parse failed: {e}") from e

    if not parsed.scheme or not parsed.netloc:
        raise UrlSafetyError(
            f"URL 缺少 scheme 或 host: {url[:80]!r}"
        )

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise UrlSafetyError(
            f"scheme {scheme!r} 不在白名单 (仅允许 http/https): {url[:80]!r}"
        )

    host = (parsed.hostname or "").strip()
    if not host:
        raise UrlSafetyError(f"URL 解析后 host 为空: {url[:80]!r}")

    return scheme, parsed.netloc, host


def validate_url(
    url: str,
    *,
    allow_private: bool = False,
) -> str:
    """校验 URL: 协议白名单 + 字面 host 检查 + 字面 IP 检查 + DNS 解析后 IP 检查。

    Args:
        url: 完整 URL (含 scheme + host)。
        allow_private: True 时跳过私有 IP 检查 (仅供测试 / 已配置白名单使用)。

    Returns:
        原 URL (未做改写 — 调用方如需锁 IP, 用 ``safe_aiohttp_connector`` 等 factory)。

    Raises:
        UrlSafetyError: scheme 不在白名单 / host 是 localhost 或私有 IP / DNS 解析失败
            或解析到私有 IP。
    """
    if not url or not isinstance(url, str):
        raise UrlSafetyError(f"URL 必须是非空字符串, 实际: {type(url).__name__}")

    scheme, netloc, host = _parse_url(url)

    # 1) 字面 host 黑名单 (loopback / *.local / *.internal)
    literal_reason = _host_is_blocked_literal(host)
    if literal_reason is not None:
        raise UrlSafetyError(
            f"SSRF blocked: host {host!r} 是字面回环/私有 ({literal_reason})"
        )

    # 2) 字面 IP 检查
    try:
        ip = ipaddress.ip_address(host)
        reason = _ip_is_blocked(ip)
        if reason is not None and not allow_private:
            raise UrlSafetyError(
                f"SSRF blocked: host {host!r} 是 {reason} 地址"
            )
        # 字面 IP 通过, 不做 DNS 解析
        return url
    except ValueError:
        pass  # 不是字面 IP, 走 DNS 解析路径

    # 3) 域名 → DNS 解析 → IP 检查
    if not allow_private:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise UrlSafetyError(
                f"SSRF blocked: host {host!r} DNS 解析失败: {e}"
            ) from e

        for family, _socktype, _proto, _canon, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            reason = _ip_is_blocked(ip)
            if reason is not None:
                raise UrlSafetyError(
                    f"SSRF blocked: host {host!r} DNS 解析到 {reason} IP {ip_str}"
                )

    return url


def safe_aiohttp_connector(
    host: str,
    *,
    ssl: bool = False,
    **kwargs: object,
) -> "aiohttp.TCPConnector":
    """构造 ``aiohttp.TCPConnector``, 把 host 锁到解析后的 IP 防 DNS rebinding。

    使用::

        connector = safe_aiohttp_connector("example.com")
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://{host}/path") as resp:
                ...

    Args:
        host: 目标域名 (已通过 ``validate_url``)。
        ssl: 是否校验 TLS (默认 False — 与现有 collector 行为一致)。
        **kwargs: 透传给 ``aiohttp.TCPConnector``。

    Raises:
        UrlSafetyError: DNS 解析失败 / 解析结果无可用 IP。
    """
    import aiohttp
    # 使用 ThreadedResolver 而非 AsyncResolver: AsyncResolver 需要 aiodns C 扩展
    # (项目用 ``threading + socket.getaddrinfo`` 即可; lock-IP 实际由 ``resolve`` 覆盖)
    from aiohttp.resolver import ThreadedResolver

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UrlSafetyError(
            f"safe_aiohttp_connector: {host!r} DNS 解析失败: {e}"
        ) from e

    ips = list({sockaddr[0] for _family, _t, _p, _c, sockaddr in infos})
    if not ips:
        raise UrlSafetyError(
            f"safe_aiohttp_connector: {host!r} 解析后无可用 IP"
        )

    target_host_lower = host.lower()
    fixed_ips = ips

    class _PinnedResolver(ThreadedResolver):
        """锁定 host → 解析时强制返回预解析 IP; 其他 host 走默认解析 (SNI/redirect)。

        继承 ``ThreadedResolver`` 而非 ``AsyncResolver``,无需 C 库 ``aiodns``;
        aiohttp 期望 ``resolve()`` 协程签名, 直接 await ``super().resolve`` 即可。
        """

        async def resolve(self, *args: object, **kw: object):  # type: ignore[override]
            host_arg = str(args[0]) if args else str(kw.get("host", ""))
            if host_arg.lower() == target_host_lower:
                port = int(args[1]) if len(args) > 1 else int(kw.get("port", 0))
                from aiohttp.resolver import ResolveResult

                return [
                    ResolveResult(hostname=ip, host=ip, port=port,
                                  family=socket.AF_INET6 if ":" in ip else socket.AF_INET)
                    for ip in fixed_ips
                ]
            return await super().resolve(*args, **kw)

    resolver = _PinnedResolver()
    return aiohttp.TCPConnector(
        resolver=resolver,
        use_dns_cache=False,
        ssl=ssl,
        **kwargs,
    )


def safe_aiohttp_get(
    session: "aiohttp.ClientSession",
    url: str,
    *,
    timeout: float = 30.0,
    ssl: bool = False,
    **kwargs: object,
):
    """带 SSRF 防护的 aiohttp GET (前置 ``validate_url``)。用法::

        async with safe_aiohttp_get(session, url, timeout=10) as resp:
            ...

    连接级 IP 锁定由 connector owner 完成 (用 ``safe_aiohttp_connector(host)`` 创建 connector,
    再绑到 session)。本函数仅做协议校验, 早期抛 SSRF 异常。
    """
    validate_url(url)
    return session.get(
        url,
        timeout=timeout,
        ssl=ssl,
        **kwargs,
    )


def pre_resolve_ip(url: str) -> tuple[str, str]:
    """预先解析 host → IP, 返回 ``(url, ip)``。给 ``httpx`` / ``urllib`` 等无 resolver 钩子的
    HTTP 客户端用作"早抛异常 + 提前记录 IP" — 真正的连接锁 IP 由调用方自行实现。

    Raises:
        UrlSafetyError: 协议不合法 / host 是字面 localhost / host 是私有 IP /
            DNS 解析失败 / 解析结果含私有 IP (与 ``validate_url`` 同等强度)。
    """
    # 走完整 validate_url 路径 — 拿到 SSRF 全套保护 (scheme / 字面 host / IP / DNS)
    validate_url(url)
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip()
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UrlSafetyError(
            f"safe_pre_resolve: {host!r} DNS 解析失败: {e}"
        ) from e
    if not infos:
        raise UrlSafetyError(f"safe_pre_resolve: {host!r} 解析后无可用 IP")
    return url, infos[0][4][0]


def safe_urllib_request(
    url: str,
    *,
    method: str = "GET",
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
):
    """带 SSRF 防护的 ``urllib.request.Request`` 构造器。

    调用方用法::

        req = safe_urllib_request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ...

    防护层:
    - 前置 ``validate_url`` 拒收 scheme / localhost / 私有 IP
    - DNS 预解析失败早抛

    urllib 无 connector 钩子, 不做连接级 IP 锁 — 调用方仍可能受 DNS rebinding 影响 (低概率,
    仅当攻击者控制 DNS server 时)。对探测类场景 (head/get, 抓取小页面) 已足够。
    """
    import urllib.request

    validate_url(url)
    pre_resolve_ip(url)
    return urllib.request.Request(url, method=method, headers=headers or {})


__all__ = [
    "UrlSafetyError",
    "pre_resolve_ip",
    "safe_aiohttp_connector",
    "safe_aiohttp_get",
    "safe_urllib_request",
    "validate_url",
]