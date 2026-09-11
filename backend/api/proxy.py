"""Phase 4 /api/proxy router — 代理配置读写 / 连通性对照测试 / 熔断状态.

cadence 修正批 T5 修复:
- ``/test`` 此前 ``from backend.proxy_session import proxy_session`` 引用不存在的符号,
  每次调用 500; PUT 里 ``init_proxy_session()`` 同样不存在 (被 try/except 吞掉)。
- PUT 改为合并语义: 未提交的字段保留现值 (此前 body 默认空串会把手动代理配置抹掉)。
- ``/test`` 直连 vs 经代理 逐站对照 (实现在 utils/proxy_probe.py), 返回
  ``status: ok|degraded|down|skipped`` + ``summary`` 供设置页展示。
- 新增 ``GET /settings`` 的 ``health`` (熔断器快照) 与 ``POST /health/reset``。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.logging_config import logger
from backend.version import APP_VERSION as API_VERSION

# cadence 修正批 T5: load/save 以模块属性方式调用 (_pc.*), 让 test_api 的
# ``patch.object(proxy_config, "save_proxy_settings", wraps=...)`` 文件保护真正生效 —
# 按值导入曾导致该保护失灵, 测试的 PUT 会把真实 proxy_config.json 写回 off。
from backend import proxy_config as _pc
from backend.proxy_config import (
    BUILTIN_NO_PROXY,
    BUILTIN_PROXY_URL,
    VALID_MODES,
    ProxySettings,
)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])


class ProxySettingsBody(BaseModel):
    """PUT body: 全部可选, 未提交字段保留现值。``whitelist`` 为旧前端遗留, 忽略。"""

    mode: str | None = None  # off / builtin / auto / manual
    http_proxy: str | None = None
    https_proxy: str | None = None
    socks_proxy: str | None = None
    no_proxy: str | None = None
    whitelist: list[str] | None = None


def _settings_payload(settings: ProxySettings) -> dict[str, Any]:
    out = settings.to_dict()
    for k in ("http_proxy", "https_proxy", "socks_proxy"):
        out[k] = _redact(out.get(k, ""))
    return out


@router.get("/settings")
async def get_settings():
    """读当前代理配置 (敏感信息遮蔽) + 生效代理 + 熔断器快照 + 内置预设。"""
    settings = _pc.load_proxy_settings()
    effective = _pc.configured_proxy_url("https://example.com/", settings)
    return {
        "version": API_VERSION,
        "settings": _settings_payload(settings),
        "valid_modes": list(VALID_MODES),
        "effective_proxy": _redact(effective or ""),
        "builtin": {"proxy_url": BUILTIN_PROXY_URL, "no_proxy": BUILTIN_NO_PROXY},
        "health": _pc.proxy_health_snapshot(),
        "detected_system_proxy": _pc.detect_system_proxy() if settings.mode == "auto" else None,
    }


@router.put("/settings")
async def update_settings(body: ProxySettingsBody):
    """更新代理配置 (合并语义); 保存后重置熔断器, 下一次请求即按新配置生效。"""
    try:
        current = _pc.load_proxy_settings()
        mode = (body.mode or current.mode).lower()
        if mode not in VALID_MODES:
            return {
                "version": API_VERSION,
                "status": "error",
                "message": f"invalid mode {body.mode!r}; expected one of {list(VALID_MODES)}",
            }
        settings = ProxySettings(
            mode=mode,
            http_proxy=current.http_proxy if body.http_proxy is None else body.http_proxy,
            https_proxy=current.https_proxy if body.https_proxy is None else body.https_proxy,
            socks_proxy=current.socks_proxy if body.socks_proxy is None else body.socks_proxy,
            no_proxy=current.no_proxy if body.no_proxy is None else (body.no_proxy or BUILTIN_NO_PROXY),
        )
        _pc.save_proxy_settings(settings)
        _pc.reset_proxy_health()
        logger.info(f"proxy settings updated: mode={settings.mode}")
        return {
            "version": API_VERSION,
            "status": "ok",
            "settings": _settings_payload(settings),
            "effective_proxy": _redact(_pc.configured_proxy_url("https://example.com/", settings) or ""),
            "health": _pc.proxy_health_snapshot(),
        }
    except Exception as e:
        logger.error(f"proxy settings update failed: {e}")
        return {"version": API_VERSION, "status": "error", "message": str(e)[:200]}


@router.post("/health/reset")
async def reset_health():
    """手动闭合熔断器 (代理修好后不想等窗口过期时用)。"""
    _pc.reset_proxy_health()
    return {"version": API_VERSION, "status": "ok", "health": _pc.proxy_health_snapshot()}


@router.get("/test")
async def test_proxy():
    """连通性对照: 每个探测站 直连 vs 经代理 并列; 汇总 status / summary。"""
    from backend.utils.proxy_probe import run_connectivity_test

    settings = _pc.load_proxy_settings()
    out = await run_connectivity_test(settings)
    out["effective_proxy"] = _redact(out.get("effective_proxy", ""))
    return {
        "version": API_VERSION,
        "mode": settings.mode,
        "system_proxy": _pc.detect_system_proxy() if settings.mode == "auto" else None,
        "health": _pc.proxy_health_snapshot(),
        **out,
    }


def _redact(url: str) -> str:
    """``http://user:pass@host:port`` → ``http://user:***@host:port``。"""
    if not url:
        return url
    try:
        if "@" not in url:
            return url
        scheme_end = url.find("://") + 3
        at = url.find("@", scheme_end)
        if at < 0:
            return url
        auth = url[scheme_end:at]
        if ":" in auth:
            user, _ = auth.split(":", 1)
            return f"{url[:scheme_end]}{user}:***{url[at:]}"
        return url
    except Exception:
        return url
