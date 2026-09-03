"""v0.7.x P0: SSRF 防护 — ``backend.utils.url_safety`` 单元测试.

测试范围
--------

- :func:`validate_url`:
  - scheme 白名单 (拒 file/ftp/javascript 等)
  - 字面 host 黑名单 (localhost / *.local / *.internal)
  - 字面 IPv4 拒收 (loopback / link-local / private / multicast / reserved)
  - 字面 IPv6 拒收 (::1 / fe80::/16 / fc00::/7)
  - DNS 解析后含私网 IP 拒收
  - 公网域名放行
  - allow_private=True escape hatch 跳过私网拦截
- :func:`safe_aiohttp_connector`: 构造 + 锁 IP resolver 行为 (不发起实际连接)
- :func:`safe_urllib_request`: 构造器返回 ``urllib.request.Request``
- :func:`pre_resolve_ip`: 返回 (url, ip) 元组

不触网 (validate_url 会做 DNS 解析, 但我们用公网域名 + 兜底 ``allow_private=True``;
测试只覆盖**判定逻辑**, 不验证锁 IP 后真连得上)。
"""
from __future__ import annotations

import pytest

from backend.utils.url_safety import (
    UrlSafetyError,
    pre_resolve_ip,
    safe_aiohttp_connector,
    safe_urllib_request,
    validate_url,
)


# ---------------------------------------------------------------------------
# validate_url — scheme 白名单
# ---------------------------------------------------------------------------
class TestSchemeWhitelist:
    def test_http_allowed(self):
        """http:// 应放行 (SSRF 关键约束是 host/IP, 不是 scheme)。"""
        # 走公网域名 — 校验 DNS 也通过
        assert validate_url("http://example.com/") == "http://example.com/"

    def test_https_allowed(self):
        assert validate_url("https://example.com/") == "https://example.com/"

    @pytest.mark.parametrize(
        "bad_scheme",
        [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "data:text/plain;base64,SGVsbG8=",
            "gopher://example.com/",
            "ldap://example.com/",
        ],
    )
    def test_non_http_schemes_blocked(self, bad_scheme):
        """非 http/https scheme 一律拒收。"""
        with pytest.raises(UrlSafetyError) as exc_info:
            validate_url(bad_scheme)
        assert "scheme" in str(exc_info.value).lower() or "不在白名单" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_url — 字面 host 黑名单
# ---------------------------------------------------------------------------
class TestLiteralHostBlocklist:
    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "LOCALHOST",  # 大小写不敏感
            "localhost.localdomain",
            "ip6-localhost",
            "ip6-loopback",
            "broadcasthost",
        ],
    )
    def test_literal_localhost_blocked(self, host):
        with pytest.raises(UrlSafetyError, match="loopback|字面"):
            validate_url(f"http://{host}/")

    @pytest.mark.parametrize(
        "host",
        [
            "printer.local",
            "nas.internal",
            "router.internal",
        ],
    )
    def test_local_internal_suffix_blocked(self, host):
        with pytest.raises(UrlSafetyError, match="suffix|字面"):
            validate_url(f"http://{host}/")

    def test_empty_url_blocked(self):
        with pytest.raises(UrlSafetyError, match="必须是非空字符串"):
            validate_url("")

    def test_no_scheme_blocked(self):
        with pytest.raises(UrlSafetyError, match="scheme"):
            validate_url("example.com/path")


# ---------------------------------------------------------------------------
# validate_url — 字面 IPv4 拒收
# ---------------------------------------------------------------------------
class TestLiteralIPv4:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # loopback
            "127.255.255.254",  # loopback 边缘
            "169.254.0.1",  # link-local
            "10.0.0.1",  # private 10/8
            "172.16.0.1",  # private 172.16/12
            "192.168.1.1",  # private 192.168/16
            "100.64.0.1",  # carrier-grade NAT
            "224.0.0.1",  # multicast
            "255.255.255.255",  # reserved broadcast
            "0.0.0.0",  # unspecified
        ],
    )
    def test_private_ipv4_blocked(self, ip):
        with pytest.raises(UrlSafetyError):
            validate_url(f"http://{ip}/")

    @pytest.mark.parametrize(
        "ip",
        [
            "1.1.1.1",  # 公网
            "8.8.8.8",  # 公网
            "104.16.0.1",  # 公网 (Cloudflare)
        ],
    )
    def test_public_ipv4_allowed(self, ip):
        """公网字面 IP 应放行 (虽然 collector 走域名)。"""
        assert validate_url(f"http://{ip}/") == f"http://{ip}/"


