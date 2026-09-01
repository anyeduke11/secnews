"""D2 (Batch ⑧) — 告警通道扩展测试.

覆盖:
- 5 通道类型注册 (webhook / email / slack / feishu / dingtalk)
- URL 校验 (https 强制 + 拒绝 localhost / 私有 / 链路本地)
- WebhookChannel (httpx mock)
- Feishu / Dingtalk HMAC 签名格式
- Dispatcher: settings 配置 → channel 实例 → 并发投递 → 写 alert_deliveries
- 失败隔离: 一个 channel 失败不影响其他
"""
from __future__ import annotations

import hashlib
import hmac
from base64 import b64encode
from collections.abc import Iterator

import pytest

# ============ Fixtures ============


@pytest.fixture()
def client(temp_db, monkeypatch) -> Iterator:
    """FastAPI TestClient (含 observability router)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.observability_router import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)

    from backend.repository import db as _db
    try:
        _db.close_db()
    except Exception:
        pass


# ============ Registry ============


def test_supported_channel_types():
    from backend.services.alert_channels import registered_channel_types

    types = registered_channel_types()
    assert set(types) == {"webhook", "email", "slack", "feishu", "dingtalk"}


def test_build_channel_webhook():
    from backend.services.alert_channels import build_channel

    ch = build_channel("webhook", url="https://example.com/hook")
    assert ch.channel_type == "webhook"
    assert ch.is_configured()


def test_build_channel_unknown_raises():
    from backend.services.alert_channels import build_channel

    with pytest.raises(ValueError):
        build_channel("telegram", url="https://x.com")


# ============ URL 校验 ============


def test_webhook_rejects_http():
    from backend.services.alert_channels import WebhookChannel

    with pytest.raises(ValueError, match="必须 https"):
        WebhookChannel(url="http://example.com/hook")


def test_webhook_rejects_localhost():
    from backend.services.alert_channels import WebhookChannel

    with pytest.raises(ValueError):
        WebhookChannel(url="https://localhost:8080/hook")


def test_webhook_rejects_private_10x():
    from backend.services.alert_channels import WebhookChannel

    with pytest.raises(ValueError):
        WebhookChannel(url="https://10.0.0.1/hook")


def test_webhook_rejects_link_local():
    from backend.services.alert_channels import WebhookChannel

    with pytest.raises(ValueError):
        WebhookChannel(url="https://169.254.169.254/latest")


# ============ Channel is_configured (env-driven) ============


def test_email_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("HOTSPOT_ALERT_SMTP_HOST", raising=False)
    monkeypatch.delenv("HOTSPOT_ALERT_SMTP_SENDER", raising=False)
    monkeypatch.delenv("HOTSPOT_ALERT_SMTP_RECIPIENTS", raising=False)
    from backend.services.alert_channels import EmailChannel

    ch = EmailChannel()
    assert ch.is_configured() is False


def test_email_configured_with_env(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ALERT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("HOTSPOT_ALERT_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HOTSPOT_ALERT_SMTP_RECIPIENTS", "a@example.com,b@example.com")
    from backend.services.alert_channels import EmailChannel

    ch = EmailChannel()
    assert ch.is_configured() is True


def test_slack_configured_with_env(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T0/B0/X")
    from backend.services.alert_channels import SlackChannel

    ch = SlackChannel()
    assert ch.is_configured() is True


def test_slack_rejects_http(monkeypatch):
    """Slack webhook 必 https (slack 不服务不签 localhost)."""
    monkeypatch.setenv("HOTSPOT_ALERT_SLACK_WEBHOOK_URL", "http://hooks.slack.com/services/X")
    from backend.services.alert_channels import SlackChannel

    with pytest.raises(ValueError):
        SlackChannel()


def test_feishu_configured_with_env(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ALERT_FEISHU_WEBHOOK_URL", "https://open.feishu.cn/hook/x")
    from backend.services.alert_channels import FeishuChannel

    ch = FeishuChannel()
    assert ch.is_configured() is True


def test_dingtalk_configured_with_env(monkeypatch):
    monkeypatch.setenv("HOTSPOT_ALERT_DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=x")
    from backend.services.alert_channels import DingtalkChannel

    ch = DingtalkChannel()
    assert ch.is_configured() is True


# ============ HMAC 签名 ============


def test_feishu_sign_format():
    """飞书签名: hmac-sha256(key=secret, msg=f"{ts}\n{secret}") → base64."""
    import os
    secret = "test-secret-abc"
    os.environ["HOTSPOT_ALERT_FEISHU_WEBHOOK_URL"] = "https://x"
    os.environ["HOTSPOT_ALERT_FEISHU_SECRET"] = secret
    from backend.services.alert_channels import FeishuChannel
    ch = FeishuChannel()
    ts = "1700000000"
    expected = b64encode(
        hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    ).decode()
    got = ch._sign(ts)
    assert got == expected


def test_dingtalk_sign_format():
    """钉钉签名: hmac-sha256 + timestamp 毫秒 + url 编码."""
    import os
    secret = "ding-secret-123"
    os.environ["HOTSPOT_ALERT_DINGTALK_WEBHOOK_URL"] = "https://oapi.dingtalk.com/x"
    os.environ["HOTSPOT_ALERT_DINGTALK_SECRET"] = secret
    from backend.services.alert_channels import DingtalkChannel
    ch = DingtalkChannel()
    ts, sign = ch._sign()
    # ts 是 13 位毫秒
    assert len(ts) == 13
    assert ts.isdigit()
    # sign 是 url-encoded base64
    from urllib.parse import unquote
    decoded = unquote(sign)
    import base64
    raw = base64.b64decode(decoded)
    expected = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    assert raw == expected


# ============ Dispatcher 集成 ============


@pytest.mark.asyncio
async def test_dispatcher_sends_to_webhook(monkeypatch, temp_db):
    """WebhookChannel 投递成功 → alert_deliveries 写 ok=1."""
    import httpx

    # settings.kv 配 webhook
    from backend.repository.settings_repo import SettingsRepository
    from backend.services.alert_channels import AlertPayload
    from backend.services.alert_dispatcher import dispatch
    SettingsRepository().set("observability.channels", [
        {"type": "webhook", "config": {"url": "https://example.com/hook"}},
    ])

    sent_to_httpx: list[dict] = []

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        sent_to_httpx.append({"url": url, "json": json})
        from httpx import Request, Response
        req = Request("POST", url)
        return Response(200, content=b"ok", request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    payload = AlertPayload(
        metric="api.error_rate_pct",
        level="warn",
        value=10.0,
        threshold=5.0,
        window_minutes=60,
        detail={},
        fired_at="2026-09-01T00:00:00Z",
    )
    res = await dispatch(payload, alert_id=42)
    assert res["dispatched"] == 1
    assert res["channels"]["webhook"]["ok"] is True
    assert len(sent_to_httpx) == 1
    assert sent_to_httpx[0]["url"] == "https://example.com/hook"

    # alert_deliveries 写留痕
    from backend.repository.db import get_connection
    rows = get_connection().execute(
        "SELECT channel, ok, alert_id FROM alert_deliveries"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["channel"] == "webhook"
    assert rows[0]["ok"] == 1
    assert rows[0]["alert_id"] == 42


@pytest.mark.asyncio
async def test_dispatcher_isolates_channel_failures(monkeypatch, temp_db):
    """一个 channel 失败不影响其他 channel 投递."""
    import httpx

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.alert_channels import AlertPayload
    from backend.services.alert_dispatcher import dispatch
    SettingsRepository().set("observability.channels", [
        {"type": "webhook", "config": {"url": "https://will.fail/hook"}},
        {"type": "webhook", "config": {"url": "https://ok.example.com/hook"}},
    ])

    async def fake_post(self, url, json=None, **kwargs):
        from httpx import Request, Response
        if "will.fail" in url:
            raise RuntimeError("simulated network error")
        req = Request("POST", url)
        return Response(200, content=b"ok", request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    payload = AlertPayload(
        metric="x", level="warn", value=1, threshold=0,
        window_minutes=60, detail={}, fired_at="2026-09-01T00:00:00Z",
    )
    res = await dispatch(payload, alert_id=99)
    # 两条 channel 都尝试了; 一条失败一条成功
    assert res["dispatched"] == 2
    # summary dict 按 channel_type 聚合, 两条都是 "webhook", 最后一条胜出 (成功)
    # 但 alert_deliveries 应有 2 行 (一条 ok=0, 一条 ok=1) — 这是真正的隔离证据
    from backend.repository.db import get_connection
    rows = get_connection().execute(
        "SELECT channel, ok FROM alert_deliveries ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    ok_values = sorted([r["ok"] for r in rows])
    assert ok_values == [0, 1]  # 一失败一成功, 隔离 OK


@pytest.mark.asyncio
async def test_dispatcher_skips_unconfigured(temp_db):
    """未配置 (env 缺失) 的 channel 被跳过."""
    from backend.repository.settings_repo import SettingsRepository
    from backend.services.alert_channels import AlertPayload
    from backend.services.alert_dispatcher import dispatch
    SettingsRepository().set("observability.channels", [
        {"type": "email"},  # 无 SMTP env → is_configured=False
        {"type": "slack"},  # 无 SLACK_WEBHOOK_URL env
    ])

    payload = AlertPayload(
        metric="x", level="warn", value=1, threshold=0,
        window_minutes=60, detail={}, fired_at="2026-09-01T00:00:00Z",
    )
    res = await dispatch(payload, alert_id=1)
    assert res["dispatched"] == 0  # 都没配, 没投递


# ============ API endpoints ============


def test_get_channels_lists_supported(client):
    r = client.get("/api/observability/channels")
    assert r.status_code == 200
    body = r.json()
    assert set(body["supported_types"]) == {"webhook", "email", "slack", "feishu", "dingtalk"}


def test_put_channels_validates(client):
    r = client.put("/api/observability/channels", json={
        "channels": [{"type": "telegram", "config": {}}]
    })
    assert r.status_code == 400


def test_put_channels_roundtrip(client):
    r = client.put("/api/observability/channels", json={
        "channels": [{"type": "webhook", "config": {"url": "https://x.example.com/h"}}]
    })
    assert r.status_code == 200

    r2 = client.get("/api/observability/channels")
    assert r2.status_code == 200
    chs = r2.json()["channels"]
    assert len(chs) == 1
    assert chs[0]["type"] == "webhook"


def test_deliveries_empty(client):
    r = client.get("/api/observability/deliveries")
    assert r.status_code == 200
    assert r.json()["deliveries"] == []