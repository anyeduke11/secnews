"""info_filter_gate — 三层门禁应用器 (v0.8 P1 Layer 1/2/3)

与 info_filter_service (CRUD + evaluate) 配对, 本模块提供:
- 进程内规则 cache (5s TTL): 避免每次 collect 查 DB
- 三个 hook 入口: filter_source / filter_items / filter_prompt_chunks

三段防御:
1. **filter_source**: collect() 入口 (base.py:_load_sources_from_registry 之后)
   - 输入: 单条 source config
   - 输出: (verdict, reason) — verdict ∈ {allow, deny}
   - 用法: collector 在 self.sources 循环里过滤, 命中 deny 直接 skip + 写
     crawler_runs.error_msg='info_filter_deny: <rule_id> <note>'
2. **filter_items**: item_builder 落库前 (item_builder.py:_build_items 末)
   - 输入: list[HotspotItem] (or raw dicts)
   - 输出: 过滤后的 list
   - 用法: 二次防御, 防 Layer 1 schema drift 漏掉
3. **filter_prompt_chunks**: ai_hub 拼 prompt 前
   - 输入: list[{source_id, source_name, category, content}]
   - 输出: 过滤后的 list
   - 用法: 让 deny 源 0 token 消耗, 同时不让其污染 LLM context

feature gate:
- 默认关闭 (feature_gates.toml info_filter=false)
- 关闭时 evaluate 直接返回 neutral, 不查表, 零开销
"""
from __future__ import annotations

import time
from typing import Any, Optional

from backend.extensions import is_extension_enabled
from backend.logging_config import logger

# 进程内规则 cache — 5s TTL 足够 (用户改规则无需实时生效, 但要秒级感知)
_CACHE_TTL_S = 5.0
_cached_rules: Optional[list[dict]] = None
_cached_at: float = 0.0


def _is_enabled() -> bool:
    """feature gate 守卫. False 时全部 pass-through, 不查表."""
    try:
        return is_extension_enabled("info_filter")
    except Exception:
        return False


def _load_rules_cached() -> list[dict]:
    """读 DB 拿 enabled 规则列表, 进程内缓存."""
    global _cached_rules, _cached_at
    now = time.monotonic()
    if _cached_rules is not None and (now - _cached_at) < _CACHE_TTL_S:
        return _cached_rules
    try:
        from backend.repository.db import get_connection
        from backend.services.info_filter_service import list_rules
        conn = get_connection()
        _cached_rules = list_rules(conn, enabled_only=True)
        _cached_at = now
        return _cached_rules
    except Exception as e:
        # DB 不可用 → 不阻断业务, 视为 neutral
        logger.warning(f"info_filter_gate._load_rules_cached failed: {e}")
        return []


def invalidate_cache() -> None:
    """API 改规则后立即让下一次 evaluate 重新读 DB."""
    global _cached_rules, _cached_at
    _cached_rules = None
    _cached_at = 0.0


def filter_source(source: dict) -> tuple[bool, Optional[str]]:
    """Layer 1 — collect 入口源级过滤.

    Args:
        source: 单条 source config, 必须含 name; category 可选.

    Returns:
        (allowed, reason):
        - allowed=True: 放行
        - allowed=False: 拒绝, reason 是 rule 描述 (e.g. "deny:source_name:华尔街见闻")
    """
    if not _is_enabled():
        return True, None
    name = source.get("name", "")
    category = source.get("category", "")
    rules = _load_rules_cached()
    if not rules:
        return True, None
    from backend.services.info_filter_service import evaluate
    verdict, matched = evaluate(
        rules, category=category, source_name=name,
    )
    if verdict == "deny":
        return False, (
            f"info_filter_deny: rule_id={matched['id']} "
            f"match_kind={matched['match_kind']} "
            f"match_value={matched['match_value']!r}"
        )
    return True, None


def filter_items(items: list[Any]) -> list[Any]:
    """Layer 2 — item 落库前过滤.

    Args:
        items: HotspotItem 列表或 raw dict 列表 (用 .get / [] 取 source_name/category)

    Returns:
        过滤后的列表 (deny 源对应 item 全 drop).
    """
    if not _is_enabled():
        return items
    rules = _load_rules_cached()
    if not rules:
        return items
    from backend.services.info_filter_service import evaluate
    kept: list[Any] = []
    dropped = 0
    for it in items:
        # 兼容 HotspotItem 与 raw dict.
        # HotspotItem.source 是源名 (str); Category enum 取 .value.
        if isinstance(it, dict):
            name = (
                it.get("source_name", "")
                or it.get("source", "")
                or it.get("name", "")
            )
            cat_raw = it.get("category", "")
            cat = cat_raw.value if hasattr(cat_raw, "value") else cat_raw
        else:
            name = getattr(it, "source_name", "") or getattr(it, "source", "") or ""
            cat_raw = getattr(it, "category", "") or ""
            cat = cat_raw.value if hasattr(cat_raw, "value") else cat_raw
        verdict, _ = evaluate(rules, category=cat or "", source_name=name or "")
        if verdict == "deny":
            dropped += 1
            continue
        kept.append(it)
    if dropped:
        logger.info(f"info_filter: dropped {dropped} items at Layer 2")
    return kept


def filter_prompt_chunks(chunks: list[dict]) -> list[dict]:
    """Layer 3 — ai_hub 拼 prompt 前过滤.

    Args:
        chunks: list[{source_id, source_name, category, content, ...}]

    Returns:
        过滤后的列表.
    """
    if not _is_enabled():
        return chunks
    rules = _load_rules_cached()
    if not rules:
        return chunks
    from backend.services.info_filter_service import evaluate
    kept: list[dict] = []
    dropped = 0
    for ch in chunks:
        name = ch.get("source_name", "") or ch.get("source", "")
        cat = ch.get("category", "")
        sid = ch.get("source_id")
        verdict, _ = evaluate(
            rules, category=cat or "", source_name=name or "",
            source_id=sid,
        )
        if verdict == "deny":
            dropped += 1
            continue
        kept.append(ch)
    if dropped:
        logger.info(
            f"info_filter: dropped {dropped} chunks at Layer 3 "
            f"(0 token cost for denied sources)"
        )
    return kept


__all__ = [
    "filter_source",
    "filter_items",
    "filter_prompt_chunks",
    "invalidate_cache",
]