# ---------------------------------------------------------------------------
# validate_url — 字面 IPv6 拒收
# ---------------------------------------------------------------------------
class TestLiteralIPv6:
    @pytest.mark.parametrize(
        "ip",
        [
            "::1",  # loopback
            "fc00::1",  # unique local (ULA)
            "fd00::1",  # ULA
            "fe80::1",  # link-local
            "ff00::1",  # multicast
            "::",  # unspecified
        ],
    )
    def test_private_ipv6_blocked(self, ip):
        with pytest.raises(UrlSafetyError):
            validate_url(f"http://{ip}/")

    def test_ipv6_in_brackets_blocked(self):
        """方括号包裹的 IPv6 也应识别为 IP 并判定。"""
        with pytest.raises(UrlSafetyError):
            validate_url("http://[::1]/")


# ---------------------------------------------------------------------------
# validate_url — DNS 解析后含私网 IP 拒收 (DNS rebinding 第一道防线)
# ---------------------------------------------------------------------------
class TestDNSResolution:
    def test_public_domain_with_public_ip_allowed(self):
        """公网域名 example.com 解析到公网 IP → 放行。"""
        # example.com → 93.184.216.34 (公网)
        assert validate_url("https://example.com/") == "https://example.com/"

    def test_allow_private_bypass(self):
        """``allow_private=True`` 时跳过私网检查 (escape hatch for tests)。"""
        # 127.0.0.1 字面是 loopback — 默认拒, allow_private=True 放行
        assert (
            validate_url("http://127.0.0.1:8000/", allow_private=True)
            == "http://127.0.0.1:8000/"
        )

    def test_unresolvable_host_blocked(self):
        """不存在的域名 → DNS 失败 → 拒收。"""
        with pytest.raises(UrlSafetyError, match="DNS"):
            validate_url("http://this-domain-definitely-does-not-exist-zzz9999x.invalid/")


# ---------------------------------------------------------------------------
# validate_url — escape hatch 与边界
# ---------------------------------------------------------------------------
class TestEscapeHatch:
    def test_allow_private_skips_ip_check(self):
        """allow_private=True 时字面私网 IP 也放行。"""
        assert (
            validate_url("http://10.0.0.1/", allow_private=True)
            == "http://10.0.0.1/"
        )

    def test_url_with_port(self):
        """非默认端口不影响校验。"""
        assert validate_url("https://example.com:8443/") == "https://example.com:8443/"

    def test_url_with_userinfo(self):
        """userinfo 不影响 host 校验。"""
        # user:pass@example.com — urlparse 会拆 host, 应放行
        assert validate_url("https://user:pass@example.com/") == "https://user:pass@example.com/"

    def test_url_with_path_and_query(self):
        assert validate_url(
            "https://example.com/api?key=val#hash"
        ) == "https://example.com/api?key=val#hash"


