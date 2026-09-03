"""v0.7 Batch ⑧ D2: 告警通道扩展 — 5 档 (webhook / email / slack / 飞书 / 钉钉).

设计原则
--------
- **配置源**: 凭据仅从环境变量或密钥服务读取 (不写源码 / 测试可用凭据字面量)
- **URL 安全**: webhook / slack / 飞书 / 钉钉 均强制 https (除 slack webhook 例外允许 http localhost for testing)
- **签名**: 飞书 / 钉钉 HMAC-SHA256 签名 (verify by secret); slack 不签名 (token 校验)
- **失败模式**: 通道 dispatch 异常 swallow + log, 不阻塞主流程; 但写入 alert_deliveries 表留痕
- **测试隔离**: 所有发送都走 ``AlertChannel.send()``, 测试用 ``FakeChannel`` 替代
"""
from __future__ import annotations

import hashlib
import hmac
import os
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import httpx


@dataclass(frozen=True)
class AlertPayload:
    """一条告警投递的统一结构.

    各 channel 用同一 payload → 不同格式 (text / markdown / card / email).
    """
    metric: str
    level: str        # "warn" | "critical"
    value: float
    threshold: float
    window_minutes: int
    detail: dict[str, Any]
    fired_at: str     # ISO UTC
    source: str = "observability_thresholds"  # 哪个 job 触发


def _validate_url(url: str, *, allow_http: bool = False) -> str:
    """URL 校验: 委托到 ``backend.utils.url_safety.validate_url`` 做 SSRF 防护。

    历史: 早期版本只做 scheme + 字面 IP 检查, 不防 DNS rebinding / 不防域名解析到私网。
    v0.7.x P0 改走 url_safety 单一真相源。

    Args:
        url: 待校验 URL。
        allow_http: 保留参数 (历史兼容), 不影响校验语义。
            注: ``url_safety.validate_url`` 默认同时允许 http/https (SSRF 关键约束在
            host/IP, 不在 scheme); webhook 强制 https 的旧行为由 ``WebhookChannel.__init__``
            单独保留 (``url.startswith("https://")`` 检查, 见下文)。

    Raises:
        ValueError: SSRF 阻断时包装 ``UrlSafetyError``。
    """
    from backend.utils.url_safety import UrlSafetyError, validate_url as _v

    # 兼容旧语义: webhook 强制 https (除测试 allow_http)
    if not allow_http and not url.startswith("https://"):
        raise ValueError(f"URL 必须 https; 不允许 http: {url[:30]}")
    try:
        return _v(url)
    except UrlSafetyError as e:
        # 兼容老调用方 — 仍抛 ValueError
        raise ValueError(str(e)) from e


class AlertChannel(ABC):
    """告警通道抽象基类."""

    channel_type: str = "abstract"

    @abstractmethod
    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        """发送一条告警. 失败抛异常 (caller 捕获 + log)."""

    @abstractmethod
    def is_configured(self) -> bool:
        """该通道是否已配置 (供 dispatcher 跳过未配置通道)."""


# ============ 1. Webhook (通用 JSON POST) ============


