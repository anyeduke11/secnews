"""trigger_webhook_api — webhook 触发入口 (Phase D D1).

对外 2 端点:
- POST ``/api/trigger/webhook/{source}`` — 外部 webhook 入口; source 是 path
  参数, 透传给 trigger 输入 (区分 GitHub / Stripe / 自定义); target 强制
  ``webhook-{source}`` 或 query 传 ``?target=xxx``
- GET  ``/api/trigger/webhook/health`` — 健康探测 (无副作用)

设计:
- 缺签名 + secret 已配置 → 422 (R7 fail-closed 沿用 envelope P3-2)
- 限流超限 → 429 (由 trigger_gate.submit 抛 ThrottleExceededError)
- source 不白名单 → 422 (R12 fail loud, 不静默路由)

注册: 在 _registry.py 由 ``is_extension_enabled("trigger_gate")`` 守门。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request

from backend.logging_config import logger
from backend.services.trigger_gate.triggers import webhook as wh_mod
from backend.services.trigger_gate.triggers.webhook import (
    SignatureInvalidError,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/trigger/webhook", tags=["trigger-webhook"])

# 允许的 source 名单 — 不在白名单 → 422 fail loud (R12)
VALID_WEBHOOK_SOURCES: frozenset[str] = frozenset(
    {
        "github",
        "stripe",
        "secnews",
        "custom",
        "cve_feed",
        "cti",
    }
)


@router.get("/health")
async def health() -> dict[str, str]:
    """无副作用健康探测 — 用于上游 watchdog 探活."""
    return {"status": "ok", "kind": "trigger-webhook"}


@router.post("/{source}")
async def trigger_webhook(
    source: str,
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    target: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
):
    """外部 webhook 入口 — 限流 + 签名校验 + 入队.

    Path ``source`` 透传到 trigger inputs.payload["source"], 区分事件源;
    不在白名单 → 422 fail loud (R12)。
    """
    if source not in VALID_WEBHOOK_SOURCES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"webhook source {source!r} 不在白名单",
                "code": "VALIDATE_FAILED",
                "hint": f"允许: {sorted(VALID_WEBHOOK_SOURCES)}",
            },
        )

    payload = await _read_payload(request)
    path = f"/api/trigger/webhook/{source}"

    target_id = target or f"webhook-{source}"
    trigger = wh_mod._default
    try:
        ticket = trigger.submit(
            path=path,
            payload=payload,
            signature=x_webhook_signature,
            target_type="skill",
            target_id=target_id,
            user_id=user_id,
        )
    except SignatureInvalidError as e:
        # R7 fail-closed: secret 已配置但签名无效 → 422 (envelope)
        logger.warning(
            "webhook signature invalid",
            extra={"trace_id": "", "source": source, "reason": str(e)},
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(e),
                "code": "SIGNATURE_INVALID",
                "hint": "校验 X-Webhook-Signature 是否与 path|payload 的 SHA-256 HMAC 一致",
            },
        )

    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "target_id": target_id,
        "source": source,
    }


async def _read_payload(request: Request) -> dict:
    """读 body — 接受 JSON dict 或 raw bytes (签名时按 path|payload_bytes)."""
    body = await request.body()
    if not body:
        return {}
    try:
        import json as _json

        return _json.loads(body)
    except Exception:
        # 非 JSON 时原样回传 (webhook 可能是 form 编码)
        return {"_raw_b64": body.hex()[:200]}