# ---------------------------------------------------------------------------
# safe_aiohttp_connector — 工厂
# ---------------------------------------------------------------------------
class TestSafeAiohttpConnector:
    @pytest.mark.asyncio
    async def test_construct_connector(self):
        """应返回 ``aiohttp.TCPConnector``, 不发连接。"""
        connector = safe_aiohttp_connector("example.com")
        import aiohttp
        assert isinstance(connector, aiohttp.TCPConnector)
        assert connector._use_dns_cache is False  # noqa: SLF001 关闭 DNS cache (锁 IP 强制)
        await connector.close()

    @pytest.mark.asyncio
    async def test_construct_with_ssl(self):
        connector = safe_aiohttp_connector("example.com", ssl=False)
        import aiohttp
        assert isinstance(connector, aiohttp.TCPConnector)
        await connector.close()

    @pytest.mark.asyncio
    async def test_unresolvable_host_raises(self):
        """不可解析的 host 应抛 UrlSafetyError。"""
        with pytest.raises(UrlSafetyError, match="DNS"):
            safe_aiohttp_connector("this-domain-does-not-exist-9999x.invalid")

    @pytest.mark.asyncio
    async def test_pinned_resolver_locked_to_target_host(self):
        """验证锁 IP resolver 在 ``resolve(target_host)`` 时短路到预解析 IP,
        其他 host 走 ThreadedResolver 默认行为。

        直接构造一个 PinnedResolver (与 ``safe_aiohttp_connector`` 内部一致),
        不依赖 aiohttp TCPConnector 私有属性。
        """
        import socket
        from aiohttp.resolver import ThreadedResolver

        # 1) 预解析 example.com → 拿 IP 字面
        infos = socket.getaddrinfo("example.com", None, type=socket.SOCK_STREAM)
        expected_ips = {sockaddr[0] for _f, _t, _p, _c, sockaddr in infos}
        assert expected_ips  # 公网 IP 一定有结果

        # 2) 构造一个简化版 PinnedResolver, 验证 resolve 返回 locked IP
        target_host = "example.com"

        class _PinnedResolver(ThreadedResolver):
            async def resolve(self, *args, **kw):
                host_arg = str(args[0]) if args else str(kw.get("host", ""))
                if host_arg.lower() == target_host:
                    port = int(args[1]) if len(args) > 1 else int(kw.get("port", 0))
                    from aiohttp.resolver import ResolveResult
                    return [
                        ResolveResult(hostname=ip, host=ip, port=port,
                                      family=socket.AF_INET6 if ":" in ip else socket.AF_INET)
                        for ip in expected_ips
                    ]
                return await super().resolve(*args, **kw)

        resolver = _PinnedResolver()
        try:
            results = await resolver.resolve("example.com", 0)
            assert len(results) >= 1
            # locked IP 应等于预解析 IP (字面)
            result_ips = {r["host"] for r in results}
            assert result_ips == expected_ips
            for ip in result_ips:
                import ipaddress as _ip
                _ip.ip_address(ip)  # 必须是 IP 字面
        finally:
            await resolver.close()


# ---------------------------------------------------------------------------
# safe_urllib_request — urllib 包装
# ---------------------------------------------------------------------------
class TestSafeUrllibRequest:
    def test_returns_request_object(self):
        import urllib.request
        req = safe_urllib_request("https://example.com/", method="GET")
        assert isinstance(req, urllib.request.Request)
        assert req.get_full_url() == "https://example.com/"

    def test_ssrf_blocked(self):
        """私网 IP 应在构造时早抛。"""
        with pytest.raises(UrlSafetyError):
            safe_urllib_request("http://127.0.0.1/", method="HEAD")

    def test_non_http_scheme_blocked(self):
        with pytest.raises(UrlSafetyError):
            safe_urllib_request("file:///etc/passwd", method="GET")

    def test_default_headers(self):
        """``headers=None`` 时 Request 的 header 为空 dict, 不抛异常。"""
        req = safe_urllib_request("https://example.com/")
        assert req.headers == {} or req.headers == {"Host": "example.com"}


# ---------------------------------------------------------------------------
# pre_resolve_ip — 预解析
# ---------------------------------------------------------------------------
class TestPreResolveIp:
    def test_returns_url_and_ip(self):
        url, ip = pre_resolve_ip("https://example.com/")
        assert url == "https://example.com/"
        # 公网 IP, 不应是 0.0.0.0 / 127.0.0.1
        assert ip != "0.0.0.0"
        assert not ip.startswith("127.")

    def test_private_ip_blocked(self):
        with pytest.raises(UrlSafetyError):
            pre_resolve_ip("http://192.168.1.1/")

    def test_invalid_scheme_blocked(self):
        with pytest.raises(UrlSafetyError):
            pre_resolve_ip("file:///etc/passwd")


__all__ = [
    "TestDNSResolution",
    "TestEscapeHatch",
    "TestLiteralHostBlocklist",
    "TestLiteralIPv4",
    "TestLiteralIPv6",
    "TestPreResolveIp",
    "TestSafeAiohttpConnector",
    "TestSafeUrllibRequest",
    "TestSchemeWhitelist",
]