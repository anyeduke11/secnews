"""资讯告警判定服务 (2026-09-27 四模式重定义 P1, spec §2)。

判定漏斗: 词表筛 (本模块 match_rules) → 去重闸 → pi LLM 复核
(review_candidates) → alert_events 落库 (run_news_alert_review)。
词表/阈值从 alert_rule_definitions.config JSON 读, 可经 settings API 调。
"""
from __future__ import annotations

from typing import Any

RuleConfig = dict[str, Any]


def match_rules(
    title: str,
    summary: str,
    quality_score: float,
    config: dict[str, RuleConfig],
) -> list[dict[str, Any]]:
    """对单条资讯跑 4 规则词表筛, 返回命中规则列表。

    每个命中项: {"rule": rule_type, "signals": [命中词], "strength": 命中数}
    - R1/R4: 任一强信号命中即候选
    - R2: ≥min_signals_alone(默认2) 个信号, 或 1 信号 + quality_score ≥ quality_score_gate
    - R3: 安全词命中 **且** title+summary 含 AI 语境词 (双通道限定)
    """
    text = f"{title} {summary}"
    hits: list[dict[str, Any]] = []

    for rule_type, cfg in config.items():
        keywords = cfg.get("keywords", [])
        signals = [kw for kw in keywords if kw in text]
        if not signals:
            continue

        if rule_type == "major_security_event":
            min_alone = int(cfg.get("min_signals_alone", 2))
            gate = float(cfg.get("quality_score_gate", 75))
            if len(signals) < min_alone and quality_score < gate:
                continue
        elif rule_type == "major_ai_security_event":
            context_words = cfg.get("ai_context_words", [])
            if not any(w in text for w in context_words):
                continue

        hits.append(
            {"rule": rule_type, "signals": signals, "strength": len(signals)}
        )
    return hits


def _parse_review_json(raw: str) -> list[dict] | None:
    """容错解析复核 JSON 数组; 失败返回 None (调用方 fail-open)。"""
    import json as _json
    import re as _re
    try:
        m = _re.search(r"\[.*\]", raw or "", _re.DOTALL)
        if not m:
            return None
        data = _json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except Exception:
        return None


def review_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """pi 复核候选 (spec §2.3): 合并单次调用, execute=true 才告警。

    fail-open: LLM 失败/解析失败 → strength ≥2 (≥2 个词表信号) 的候选
    直接放行, 单信号丢弃 — 宁多报不漏报。
    返回: 确认告警列表 [{id, rule, signals, reason}]。
    """
    if not candidates:
        return []
    import asyncio

    def _call_llm() -> str:
        from backend.services.ai_hub.gateway import llm_service
        from backend.services.ai_hub.prompts import (
            build_news_alert_review_prompt,
        )

        return asyncio.run(llm_service.generate(
            build_news_alert_review_prompt(candidates),
            task="news_alert_review",
        ))

    try:
        raw = _call_llm()
    except Exception:
        raw = None
    confirmed: list[dict[str, Any]] = []
    parsed = _parse_review_json(raw if isinstance(raw, str) else "")
    if parsed is None:
        # fail-open (strength ≡ len(signals), match_rules 产出定义)
        for c in candidates:
            if len(c["signals"]) >= 2:
                confirmed.append({
                    "id": c["id"], "rule": c["rule"],
                    "signals": c["signals"],
                    "reason": f"llm_fail_open: {len(c['signals'])} 强信号",
                })
        return confirmed
    by_id = {str(v.get("id")): v for v in parsed if isinstance(v, dict)}
    for c in candidates:
        v = by_id.get(str(c["id"]))
        if v and v.get("execute"):
            confirmed.append({
                "id": c["id"], "rule": c["rule"], "signals": c["signals"],
                "reason": str(v.get("reason", ""))[:200],
            })
    return confirmed


__all__ = ["match_rules"]
