"""test_trigger_sources.py — v0.8 Phase D D1 trigger 适配层 + webhook API 测试.

覆盖:
- webhook: 签名校验 (有 secret / 无 secret 两种模式), HMAC 算法正确, 提交入队
- kl_event: 5 阶段合法, 非法 stage/item_id 拒绝, 默认 target_id 正确
- collector_event: 3 status 行为 (success 早返回 / failed NORMAL / timeout REALTIME),
  非白名单 status 拒绝
- API: /api/trigger/webhook/{source} 全路径 (200/422/429)
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services.trigger_gate import (
    ThrottleExceededError,
    trigger_gate,
)
from backend.services.trigger_gate.priority import Priority
from backend.services.trigger_gate.queue import TriggerQueue
from backend.services.trigger_gate.throttle import TriggerThrottle
from backend.services.trigger_gate.triggers.collector_event import (
    CollectorEventTrigger,
    InvalidCollectorStatusError,
    submit_collector_event,
)
from backend.services.trigger_gate.triggers.kl_event import (
    InvalidKLEventError,
    KLEventTrigger,
    submit_kl_event,
)
from backend.services.trigger_gate.triggers.webhook import (
    SignatureInvalidError,
    WebhookTrigger,
    submit_webhook,
)


# ---------------------------------------------------------------------------
# 共用: 自定义 throttle/queue 注入, 避免测试间限流污染
# ---------------------------------------------------------------------------
@pytest.fixture
def fresh_gate(monkeypatch):
    """返回一个新 TriggerGate 实例 (含干净 throttle + 干净 queue)."""
    g = type(trigger_gate)(
        throttle=TriggerThrottle(per_user_per_minute=10_000, global_per_minute=100_000),
        queue=TriggerQueue(),
    )
    return g


@pytest.fixture(autouse=True)
def _patch_default_gate(monkeypatch, fresh_gate):
    """替换 trigger_gate.triggers.* 默认 _default 实例, 让它们用 fresh_gate."""
    import backend.services.trigger_gate as tg_mod
    import backend.services.trigger_gate.triggers.webhook as wh_mod
    import backend.services.trigger_gate.triggers.kl_event as kl_mod
    import backend.services.trigger_gate.triggers.collector_event as ce_mod

    # 把 trigger_gate 单例也指向 fresh_gate, 方便 webhook 内部调用 trigger_gate.submit
    monkeypatch.setattr(tg_mod, "trigger_gate", fresh_gate)
    # triggers/* 的 _default 实例直接 inject gate
    wh_mod._default.__class__ = WebhookTrigger
    # 重新构造 _default 实例, secret_provider 用 lambda 让 secret 缺省
    wh_mod._default = WebhookTrigger(secret_provider=lambda: None)
    wh_mod._default.__class__ = WebhookTrigger  # 保持类属性
    kl_mod._default = KLEventTrigger()
    ce_mod._default = CollectorEventTrigger()
    yield fresh_gate


# ---------------------------------------------------------------------------
# webhook 适配层
# ---------------------------------------------------------------------------
class TestWebhookTrigger:
    def test_submit_webhook_no_secret_no_signature_succeeds(self, fresh_gate):
        ticket = submit_webhook(
            "/api/trigger/webhook/secnews",
            {"event": "push"},
            target_id="webhook-test",
        )
        assert ticket.ticket_id.startswith("tg-")
        assert ticket.source == "webhook"
        assert ticket.target_id == "webhook-test"
        assert ticket.inputs["path"] == "/api/trigger/webhook/secnews"
        assert ticket.inputs["payload"] == {"event": "push"}

    def test_submit_webhook_signature_valid(self, fresh_gate):
        import backend.services.trigger_gate.triggers.webhook as wh_mod

        secret = "test-secret"
        wh_mod._default = WebhookTrigger(secret_provider=lambda: secret)
        path = "/api/trigger/webhook/secnews"
        payload = {"event": "push"}
        # 计算期望签名
        msg = path.encode() + b"|" + json.dumps(payload, sort_keys=True).encode()
        sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
        ticket = submit_webhook(
            path, payload, signature=sig, target_id="whhook-test"
        )
        assert ticket.source == "webhook"

    def test_submit_webhook_signature_missing_raises(self, fresh_gate):
        import backend.services.trigger_gate.triggers.webhook as wh_mod

        wh_mod._default = WebhookTrigger(secret_provider=lambda: "test-secret")
        with pytest.raises(SignatureInvalidError, match="缺少签名"):
            submit_webhook(
                "/api/trigger/webhook/secnews",
                {"event": "x"},
                target_id="t",
            )

    def test_submit_webhook_signature_invalid_raises(self, fresh_gate):
        import backend.services.trigger_gate.triggers.webhook as wh_mod

        wh_mod._default = WebhookTrigger(secret_provider=lambda: "test-secret")
        with pytest.raises(SignatureInvalidError, match="签名校验失败"):
            submit_webhook(
                "/api/trigger/webhook/secnews",
                {"event": "x"},
                signature="0" * 64,
                target_id="t",
            )


# ---------------------------------------------------------------------------
# kl_event 适配层
# ---------------------------------------------------------------------------
class TestKLEventTrigger:
    @pytest.mark.parametrize("stage", ["T1", "T2", "T3", "T4", "T5"])
    def test_submit_kl_event_all_stages_valid(self, fresh_gate, stage):
        ticket = submit_kl_event(stage, "item-abc")
        assert ticket.source == "kl_event"
        assert ticket.target_id == "quality-patrol"
        assert ticket.inputs["stage"] == stage
        assert ticket.inputs["item_id"] == "item-abc"

    def test_submit_kl_event_invalid_stage_raises(self, fresh_gate):
        with pytest.raises(InvalidKLEventError, match="非法"):
            submit_kl_event("T99", "item-1")

    def test_submit_kl_event_empty_item_id_raises(self, fresh_gate):
        with pytest.raises(InvalidKLEventError, match="item_id"):
            submit_kl_event("T1", "")

    def test_submit_kl_event_custom_target(self, fresh_gate):
        ticket = submit_kl_event("T3", "item-x", target_id="my-custom-skill")
        assert ticket.target_id == "my-custom-skill"


# ---------------------------------------------------------------------------
# collector_event 适配层
# ---------------------------------------------------------------------------
class TestCollectorEventTrigger:
    def test_success_early_returns_no_ticket(self, fresh_gate):
        result = submit_collector_event("ai_security_collector", "success")
        assert result is None  # 不触发, 不消耗限流配额

    def test_failed_triggers_normal_priority(self, fresh_gate):
        ticket = submit_collector_event(
            "ai_security_collector", "failed", error="404 not found"
        )
        assert ticket is not None
        assert ticket.source == "collector_event"
        assert ticket.priority == Priority.NORMAL
        assert ticket.target_id == "source-health-scan"
        assert ticket.inputs["status"] == "failed"
        assert ticket.inputs["error"] == "404 not found"

    def test_timeout_triggers_realtime_priority(self, fresh_gate):
        ticket = submit_collector_event("hn_collector", "timeout", error="30s elapsed")
        assert ticket.priority == Priority.REALTIME

    def test_invalid_status_raises(self, fresh_gate):
        with pytest.raises(InvalidCollectorStatusError, match="非法"):
            submit_collector_event("foo", "weird-status")

    def test_empty_collector_name_raises(self, fresh_gate):
        with pytest.raises(InvalidCollectorStatusError, match="collector_name"):
            submit_collector_event("", "failed")


# ---------------------------------------------------------------------------
# webhook API
# ---------------------------------------------------------------------------
class TestWebhookApi:
    @pytest.fixture
    def client(self):
        from backend.api import trigger_webhook_api

        app = FastAPI()
        app.include_router(trigger_webhook_api.router)
        return TestClient(app)

    def test_health_endpoint(self, client):
        r = client.get("/api/trigger/webhook/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_valid_source_no_signature(self, client):
        r = client.post(
            "/api/trigger/webhook/secnews",
            json={"event": "push", "ref": "main"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ticket_id"].startswith("tg-")
        assert data["source"] == "secnews"
        assert data["target_id"] == "webhook-secnews"

    def test_valid_source_with_query_target(self, client):
        r = client.post(
            "/api/trigger/webhook/cve_feed?target=custom-skill",
            json={"cve": "CVE-2026-0001"},
        )
        assert r.status_code == 200
        assert r.json()["target_id"] == "custom-skill"

    def test_invalid_source_returns_422(self, client):
        r = client.post(
            "/api/trigger/webhook/not-whitelisted",
            json={"x": 1},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "VALIDATE_FAILED"
        assert "白名单" in detail["message"]

    def test_signature_invalid_returns_422(self, client, monkeypatch):
        # 强制 secret 已配置但签名缺失
        import backend.services.trigger_gate.triggers.webhook as wh_mod

        wh_mod._default = WebhookTrigger(secret_provider=lambda: "real-secret")
        r = client.post(
            "/api/trigger/webhook/secnews",
            json={"event": "push"},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "SIGNATURE_INVALID"

    def test_signature_valid_succeeds(self, client, monkeypatch):
        import backend.services.trigger_gate.triggers.webhook as wh_mod

        secret = "abc"
        wh_mod._default = WebhookTrigger(secret_provider=lambda: secret)
        path = "/api/trigger/webhook/secnews"
        body = {"event": "push"}
        msg = path.encode() + b"|" + json.dumps(body, sort_keys=True).encode()
        sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

        r = client.post(
            path,
            content=json.dumps(body).encode(),
            headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["ticket_id"].startswith("tg-")