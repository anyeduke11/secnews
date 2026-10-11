"""内容偏好 (类目 / 来源) API — DEV-0315 (A 噪音抑制 + B 显式开关 整合, 归拢设置)。

端点 (前缀沿用 ``/api/settings``, URL 与合并前一致):
- ``GET   /api/settings/content-preferences``  读偏好 + 可得来源清单 (近 30 天实际入库)
- ``PATCH /api/settings/content-preferences``  写偏好 (settings.kv + audit_log)

消费方: ``/api/hotspots`` 排序第二轴 (``hotspot_service._rank_items``, 只升降不删)。
存储键 ``interest.content_preferences`` (复用已登记前缀, 不动 namespace 契约)。

拆分缘由: 原并入 ``settings.py`` 后超该文件 R3 豁免上限 (291 行, 只许收缩),
按守卫要求拆出独立文件 (见 ``backend/api/AGENTS.md`` 路由 ≤150 行规格)。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.exceptions import InvalidParamException
from backend.logging_config import logger
from backend.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])

_CONTENT_PREF_KEY = "interest.content_preferences"
_CONTENT_PREF_LEVELS = ("more", "normal", "less")
_CONTENT_PREF_SOURCE_DAYS = 30
_CONTENT_PREF_SOURCE_LIMIT = 200


class ContentPreferencesRequest(BaseModel):
    """内容偏好: 类目/来源 → 三级 (more/normal/less)。normal = 不存 (等价缺省)。"""

    categories: dict[str, str] = Field(default_factory=dict, description="类目 → 三级偏好")
    sources: dict[str, str] = Field(default_factory=dict, description="来源 → 三级偏好")
    actor: str = Field("web")


def _clean_content_prefs(table: dict[str, str] | None, allowed: set[str] | None) -> dict[str, str]:
    """校验 + 归一: 去 normal / 非法 level / 空或不在允许集的 key (保输入序)。"""
    out: dict[str, str] = {}
    for k, v in (table or {}).items():
        if not isinstance(k, str) or not k.strip():
            continue
        if allowed is not None and k not in allowed:
            continue
        if v in _CONTENT_PREF_LEVELS and v != "normal":
            out[k] = v
    return out


@router.get("/content-preferences")
async def get_content_preferences() -> dict:
    """读取内容偏好 + 可得来源清单 (近 30 天实际入库的来源, 按量降序)。"""
    from backend.domain.enums import Category
    from backend.repository.hotspot_repo import distinct_sources_since
    from backend.services.hotspot_service import load_content_preferences

    prefs = await asyncio.to_thread(load_content_preferences)
    since = (datetime.now(timezone.utc) - timedelta(days=_CONTENT_PREF_SOURCE_DAYS)).isoformat()
    sources = await asyncio.to_thread(distinct_sources_since, since, _CONTENT_PREF_SOURCE_LIMIT)
    return {
        "preferences": {
            "categories": prefs.get("categories", {}),
            "sources": prefs.get("sources", {}),
        },
        "valid_categories": [c.value for c in Category],
        "available_sources": sources,
        "levels": list(_CONTENT_PREF_LEVELS),
        "source_window_days": _CONTENT_PREF_SOURCE_DAYS,
    }


@router.patch("/content-preferences")
async def set_content_preferences(body: ContentPreferencesRequest):
    """写入内容偏好 (settings.kv 持久化 + audit_log)。

    校验: 类目必须在 ``Category`` 枚举内 (防 typo); level 必须 ∈ more/normal/less。
    来源名不硬校验 (源会新增/下线, 硬校验会拒绝合法新源) — 只做格式与 level 校验。
    """
    from backend.domain.enums import Category

    valid_cats = {c.value for c in Category}
    bad_cats = [
        k for k, v in (body.categories or {}).items()
        if v != "normal" and k not in valid_cats
    ]
    if bad_cats:
        raise InvalidParamException(
            f"unknown categories {bad_cats}; valid: {sorted(valid_cats)}"
        )
    bad_levels = [
        f"{k}={v}"
        for table in (body.categories, body.sources)
        for k, v in (table or {}).items()
        if v not in _CONTENT_PREF_LEVELS
    ]
    if bad_levels:
        raise InvalidParamException(
            f"invalid levels {bad_levels}; valid: {list(_CONTENT_PREF_LEVELS)}"
        )

    categories = _clean_content_prefs(body.categories, valid_cats)
    sources = _clean_content_prefs(body.sources, None)
    payload: dict = {}
    if categories:
        payload["categories"] = categories
    if sources:
        payload["sources"] = sources

    svc = SettingsService()
    old = svc.get(_CONTENT_PREF_KEY, {})
    svc.set(
        _CONTENT_PREF_KEY,
        payload,
        actor=body.actor,
        action="feed.content_prefs.set",
        detail={"from": old, "to": payload},
    )
    logger.info("content preferences set: {} -> {} (actor={})", old, payload, body.actor)
    return {"status": "ok", "preferences": payload}
