"""CloudBase OAuth 2.0 provider — Batch ⑧ D1 (前置修复 Batch ⑦ T5 假象).

设计原则:
- 配置源: HOTSPOT_OAUTH_CLIENT_ID / HOTSPOT_OAUTH_CLIENT_SECRET / HOTSPOT_OAUTH_REDIRECT_URI
  全部仅从环境变量读取; 源码 / 示例 / 测试 不写入可用的凭据字面量。
- URL 安全: 仅允许 https; 拒绝 localhost / 环回 / 私有 / 保留地址。
- User info allowlist: 解锁前需校验 user.email 在 settings.kv ``secrets.oauth_allowlist``。
- Mock: 测试用 ``MockOAuthProvider`` (conftest.py autouse), 不打真实接口。
"""
from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from backend.exceptions import InternalException
from backend.logging_config import logger


class OAuthVerificationError(Exception):
    """OAuth token 验证失败 (无效 / 过期 / 不在 allowlist)。"""


@dataclass
class OAuthToken:
    access_token: str
    expires_in: int


@dataclass
class OAuthUser:
    user_id: str
    email: str
    display_name: str
    roles: list[str]


def _validate_redirect_url(url: str) -> None:
    """校验 redirect URL: 必须 https, 不允许 localhost / 环回 / 私有 / 保留。"""
    if not url:
        raise InternalException("OAuth redirect URI 未配置")
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise InternalException(
            f"OAuth redirect URI 必须为 https, 当前={parsed.scheme}"
        )
    host = parsed.hostname or ""
    # 1. 显式黑名单
    if host.lower() in ("localhost", "0.0.0.0"):
        raise InternalException(f"OAuth redirect URI 不允许 {host}")
    # 2. 环回 / 私有 / 保留 IP 段
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
        ):
            raise InternalException(
                f"OAuth redirect URI 命中禁止 IP 段 (loopback/private/reserved): {host}"
            )
    except ValueError:
        # 不是 IP 字面量, 通过 DNS 解析检查
        try:
            resolved = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_reserved
                or ip.is_link_local
                or ip.is_multicast
            ):
                raise InternalException(
                    f"OAuth redirect URI host {host} 解析到禁止 IP {resolved}"
                )
        except socket.gaierror as e:
            raise InternalException(f"OAuth redirect URI host 无法解析: {host}") from e


class OAuthProvider:
    """OAuth provider 协议 (供 mock 实现覆盖)。"""

    def get_user_info(self, access_token: str) -> OAuthUser:  # pragma: no cover - 协议
        raise NotImplementedError