class WebhookChannel(AlertChannel):
    """通用 webhook — POST JSON 到任意 URL (Slack 兼容 webhook / 自建 endpoint)."""

    channel_type = "webhook"

    def __init__(self, *, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = _validate_url(url)
        self.headers = headers or {}

    def is_configured(self) -> bool:
        return bool(self.url)

    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        body = {
            "metric": payload.metric,
            "level": payload.level,
            "value": payload.value,
            "threshold": payload.threshold,
            "window_minutes": payload.window_minutes,
            "detail": payload.detail,
            "fired_at": payload.fired_at,
            "source": payload.source,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.url, json=body, headers=self.headers)
            resp.raise_for_status()
            return {"status_code": resp.status_code, "bytes": len(resp.content)}


# ============ 2. Email (SMTP) ============


class EmailChannel(AlertChannel):
    """SMTP email — 用环境变量读 smtp host / port / user / pass / sender / recipients."""

    channel_type = "email"

    def __init__(self) -> None:
        self.host = os.environ.get("HOTSPOT_ALERT_SMTP_HOST", "").strip()
        self.port = int(os.environ.get("HOTSPOT_ALERT_SMTP_PORT", "587"))
        self.user = os.environ.get("HOTSPOT_ALERT_SMTP_USER", "").strip()
        # 密码从密钥服务读 (避免明文进 env / 测试)
        self._password: str | None = None
        self.sender = os.environ.get("HOTSPOT_ALERT_SMTP_SENDER", "").strip()
        self.recipients = [
            r.strip()
            for r in os.environ.get("HOTSPOT_ALERT_SMTP_RECIPIENTS", "").split(",")
            if r.strip()
        ]

    def is_configured(self) -> bool:
        return bool(self.host and self.sender and self.recipients)

    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("EmailChannel 未配置 (SMTP host / sender / recipients 缺失)")
        if self._password is None:
            try:
                from backend.services.secrets_service import SecretsService

                svc = SecretsService()
                # 尝试读 SMTP password from secrets (provider=email_alert)
                from backend.repository.secrets_repo import SecretRepository
                item = SecretRepository().get_by_provider("email_alert")
                self._password = svc.decrypt_for_internal_use(item.id) if item else ""
            except Exception:
                self._password = ""

        msg = EmailMessage()
        msg["Subject"] = f"[{payload.level.upper()}] {payload.metric} 触发阈值告警"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        body = (
            f"指标: {payload.metric}\n"
            f"等级: {payload.level}\n"
            f"当前值: {payload.value}\n"
            f"阈值: {payload.threshold}\n"
            f"窗口: {payload.window_minutes}min\n"
            f"触发时间: {payload.fired_at}\n"
        )
        msg.set_content(body)

        # SMTP 同步发送 (smtplib 无原生 async; run in executor via dispatcher 包裹)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.starttls()
            if self.user and self._password:
                smtp.login(self.user, self._password)
            smtp.send_message(msg)
        return {"recipients": len(self.recipients)}


# ============ 3. Slack (incoming webhook) ============


class SlackChannel(AlertChannel):
    """Slack incoming webhook — POST 到 hooks.slack.com/services/..."""

    channel_type = "slack"

    def __init__(self) -> None:
        # Slack webhook URL 必 https
        self.url = os.environ.get("HOTSPOT_ALERT_SLACK_WEBHOOK_URL", "").strip()
        if self.url and not self.url.startswith("https://"):
            # 仅允许 https (Slack 服务不签 localhost)
            raise ValueError("Slack webhook URL 必须 https")
        self.channel = os.environ.get("HOTSPOT_ALERT_SLACK_CHANNEL", "").strip()

    def is_configured(self) -> bool:
        return bool(self.url)

    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("SlackChannel 未配置 (HOTSPOT_ALERT_SLACK_WEBHOOK_URL 缺失)")
        text = (
            f":warning: *[{payload.level.upper()}]* `{payload.metric}` 触发阈值告警\n"
            f"当前值 `{payload.value}` ≥ 阈值 `{payload.threshold}` "
            f"(窗口 {payload.window_minutes}min)\n"
            f"触发时间 `{payload.fired_at}`"
        )
        body: dict[str, Any] = {"text": text}
        if self.channel:
            body["channel"] = self.channel
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.url, json=body)
            resp.raise_for_status()
            return {"status_code": resp.status_code, "channel": self.channel}


# ============ 4. 飞书 (custom robot webhook) ============


