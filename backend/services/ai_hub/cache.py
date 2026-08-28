"""ai_hub/cache.py — LLM 缓存统一操作 (llm_cache 表)。

LLMService 与 AIService 共享同一张 ``llm_cache`` 表，但序列化格式不同：
- LLMService: 纯文本 ``response``
- AIService: JSON 字符串 ``response`` (dict)

本模块提供两套接口，避免两个类耦合。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.repository.db import get_connection

log = logging.getLogger("hotspot.ai_hub")


# ── LLMService 缓存 (纯文本) ─────────────────────────────────────

def get_llm_cache(cache_key: str, ttl_seconds: int | None = None) -> str | None:
    """读取 LLMService 缓存（纯文本 response）。"""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT response, cached_at, ttl_seconds FROM llm_cache "
            "WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        # 检查 TTL
        cached_at = datetime.fromisoformat(row["cached_at"])
        ttl = ttl_seconds if ttl_seconds is not None else row["ttl_seconds"]
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age < ttl:
            return row["response"]
        # 过期删除
        conn.execute("DELETE FROM llm_cache WHERE cache_key = ?", (cache_key,))
        return None
    except Exception:
        return None


def set_llm_cache(cache_key: str, response: str, ttl_seconds: int = 86400) -> None:
    """写入 LLMService 缓存（纯文本 response）。"""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache "
            "(cache_key, provider, model, response, cached_at, ttl_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                cache_key,
                "",
                "",
                response,
                datetime.now(timezone.utc).isoformat(),
                ttl_seconds,
            ),
        )
    except Exception:
        pass


# ── AIService 缓存 (JSON dict) ──────────────────────────────────

def get_ai_cache(key: str) -> dict | None:
    """读取 AIService 缓存（JSON dict）。"""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT response FROM llm_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["response"])
    except Exception:
        return None


def set_ai_cache(key: str, value: dict, ttl_seconds: int = 86400) -> None:
    """写入 AIService 缓存（JSON dict）。"""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache "
            "(cache_key, provider, model, response, cached_at, ttl_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                key,
                value.get("provider", ""),
                "",  # model 由 AIService 自行决定
                json.dumps(value, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
                ttl_seconds,
            ),
        )
    except Exception:
        pass
