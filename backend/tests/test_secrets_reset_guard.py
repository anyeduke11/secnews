"""POST /api/secrets/reset 来源门禁单测 (C2: 不可逆销毁不得被局域网单点触发)。"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.secrets import _require_local_or_admin


class _Client:
    def __init__(self, host: str | None):
        self.host = host


class _Req:
    """最小 Request 替身: 门禁只读 client.host 与一个请求头。"""

    def __init__(self, host: str | None, headers: dict | None = None):
        self.client = _Client(host) if host is not None else None
        self.headers = headers or {}


def test_loopback_and_inprocess_peers_pass():
    for host in ("127.0.0.1", "::1", "testclient", ""):
        _require_local_or_admin(_Req(host))  # 不应抛
    _require_local_or_admin(_Req(None))  # 无 client 信息 (ASGI 进程内)


def test_remote_peer_without_token_is_refused(monkeypatch):
    monkeypatch.delenv("HOTSPOT_ADMIN_TOKEN", raising=False)
    with pytest.raises(HTTPException) as ei:
        _require_local_or_admin(_Req("192.168.1.50"))
    assert ei.value.status_code == 403


def test_remote_peer_with_correct_token_passes(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ADMIN_TOKEN", "s3cret-token")
    _require_local_or_admin(
        _Req("192.168.1.50", {"X-Admin-Token": "s3cret-token"})
    )


def test_remote_peer_with_wrong_or_missing_header_refused(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ADMIN_TOKEN", "s3cret-token")
    for headers in ({}, {"X-Admin-Token": "wrong"}, {"X-Admin-Token": ""}):
        with pytest.raises(HTTPException) as ei:
            _require_local_or_admin(_Req("10.0.0.7", headers))
        assert ei.value.status_code == 403


def test_empty_configured_token_does_not_bypass(monkeypatch):
    """未配置 HOTSPOT_ADMIN_TOKEN 时, 空 token 不得让远程来源通过。"""
    monkeypatch.setenv("HOTSPOT_ADMIN_TOKEN", "   ")
    with pytest.raises(HTTPException):
        _require_local_or_admin(_Req("10.0.0.7", {"X-Admin-Token": ""}))
