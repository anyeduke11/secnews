"""Phase 4 /api/quality router.

Phase 3.5 推迟的 4 个端点：
- ``GET /api/quality/summary``     24h 各 gate 统计
- ``GET /api/quality/rules``        当前 quality.* 配置
- ``PUT /api/quality/rules``        更新 quality.* 配置
- ``GET /api/quality/logs?item_id`` 单 item 检查日志
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.cache import invalidate as cache_invalidate, static_cache
from backend.exceptions import InvalidParamException, NotFoundException
from backend.quality.config import default_category_keywords
from backend.repository.quality_repo import (
    QualityLogRepository,
    SourceReputationRepository,
)
from backend.repository.settings_repo import SettingsRepository

router = APIRouter(prefix="/api/quality", tags=["quality"])
_log_repo = QualityLogRepository()
_settings_repo = SettingsRepository()


# ---------------------------------------------------------------------------
# GET /api/quality/summary
# ---------------------------------------------------------------------------
def _build_summary() -> dict:
    """同步构建 summary payload（在 thread pool 中执行）。"""
    summary = _log_repo.summary_24h()
    result = {
        "version": "1.2.0",
        "summary": summary,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    static_cache["quality:summary"] = result
    return result


@router.get("/summary")
async def quality_summary():
    """返回 24h 内每个 gate 的 pass / total / avg_deduction。

    Phase 9 修复：同步 DB query 放 thread pool。
    """
    cache_key = "quality:summary"
    if cache_key in static_cache:
        return static_cache[cache_key]
    return await asyncio.to_thread(_build_summary)


# ---------------------------------------------------------------------------
# Rule 描述 + 默认值（Phase 9 上线修复：前端 SettingsPanel 需要 array 格式）
# ---------------------------------------------------------------------------
# 规则元数据：(type, default, description, editable)
RULE_METADATA: dict[str, tuple[str, Any, str, bool]] = {
    "quality.strict_mode": (
        "boolean", False, "严格模式（评分 < 阈值时拒绝入库）", True,
    ),
    "quality.min_score": (
        "number", 30, "最低质量分数（0-100）", True,
    ),
    "quality.url_check_sample_rate": (
        "number", 0.1, "URL 抽检率（0-1）", True,
    ),
    "quality.url_check_concurrency": (
        "number", 5, "URL 并发检查数", True,
    ),
    "quality.url_check_timeout": (
        "number", 8, "URL 检查超时（秒）", True,
    ),
    "quality.url_check_interval_seconds": (
        "number", 300, "URL 检查任务间隔（秒）", True,
    ),
    "quality.reputation_interval_seconds": (
        "number", 21600, "源信誉重建间隔（秒）", True,
    ),
}
# quality.category_keywords.* 不在 RULE_METADATA，运行时从 category 构造


# ---------------------------------------------------------------------------
# GET /api/quality/rules
# ---------------------------------------------------------------------------
def _build_rules() -> dict:
    """同步构建 rules payload（在 thread pool 中执行）。"""
    current = _settings_repo.list_all()  # dict
    defaults_map = default_category_keywords()  # dict[cat, list[str]]
    out: list[dict[str, Any]] = []

    # 1) 7 个标量规则
    for key, (rtype, default, desc, editable) in RULE_METADATA.items():
        value = current.get(key, default)
        # type 强一致（防止 settings 表里被存成字符串）
        if rtype == "boolean" and not isinstance(value, bool):
            value = bool(value) if isinstance(value, (int, float)) else default
        elif rtype == "number" and not isinstance(value, (int, float)):
            try:
                value = float(value) if rtype == "number" else value
            except Exception:
                value = default
        out.append({
            "key": key,
            "value": value,
            "default": default,
            "type": rtype,
            "description": desc,
            "category": "general",
            "editable": editable,
        })

    # 2) 6 个 category_keywords.* 规则
    for cat, default_kws in defaults_map.items():
        key = f"quality.category_keywords.{cat}"
        value = current.get(key, default_kws)
        if not isinstance(value, list):
            value = default_kws
        out.append({
            "key": key,
            "value": value,
            "default": default_kws,
            "type": "list",
            "description": f"{cat} 分类关键词",
            "category": "keywords",
            "editable": True,
        })

    result = {
        "version": "1.2.0",
        "rules": out,
        "defaults": {
            "category_keywords": defaults_map,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    static_cache["quality:rules"] = result
    return result


@router.get("/rules")
async def quality_rules():
    """返回当前生效的 quality.* 配置。

    Phase 9 修复：返回 array 格式 + 同步 DB query 放 thread pool。
    """
    cache_key = "quality:rules"
    if cache_key in static_cache:
        return static_cache[cache_key]
    return await asyncio.to_thread(_build_rules)


# ---------------------------------------------------------------------------
# PUT /api/quality/rules
# ---------------------------------------------------------------------------
class RulesUpdate(BaseModel):
    rules: dict[str, Any] = Field(..., description="key→value to update")


@router.put("/rules")
async def update_quality_rules(body: RulesUpdate):
    """更新 quality.* 配置。"""
    if not body.rules:
        raise InvalidParamException("rules must not be empty")
    updated = []
    for key, value in body.rules.items():
        if not key.startswith("quality."):
            raise InvalidParamException(
                f"key must start with 'quality.', got {key!r}"
            )
        _settings_repo.set(key, value)
        updated.append(key)
    # 失效 static_cache
    cache_invalidate("quality:*")
    return {
        "version": "1.2.0",
        "status": "ok",
        "updated": updated,
    }


# ---------------------------------------------------------------------------
# GET /api/quality/logs
# ---------------------------------------------------------------------------
def _build_logs(item_id: str, limit: int) -> dict:
    """同步构建 logs payload（在 thread pool 中执行）。"""
    logs = _log_repo.list_for_item(item_id, limit=limit)
    return {
        "version": "1.2.0",
        "item_id": item_id,
        "logs": logs,
        "count": len(logs),
    }


@router.get("/logs")
async def quality_logs(
    item_id: str = Query(..., description="item id"),
    limit: int = Query(50, ge=1, le=200),
):
    """返回该 item 的最近 N 条 gate 检查日志。

    Phase 9 修复：同步 DB query 放 thread pool。
    """
    if not item_id:
        raise InvalidParamException("item_id is required")
    return await asyncio.to_thread(_build_logs, item_id, limit)


# ---------------------------------------------------------------------------
# GET /api/quality/source-reputation
# ---------------------------------------------------------------------------
def _build_source_reputation() -> dict:
    """同步构建 source-reputation payload（在 thread pool 中执行）。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT source, score, blacklist, pass_count, fail_count, last_updated "
        "FROM source_reputation ORDER BY score DESC"
    ).fetchall()
    sources = [
        {
            "source": r["source"],
            "score": r["score"],
            "blacklist": bool(r["blacklist"]),
            "pass_count": r["pass_count"],
            "fail_count": r["fail_count"],
            "last_updated": r["last_updated"],
        }
        for r in rows
    ]
    return {
        "version": "1.2.0",
        "sources": sources,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/source-reputation")
async def source_reputation():
    """返回 source 信誉表。

    Phase 9 修复：同步 DB query 放 thread pool。
    """
    return await asyncio.to_thread(_build_source_reputation)
