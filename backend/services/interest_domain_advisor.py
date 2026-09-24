"""Interest Domain Advisor — 关注域 AI 推荐 (density T3, 设计稿 §4.2).

职责 (推荐**不自动生效**, 用户采纳才写 kv):
- ``build_recommendation_input``: 确定性组装三通道输入 — 近 7d 各域入库
  分布 (top N + 占比) / interest_signals 近 30d 行为聚合分 (复用
  InterestEngineService.aggregate) / 当前勾选域。全部为统计值, 不含
  原始 URL 与标题。
- ``get_recommendations``: 缓存 (settings.kv ``interest.advisor_cache``,
  24h TTL) → 过期/force 则组装输入 → ``llm_service.generate`` (ai_hub
  单出口, task=interest_advisor 走 FLASH/light 档) → 解析 JSON
  {recommended ≤5, reasons} → 域枚举校验 (PRACTICE_DOMAIN_LABELS 键集,
  越界丢弃) → 写缓存。解析失败/LLM 异常 → 返回上次缓存或空列表 +
  note, 不抛错 (手动刷新/每日 job 兜底都依赖此契约)。

SQL 集中在 hotspot_repo (interest_domain_distribution), 本模块纯逻辑 —
新 service 文件含 SQL 会被扫描器整文件拦截 (DEV-0182 先例)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.hotspot_repo import interest_domain_distribution
from backend.services import ai_hub as _ai_hub_mod
from backend.services.interest_engine_service import InterestEngineService
from backend.services.settings_service import SettingsService

ADVISOR_TASK = "interest_advisor"
_CACHE_KEY = "interest.advisor_cache"
_CACHE_TTL_S = 86400.0  # 24h
_MAX_RECOMMENDED = 5
_MAX_TOKENS = 800
_TEMPERATURE = 0.3
_TOP_N = 5
_INTEREST_KEY = "interest.practice_domains"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_recommendation_input(top_n: int = _TOP_N) -> dict[str, Any]:
    """三通道确定性组装 (无原始 URL/标题, 只含统计)。"""
    dist = interest_domain_distribution(days=7)
    total = sum(dist.values()) or 1
    ingest = [
        {"domain": d, "count": c, "share": round(c / total, 4)}
        for d, c in sorted(dist.items(), key=lambda p: p[1], reverse=True)[:top_n]
    ]
    agg = InterestEngineService().aggregate()
    behavior = [
        {
            "domain": d,
            "score": agg[d]["behavioral_score"],
            "events_30d": agg[d]["events_30d"],
        }
        for d in sorted(
            agg, key=lambda k: agg[k]["behavioral_score"], reverse=True
        )[:top_n]
    ]
    raw = SettingsService().get(_INTEREST_KEY, [])
    current = (
        [d for d in raw if isinstance(d, str)] if isinstance(raw, list) else []
    )
    return {
        "ingest_7d": ingest,
        "behavior_30d": behavior,
        "current_selected": current,
    }


def _parse_reply(raw: str) -> dict[str, Any]:
    """LLM 输出 → {recommended, reasons}; 非法输入抛 ValueError。"""
    if not raw or not raw.strip():
        raise ValueError("empty llm reply")
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    elif "{" in s:
        s = s[s.find("{"):s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"llm reply not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("llm reply not a JSON object")
    recommended = obj.get("recommended")
    reasons = obj.get("reasons")
    if not isinstance(recommended, list) or not isinstance(reasons, dict):
        raise ValueError("llm reply missing recommended/reasons")
    return {
        "recommended": [d for d in recommended if isinstance(d, str)],
        "reasons": {k: v for k, v in reasons.items() if isinstance(v, str)},
    }


def _read_cache() -> dict[str, Any] | None:
    try:
        cached = SettingsService().get(_CACHE_KEY)
    except Exception as e:
        logger.warning(f"advisor cache read failed: {e}")
        return None
    if isinstance(cached, dict) and isinstance(cached.get("recommended"), list):
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
            action="interest.advisor_refresh",
        )
    except Exception as e:
        logger.warning(f"advisor cache write failed (recommendation kept): {e}")


async def get_recommendations(force: bool = False) -> dict[str, Any]:
    """读缓存或刷新; 任何失败都返回 {recommended, reasons, cached_at, note}。"""
    from backend.services.ai_hub.prompts import build_interest_advisor_prompt
    from backend.services.auto_classifier import PRACTICE_DOMAIN_LABELS

    cached = _read_cache()
    if cached is not None and not force and not _cache_expired(cached):
        return {
            "recommended": cached["recommended"],
            "reasons": cached.get("reasons", {}),
            "cached_at": cached.get("cached_at"),
            "note": "",
        }

    note = ""
    try:
        prompt = build_interest_advisor_prompt(**build_recommendation_input())
        raw = await _ai_hub_mod.llm_service.generate(
            prompt,
            task=ADVISOR_TASK,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
        )
        parsed = _parse_reply(raw)
        # 域枚举校验: ∉PRACTICE_DOMAIN_LABELS 丢弃该项 (prompt 约束的双保险)
        valid = [
            d for d in parsed["recommended"] if d in PRACTICE_DOMAIN_LABELS
        ][:_MAX_RECOMMENDED]
        if not valid:
            raise ValueError("no recommendation survived domain enum check")
        payload = {
            "recommended": valid,
            "reasons": {d: parsed["reasons"][d] for d in valid if d in parsed["reasons"]},
            "cached_at": _now_iso(),
        }
        _write_cache(payload)
        return {
            "recommended": payload["recommended"],
            "reasons": payload["reasons"],
            "cached_at": payload["cached_at"],
            "note": "",
        }
    except Exception as e:
        logger.warning(f"interest advisor refresh failed: {e}")
        note = f"advisor refresh failed: {e}"

    if cached is not None:
        return {
            "recommended": cached["recommended"],
            "reasons": cached.get("reasons", {}),
            "cached_at": cached.get("cached_at"),
            "note": note,
        }
    return {"recommended": [], "reasons": {}, "cached_at": None, "note": note}


__all__ = ["ADVISOR_TASK", "build_recommendation_input", "get_recommendations"]