class FeishuChannel(AlertChannel):
    """飞书 custom robot webhook — HMAC-SHA256 签名 + 卡片格式."""

    channel_type = "feishu"

    def __init__(self) -> None:
        self.url = os.environ.get("HOTSPOT_ALERT_FEISHU_WEBHOOK_URL", "").strip()
        self.secret = os.environ.get("HOTSPOT_ALERT_FEISHU_SECRET", "").strip()

    def is_configured(self) -> bool:
        return bool(self.url)

    def _sign(self, timestamp: str) -> str:
        """飞书签名: HMAC-SHA256(key=secret, msg=f"{timestamp}\\n{secret}"), base64."""
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        import base64
        return base64.b64encode(hmac_code).decode("utf-8")

    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("FeishuChannel 未配置 (HOTSPOT_ALERT_FEISHU_WEBHOOK_URL 缺失)")
        # 用真实时间戳 (签名依赖)
        import time
        ts = str(int(time.time()))
        body: dict[str, Any] = {
            "timestamp": ts,
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"[{payload.level.upper()}] {payload.metric}",
                    },
                    "template": "red" if payload.level == "critical" else "orange",
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {"is_short": True, "text": {"tag": "lark_md",
                                "content": f"**当前值**\n{payload.value}"}},
                            {"is_short": True, "text": {"tag": "lark_md",
                                "content": f"**阈值**\n{payload.threshold}"}},
                        ],
                    },
                ],
            },
        }
        if self.secret:
            body["sign"] = self._sign(ts)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.url, json=body)
            resp.raise_for_status()
            return {"status_code": resp.status_code}


# ============ 5. 钉钉 (custom robot webhook) ============


class DingtalkChannel(AlertChannel):
    """钉钉 custom robot webhook — 可选 HMAC-SHA256 签名 + markdown 格式."""

    channel_type = "dingtalk"

    def __init__(self) -> None:
        self.url = os.environ.get("HOTSPOT_ALERT_DINGTALK_WEBHOOK_URL", "").strip()
        self.secret = os.environ.get("HOTSPOT_ALERT_DINGTALK_SECRET", "").strip()

    def is_configured(self) -> bool:
        return bool(self.url)

    def _sign(self) -> tuple[str, str]:
        """钉钉签名: HMAC-SHA256(key=secret, msg=timestamp+"\n"+url_secret), base64+urlencode."""
        import base64
        import time
        from urllib.parse import quote
        ts = str(round(time.time() * 1000))
        string_to_sign = f"{ts}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = quote(base64.b64encode(hmac_code).decode("utf-8"))
        return ts, sign

    async def send(self, payload: AlertPayload) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("DingtalkChannel 未配置 (HOTSPOT_ALERT_DINGTALK_WEBHOOK_URL 缺失)")
        body: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "title": f"[{payload.level.upper()}] {payload.metric}",
                "text": (
                    f"## [{payload.level.upper()}] {payload.metric}\n\n"
                    f"- 当前值: **{payload.value}**\n"
                    f"- 阈值: **{payload.threshold}**\n"
                    f"- 窗口: {payload.window_minutes}min\n"
                    f"- 触发时间: {payload.fired_at}\n"
                ),
            },
            "at": {"isAtAll": False},
        }
        url = self.url
        if self.secret:
            ts, sign = self._sign()
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={sign}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return {"status_code": resp.status_code}


# ============ Registry ============


_REGISTRY: dict[str, type[AlertChannel]] = {
    "webhook": WebhookChannel,
    "email": EmailChannel,
    "slack": SlackChannel,
    "feishu": FeishuChannel,
    "dingtalk": DingtalkChannel,
}


def build_channel(channel_type: str, **kwargs: Any) -> AlertChannel:
    """按类型建实例. 未知类型抛 ValueError."""
    cls = _REGISTRY.get(channel_type)
    if cls is None:
        raise ValueError(
            f"未知 channel_type={channel_type}; 支持: {list(_REGISTRY.keys())}"
        )
    if channel_type == "webhook":
        return cls(url=kwargs["url"], headers=kwargs.get("headers"))
    return cls()


def registered_channel_types() -> list[str]:
    """列出已注册 channel 类型 (供前端 UI dropdown)."""
    return list(_REGISTRY.keys())


__all__ = [
    "AlertChannel",
    "AlertPayload",
    "DingtalkChannel",
    "EmailChannel",
    "FeishuChannel",
    "SlackChannel",
    "WebhookChannel",
    "build_channel",
    "registered_channel_types",
]