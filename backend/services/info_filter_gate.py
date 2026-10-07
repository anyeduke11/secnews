"""info_filter_gate — 三层门禁应用器 (v0.8 P1 Layer 1/2/3)

与 info_filter_service (CRUD + evaluate) 配对, 本模块提供:
- 进程内规则 cache (5s TTL): 避免每次 collect 查 DB
- 三个 hook 入口: filter_source / filter_items / filter_prompt_chunks
- post-ingest 补偿判别: post_ingest_semantic_filter (v0.8.7 P3-F —
  语义 LLM 判别已移出采集热路径, 落库后 tick 尾异步补偿; D2 检测保留兜底)

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
from typing import Any

from backend.extensions import is_extension_enabled
from backend.logging_config import logger

# 进程内规则 cache — 5s TTL 足够 (用户改规则无需实时生效, 但要秒级感知)
_CACHE_TTL_S = 5.0
_cached_rules: list[dict] | None = None
_cached_at: float = 0.0


def _is_enabled() -> bool:
    """feature gate 守卫. False 时全部 pass-through, 不查表."""
    try:
        return is_extension_enabled("info_filter")
    except Exception:
        return False


def _semantic_enabled() -> bool:
    from backend.extensions import is_extension_enabled
    return is_extension_enabled("semantic_filter")


def _item_text(it: Any) -> str:
    """Layer 2 item → 判别文本 (title + summary, 兼容 dict / HotspotItem)。"""
    def _get(obj, key: str) -> str:
        if isinstance(obj, dict):
            return str(obj.get(key, "") or "")
        return str(getattr(obj, key, "") or "")
    parts = [_get(it, "title"), _get(it, "summary")]
    return " ".join(p for p in parts if p.strip())


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


def filter_source(source: dict) -> tuple[bool, str | None]:
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
        # v0.8.7 P3-F: 语义 LLM 判别已移出采集热路径 (post-ingest 化, 见
        # post_ingest_semantic_filter)。此前在本函数内联调 semantic_verdict,
        # 而本函数运行于采集 loop 线程 → D2 检测恒 fail-open (判别量恒 0)。
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


def post_ingest_semantic_filter(
    window_hours: int = 24, limit: int = 50,
) -> dict[str, Any]:
    """post-ingest 语义补偿判别 (v0.8.7 P3-F, PLAN_P3 F 方案)。

    采集落库后由 tick job 尾部异步补偿判别 (asyncio.to_thread → 无 running
    loop → semantic_verdict 真调 LLM); deny → is_hidden=1 + flag 打标,
    **不阻塞采集、不删除** (可回溯)。D2 loop 检测保留作兜底防线 (防回归:
    若未来又有人把 LLM 判别放回 loop 线程, 依旧诚实可见)。

    幂等: 已判别条目打 ``semantic_checked`` flag, 候选查询 NOT LIKE 跳过;
    fail-open (LLM 失败/解析失败) **不打标** → 下一 tick 重试, 滚出窗口自然停。

    Returns:
        {"candidates", "judged", "rejected", "errors", "skipped_reason"}
    """
    summary: dict[str, Any] = {
        "candidates": 0, "judged": 0, "rejected": 0, "errors": 0,
        "skipped_reason": None,
    }
    if not _is_enabled():
        summary["skipped_reason"] = "info_filter_gate_off"
        return summary
    if not _semantic_enabled():
        summary["skipped_reason"] = "semantic_filter_gate_off"
        return summary

    import json as _json
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection
    from backend.services.ai_hub.tasks import semantic_verdict

    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    rows = conn.execute(
        "SELECT id, title, summary, source, quality_flags FROM hotspots "
        "WHERE is_hidden = 0 AND title != '' "
        "  AND COALESCE(fetched_at, published_at, ingested_at) >= ? "
        "  AND quality_flags NOT LIKE '%semantic_checked%' "
        "ORDER BY fetched_at DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()
    summary["candidates"] = len(rows)

    for r in rows:
        text = _item_text({"title": r["title"], "summary": r["summary"]})
        if not text.strip():
            continue
        sv = semantic_verdict(text)
        reason = str(sv.get("reason", ""))
        fail_open = reason.endswith("fail_open") or reason.startswith("parse_failed")
        if fail_open:
            # 不打标 → 下轮重试 (出窗即停); 失败已落 llm_usage_log (D2 契约)
            summary["errors"] += 1
            continue
        summary["judged"] += 1
        try:
            flags = _json.loads(r["quality_flags"] or "[]")
        except Exception:
            flags = []
        if not isinstance(flags, list):
            flags = []
        flags.append("semantic_checked")
        if sv.get("verdict") == "reject":
            flags.append("semantic_reject")
            conn.execute(
                "UPDATE hotspots SET is_hidden = 1, quality_flags = ? WHERE id = ?",
                (_json.dumps(flags, ensure_ascii=False), r["id"]),
            )
            summary["rejected"] += 1
            logger.info(
                f"info_filter: post-ingest semantic reject hotspot {r['id']} "
                f"source={r['source']!r} reason={reason!r} (hidden, 可回溯)"
            )
        else:
            conn.execute(
                "UPDATE hotspots SET quality_flags = ? WHERE id = ?",
                (_json.dumps(flags, ensure_ascii=False), r["id"]),
            )
    conn.commit()

    if summary["judged"] or summary["rejected"] or summary["errors"]:
        # P0-10: 有判别量才 INFO (obs 面: 判别量/拒绝量 24h 观测口)
        logger.info(
            f"info_filter: post-ingest semantic filter candidates="
            f"{summary['candidates']} judged={summary['judged']} "
            f"rejected={summary['rejected']} fail_open={summary['errors']}"
        )
    return summary


__all__ = [
    "filter_items",
    "filter_prompt_chunks",
    "filter_source",
    "invalidate_cache",
    "post_ingest_semantic_filter",
]