class CloudBaseOAuthProvider(OAuthProvider):
    """CloudBase OAuth 2.0 客户端实现。

    凭据: HOTSPOT_OAUTH_CLIENT_ID / HOTSPOT_OAUTH_CLIENT_SECRET / HOTSPOT_OAUTH_REDIRECT_URI
    端点: HOTSPOT_OAUTH_USERINFO_URL (默认 https://api.cloudbase.net/oauth2/userinfo)
    """

    def __init__(self) -> None:
        self.client_id = os.environ.get("HOTSPOT_OAUTH_CLIENT_ID", "")
        self.client_secret = os.environ.get("HOTSPOT_OAUTH_CLIENT_SECRET", "")
        self.redirect_uri = os.environ.get("HOTSPOT_OAUTH_REDIRECT_URI", "")
        self.userinfo_url = os.environ.get(
            "HOTSPOT_OAUTH_USERINFO_URL",
            "https://api.cloudbase.net/oauth2/userinfo",
        )
        self.token_url = os.environ.get(
            "HOTSPOT_OAUTH_TOKEN_URL",
            "https://api.cloudbase.net/oauth2/token",
        )
        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            raise InternalException(
                "CloudBase OAuth 配置缺失 (HOTSPOT_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI)"
            )
        _validate_redirect_url(self.redirect_uri)
        _validate_redirect_url(self.userinfo_url)
        _validate_redirect_url(self.token_url)

    def exchange_code(self, code: str) -> OAuthToken:
        """OAuth code → access_token."""
        if not code or len(code) < 8:
            raise OAuthVerificationError("OAuth code 太短")
        # P1.8: with httpx.Client 显式管理连接, 避免 httpx.post 模块函数
        # 每次创建内部 Client 不复用 (连接池泄露)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": self.redirect_uri,
                    },
                )
        except httpx.HTTPError as e:
            logger.warning("OAuth token exchange failed: %s", e)
            raise OAuthVerificationError(f"OAuth token 交换失败: {e}") from e
        if resp.status_code != 200:
            raise OAuthVerificationError(
                f"OAuth token 交换返回 {resp.status_code}"
            )
        body = resp.json()
        return OAuthToken(
            access_token=str(body.get("access_token", "")),
            expires_in=int(body.get("expires_in", 3600)),
        )

    def get_user_info(self, access_token: str) -> OAuthUser:
        """OAuth access_token → user info。"""
        if not access_token or len(access_token) < 10:
            raise OAuthVerificationError("OAuth access_token 太短")
        # P1.8: 同 exchange_code, 显式 Client 上下文管理连接池
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as e:
            logger.warning("OAuth userinfo failed: %s", e)
            raise OAuthVerificationError(f"OAuth userinfo 失败: {e}") from e
        if resp.status_code != 200:
            raise OAuthVerificationError(
                f"OAuth userinfo 返回 {resp.status_code}"
            )
        body = resp.json()
        return OAuthUser(
            user_id=str(body.get("sub", body.get("user_id", ""))),
            email=str(body.get("email", "")),
            display_name=str(body.get("name", body.get("display_name", ""))),
            roles=list(body.get("roles", [])),
        )


class MockOAuthProvider(OAuthProvider):
    """测试用 mock provider (conftest.py autouse 注入)。

    行为: token 以 ``mock:<user_id>:<email>`` 解析, 不发任何网络请求。
    """

    def __init__(self, *, allowlist: list[str] | None = None) -> None:
        self._allowlist = allowlist or []

    def get_user_info(self, access_token: str) -> OAuthUser:
        if not access_token.startswith("mock:"):
            raise OAuthVerificationError("mock token 必须以 'mock:' 开头")
        parts = access_token.split(":", 3)
        if len(parts) < 3:
            raise OAuthVerificationError("mock token 格式: mock:<user_id>:<email>")
        user_id = parts[1]
        email = parts[2]
        return OAuthUser(
            user_id=user_id,
            email=email,
            display_name=f"Mock {user_id}",
            roles=["user"],
        )


_provider_singleton: OAuthProvider | None = None


def get_oauth_provider() -> OAuthProvider:
    """D1: provider 单例工厂 — 优先 mock (测试), 否则 CloudBase 真身。

    切换源:
    - ``HOTSPOT_OAUTH_PROVIDER=mock`` → MockOAuthProvider (conftest autouse)
    - 默认 / ``cloudbase`` → CloudBaseOAuthProvider
    """
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton
    flavour = os.environ.get("HOTSPOT_OAUTH_PROVIDER", "cloudbase").strip().lower()
    if flavour == "mock":
        _provider_singleton = MockOAuthProvider()
    else:
        _provider_singleton = CloudBaseOAuthProvider()
    return _provider_singleton


def reset_oauth_provider() -> None:
    """测试用: 重置单例, 让下一次 ``get_oauth_provider()`` 重建。"""
    global _provider_singleton
    _provider_singleton = None


__all__ = [
    "CloudBaseOAuthProvider",
    "MockOAuthProvider",
    "OAuthProvider",
    "OAuthToken",
    "OAuthUser",
    "OAuthVerificationError",
    "get_oauth_provider",
    "reset_oauth_provider",
]
