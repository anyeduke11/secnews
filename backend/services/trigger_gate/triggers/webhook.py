"""trigger_gate.triggers.webhook — HTTP webhook 触发源适配 (D1).

契约:
- :func:`submit_webhook(path, payload, *, signature, target_type, target_id,
  user_id)` 内部调 ``trigger_gate.submit(source="webhook", ...)``
- 签名: SHA-256 HMAC over ``path|payload_bytes``; secret 从 settings.kv 取
  (``webhook.secret``), 缺 secret 时跳过签名校验 (fail-open 仅 v0.8 dev 期)
- 未知 path → ValueError (R12 fail loud, 不静默路由到 default skill)

signature 校验逻辑 (R7):
- 当 settings.kv 中存在 ``webhook.secret`` 时, 缺签名 / 签名错一律拒
  (R7 fail-closed); 当 secret 未配置时, 校验放行 (R7 fail-open dev 期)
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from backend.logging_config import logger
from backend.services.trigger_gate import trigger_gate

__all__ = ["SignatureInvalidError", "WebhookTrigger", "submit_webhook"]


class SignatureInvalidError(ValueError):
    """webhook 签名缺失或校验失败 (R7)."""


class WebhookTrigger:
    """HTTP webhook 触发器 — 适配层.

    - 测试时构造空 ``secret_provider`` 注入; 生产默认 settings.kv 读
    - 公开 :meth:`submit` 调底层 ``trigger_gate.submit(source="webhook", ...)``
    """

    def __init__(self, secret_provider: Any | None = None) -> None:
        # 默认从 settings.kv 读 (Repository 模式, 见 backend/services/settings_kv.py);
        # 测试可注入 lambda / 字典 / Repository 实现
        self._secret_provider = secret_provider

    def _get_secret(self) -> str | None:
        if self._secret_provider is None:
            try:
                from backend.services.settings_kv import SettingsRepository

                return SettingsRepository().get("webhook.secret")
            except Exception:  # noqa: BLE001
                return None
        if callable(self._secret_provider):
            return self._secret_provider()
        if isinstance(self._secret_provider, dict):
            return self._secret_provider.get("webhook.secret")
        # 假定 Repository 实例
        return self._secret_provider.get("webhook.secret")

    @staticmethod
    def _expected_signature(secret: str, path: str, payload: bytes) -> str:
        """计算期望签名: hex(SHA-256 HMAC(secret, path|payload))."""
        msg = path.encode("utf-8") + b"|" + payload
        return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    def submit(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        signature: str | None = None,
        target_type: str = "skill",
        target_id: str = "webhook-default",
        user_id: str | None = None,
        priority: int = 1,
    ) -> Any:
        """提交 webhook 触发.

        Args:
            path: webhook 路径 (e.g. ``/api/trigger/webhook/secnews``)
            payload: 请求体 dict
            signature: HMAC-SHA256 hex 签名 (header ``X-Webhook-Signature``)
            target_type: ``skill`` / ``playbook``
            target_id: 目标 ID (默认 ``webhook-default``)
            user_id: 触发用户 (限流按 user 配额)
            priority: 0=REALTIME / 1=NORMAL / 2=BATCH

        Returns:
            ``TriggerTicket`` (pending)

        Raises:
            SignatureInvalidError: secret 已配置但签名缺失/错误
            ValueError: target_type 非法
        """
        secret = self._get_secret()
        payload_bytes = _payload_to_bytes(payload)
        if secret:
            if not signature:
                raise SignatureInvalidError(
                    f"webhook {path} 缺少签名 (X-Webhook-Signature), secret 已配置 (R7 fail-closed)"
                )
            expected = self._expected_signature(secret, path, payload_bytes)
            if not hmac.compare_digest(expected, signature):
                raise SignatureInvalidError(
                    f"webhook {path} 签名校验失败 (R7 fail-closed)"
                )

        inputs = {"path": path, "payload": payload}
        ticket = trigger_gate.submit(
            target_type=target_type,
            target_id=target_id,
            inputs=inputs,
            priority=priority,
            source="webhook",
            user_id=user_id,
        )
        logger.info(
            "webhook trigger submitted",
            extra={
                "trace_id": "",
                "ticket_id": ticket.ticket_id,
                "path": path,
                "target_id": target_id,
                "user_id": user_id,
            },
        )
        return ticket


def _payload_to_bytes(payload: Any) -> bytes:
    """payload → bytes (用于签名); dict 走紧凑 JSON."""
    import json

    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


# 模块级便捷函数 — 默认走 WebhookTrigger() 单例
_default = WebhookTrigger()


def submit_webhook(
    path: str,
    payload: dict[str, Any],
    *,
    signature: str | None = None,
    target_type: str = "skill",
    target_id: str = "webhook-default",
    user_id: str | None = None,
    priority: int = 1,
) -> Any:
    """便捷函数 — 等价 :meth:`WebhookTrigger().submit(...)`."""
    return _default.submit(
        path,
        payload,
        signature=signature,
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        priority=priority,
    )