"""Phase 4 /api/proxy router."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.logging_config import logger
from backend.proxy_config import (
    ProxySettings,
    load_proxy_settings,
    save_proxy_settings,
)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])


class ProxySettingsBody(BaseModel):
    mode: str = "off"  # off / auto / manual
    http_proxy: str = ""
    https_proxy: str = ""
    socks_proxy: str = ""
    no_proxy: str = "localhost,127.0.0.1,::1"
    whitelist: list[str] = []


@router.get("/settings")
async def get_settings():
    """读当前代理配置（敏感信息遮蔽）。"""
    settings = load_proxy_settings()
    out = settings.to_dict()
    out["http_proxy"] = _redact(out.get("http_proxy", ""))
    out["https_proxy"] = _redact(out.get("https_proxy", ""))
    out["socks_proxy"] = _redact(out.get("socks_proxy", ""))
    return {"version": "1.2.0", "settings": out}


@router.put("/settings")
async def update_settings(body: ProxySettingsBody):
    """更新代理配置。"""
    try:
        settings = ProxySettings(
            mode=body.mode,
            http_proxy=body.http_proxy,
            https_proxy=body.https_proxy,
            socks_proxy=body.socks_proxy,
            no_proxy=body.no_proxy,
        )
        save_proxy_settings(settings)
        # 触发下次采集立即生效
        try:
            from backend.proxy_session import init_proxy_session

            init_proxy_session()
        except Exception:
            pass
        return {
            "version": "1.2.0",
            "status": "ok",
            "settings": body.model_dump(),
        }
    except Exception as e:
        logger.error(f"proxy settings update failed: {e}")
        return {"version": "1.2.0", "status": "error", "message": str(e)[:200]}


@router.get("/test")
async def test_proxy():
    """测试代理可用性（按 host 分组）。"""
    from backend.proxy_config import detect_system_proxy, get_proxy_url
    from backend.proxy_session import proxy_session

    settings = load_proxy_settings()
    sys_proxy = detect_system_proxy()
    test_hosts = [
        "www.baidu.com",
        "www.36kr.com",
        "github.com",
        "openai.com",
    ]
    results: list[dict[str, Any]] = []
    for host in test_hosts:
        proxy_url = get_proxy_url(f"https://{host}/")
        try:
            async with proxy_session.get(
                f"https://{host}/",
                proxy=proxy_url,
                timeout=5,
            ) as resp:
                results.append(
                    {
                        "host": host,
                        "ok": resp.status < 500,
                        "status": resp.status,
                        "via_proxy": bool(proxy_url),
                    }
                )
        except Exception as e:
            results.append(
                {
                    "host": host,
                    "ok": False,
                    "error": str(e)[:100],
                    "via_proxy": bool(proxy_url),
                }
            )
    return {
        "version": "1.2.0",
        "mode": settings.mode,
        "system_proxy": sys_proxy,
        "results": results,
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
