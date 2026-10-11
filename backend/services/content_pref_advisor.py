"""Content Preference Advisor — 内容偏好 AI 优化建议 (DEV-0316)。

职责 (建议**不自动生效**, 用户采纳才写 kv — 与 interest_domain_advisor 同范式):
- ``build_advisor_input``: 确定性组装 — 近 30d 各类目/来源行为净分
  (interest_signal_stats_by_axis, |net| 降序 top N) + 当前生效偏好。全为统计值。
- ``get_suggestions``: 缓存 (settings.kv ``interest.content_pref_advisor_cache``,
  24h TTL) → 过期/force 则组装 → ``llm_service.generate`` (ai_hub 单出口,
  复用 task=interest_advisor 的 light 档路由, 不动 ai_hub 调用链) → 解析 JSON
  {categories, sources, reasons} → 枚举校验 (类目 ∈ Category, level ∈ more/less,
  每轴 ≤5) → 写缓存。失败返回上次缓存或空 + note, 不抛错。

SQL 集中在 hotspot_repo (interest_signal_stats_by_axis), 本模块纯逻辑
(新 service 文件含 SQL 会被扫描器拦截, DEV-0182 先例)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.hotspot_repo import interest_signal_stats_by_axis
from backend.services import ai_hub as _ai_hub_mod
from backend.services.settings_service import SettingsService

# 复用已注册的 light 档任务路由 (红线: 未裁决前不动 ai_hub 调用链, 不新增 task 接线)
ADVISOR_TASK = "interest_advisor"
_CACHE_KEY = "interest.content_pref_advisor_cache"
_CACHE_TTL_S = 86400.0  # 24h
_MAX_PER_AXIS = 5
_TOP_N = 8
_MAX_TOKENS = 900
_TEMPERATURE = 0.3
_WINDOW_DAYS = 30
_VALID_LEVELS = ("more", "less")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _behavior_lines(stats: dict[str, dict]) -> list[dict[str, Any]]:
    """净分表 → |net| 降序 top N (正负两侧都展示给模型)。"""
    ranked = sorted(stats.items(), key=lambda kv: abs(kv[1]["net"]), reverse=True)
    return [
        {"key": k, "net": round(v["net"], 2), "events": v["events"]}
        for k, v in ranked[:_TOP_N]
    ]


def build_advisor_input() -> dict[str, Any]:
    """两通道确定性组装 (近 30d 类目/来源行为净分 + 当前生效偏好)。"""
    from backend.services.hotspot_service import effective_content_preferences

    since = (datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)).isoformat()
    cats = _behavior_lines(interest_signal_stats_by_axis("category", since))
    srcs = _behavior_lines(interest_signal_stats_by_axis("source", since))
    return {
        "category_behavior": cats,
        "source_behavior": srcs,
        "current_effective": effective_content_preferences(),
    }


def _clean_axis(table: Any, valid_keys: set[str] | None) -> dict[str, str]:
    """LLM 输出轴表 → 校验: level ∈ {more,less}; key ∈ 枚举 (类目轴); ≤5 项。"""
    out: dict[str, str] = {}
    if not isinstance(table, dict):
        return out
    for k, v in table.items():
        if not isinstance(k, str) or v not in _VALID_LEVELS:
            continue
        if valid_keys is not None and k not in valid_keys:
            continue
        if len(out) >= _MAX_PER_AXIS:
            break
        out[k] = v
    return out


def _parse_reply(raw: str) -> dict[str, Any]:
    """LLM 输出 → {categories, sources, reasons}; 非法输入抛 ValueError。"""
    if not raw or not raw.strip():
        raise ValueError("empty llm reply")
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    elif "{" in s:
        s = s[s.find("{"): s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"llm reply not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("llm reply not a JSON object")
    reasons = obj.get("reasons")
    return {
        "categories": obj.get("categories"),
        "sources": obj.get("sources"),
        "reasons": reasons if isinstance(reasons, dict) else {},
    }


def _read_cache() -> dict[str, Any] | None:
    try:
        cached = SettingsService().get(_CACHE_KEY)
    except Exception as e:
        logger.warning(f"content-pref advisor cache read failed: {e}")
        return None
    if isinstance(cached, dict) and isinstance(cached.get("categories"), dict):
        return cached
    return None


def _cache_expired(cached: dict[str, Any]) -> bool:
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["cached_at"])
        return age.total_seconds() > _CACHE_TTL_S
    except (KeyError, TypeError, ValueError):
        return True


def _write_cache(payload: dict[str, Any]) -> None:
    try:
        SettingsService().set(
            _CACHE_KEY,
            payload,
            actor="system",
            action="feed.content_pref_advisor_refresh",
        )
    except Exception as e:
        logger.warning(f"content-pref advisor cache write failed (kept): {e}")


async def get_suggestions(force: bool = False) -> dict[str, Any]:
    """读缓存或刷新; 任何失败都返回 {categories, sources, reasons, cached_at, note}。"""
    from backend.domain.enums import Category
    from backend.services.ai_hub.prompts import build_content_pref_advisor_prompt
    from backend.services.monthly_report_service import CATEGORY_LABELS

    cached = _read_cache()
    if cached is not None and not force and not _cache_expired(cached):
        return {
            "categories": cached["categories"],
            "sources": cached.get("sources", {}),
            "reasons": cached.get("reasons", {}),
            "cached_at": cached.get("cached_at"),
            "note": "",
        }

    note = ""
    try:
        inp = build_advisor_input()
        prompt = build_content_pref_advisor_prompt(
            category_behavior=[
                {"category": e["key"], "net": e["net"], "events": e["events"]}
                for e in inp["category_behavior"]
            ],
            source_behavior=[
                {"source": e["key"], "net": e["net"], "events": e["events"]}
                for e in inp["source_behavior"]
            ],
            current_effective=inp["current_effective"],
            category_labels=CATEGORY_LABELS,
        )
        raw = await _ai_hub_mod.llm_service.generate(
            prompt, task=ADVISOR_TASK, max_tokens=_MAX_TOKENS, temperature=_TEMPERATURE
        )
        parsed = _parse_reply(raw)
        valid_cats = {c.value for c in Category}
        cats = _clean_axis(parsed["categories"], valid_cats)
        srcs = _clean_axis(parsed["sources"], None)
        if not cats and not srcs:
            raise ValueError("no suggestion survived enum/level checks")
        reasons = {
            k: v for k, v in parsed["reasons"].items() if isinstance(v, str) and (k in cats or k in srcs)
        }
        payload = {
            "categories": cats,
            "sources": srcs,
            "reasons": reasons,
            "cached_at": _now_iso(),
        }
        _write_cache(payload)
        return {**payload, "note": ""}
    except Exception as e:
        logger.warning(f"content-pref advisor refresh failed: {e}")
        note = f"advisor refresh failed: {e}"

    if cached is not None:
        return {
            "categories": cached["categories"],
            "sources": cached.get("sources", {}),
            "reasons": cached.get("reasons", {}),
            "cached_at": cached.get("cached_at"),
            "note": note,
        }
    return {"categories": {}, "sources": {}, "reasons": {}, "cached_at": None, "note": note}


__all__ = ["ADVISOR_TASK", "build_advisor_input", "get_suggestions"]
