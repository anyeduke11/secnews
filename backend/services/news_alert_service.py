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


def _load_rule_config() -> dict[str, RuleConfig]:
    """从 alert_rule_definitions 读 4 规则 config JSON (enabled=1)。"""
    import json as _json

    from backend.repository.db import get_connection

    rows = get_connection().execute(
        "SELECT rule_type, config FROM alert_rule_definitions "
        "WHERE enabled = 1 AND rule_type IN "
        "('critical_vuln','major_security_event',"
        "'major_ai_security_event','must_know_regulatory')"
    ).fetchall()
    out: dict[str, RuleConfig] = {}
    for r in rows:
        try:
            cfg = _json.loads(r["config"]) if r["config"] else {}
        except Exception:
            cfg = {}
        out[r["rule_type"]] = cfg
    return out


def run_news_alert_review(lookback_hours: int = 40) -> dict[str, int]:
    """采集尾部入口 (spec §2.1 漏斗编排)。全程不抛 — 调用方 (_tick) 再兜一层。

    Returns: {"candidates": 词表筛候选数, "alerted": 实际落 alert_events 数}
    """
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=lookback_hours)).isoformat()
    rows = get_connection().execute(
        "SELECT id, title, COALESCE(summary,'') summary, quality_score, source,"
        " url FROM hotspots "
        "WHERE fetched_at >= ? AND category IN ('security','ai_security','ai') "
        "ORDER BY fetched_at DESC LIMIT 500",
        (cutoff,),
    ).fetchall()

    config = _load_rule_config()
    if not config:
        return {"candidates": 0, "alerted": 0}

    # 词表筛
    candidates: list[dict[str, Any]] = []
    seen_hotspots: set[str] = set()
    for r in rows:
        item = dict(r)
        if item["id"] in seen_hotspots:
            continue
        # 去重闸: 该 hotspot 已告警过 → 跳过
        dup = get_connection().execute(
            "SELECT 1 FROM alert_events WHERE item_id = ? LIMIT 1",
            (item["id"],),
        ).fetchone()
        if dup:
            continue
        hits = match_rules(
            item["title"], item["summary"],
            float(item["quality_score"] or 0), config,
        )
        for h in hits:
            candidates.append({
                "id": item["id"], "rule": h["rule"], "signals": h["signals"],
                "strength": h["strength"], "title": item["title"],
                "summary": item["summary"], "source": item["source"],
                "url": item["url"], "quality_score": item["quality_score"],
            })
    seen_hotspots = {c["id"] for c in candidates}

    confirmed = review_candidates(candidates)
    alerted = 0
    per_rule: dict[str, int] = {}
    for c in confirmed:
        cap = int(config.get(c["rule"], {}).get("max_per_run", 5))
        if per_rule.get(c["rule"], 0) >= cap:
            continue
        per_rule[c["rule"]] = per_rule.get(c["rule"], 0) + 1

        from backend.services.alert_engine import AlertEngine

        engine = AlertEngine()
        sev = "critical" if c["rule"] == "critical_vuln" else (
            "medium" if c["rule"] == "must_know_regulatory" else "high"
        )
        item_row = next(x for x in candidates if x["id"] == c["id"])
        new_id = engine._trigger_alert(
            rule_type=c["rule"],
            title=item_row["title"][:200],
            description=(
                f"{c['reason']} | {item_row['summary'][:200]}"
            ),
            severity=sev,
            source=item_row["source"],
            source_url=item_row["url"],
            item_id=c["id"],
        )
        if new_id:
            alerted += 1

    if alerted:
        _publish_news_alert_sse(alerted)
    return {"candidates": len(candidates), "alerted": alerted}


def _publish_news_alert_sse(alerted: int) -> None:
    """SSE news_alert 事件 (与 publish_collect_done 同款: spawn 协程而非阻塞)。"""
    try:
        import asyncio

        from backend.core.events import publish_event
        import backend.services.collection_pipeline as _cp

        _cp._spawn(asyncio.ensure_future(
            publish_event("news_alert", {"count": alerted})
        ))
    except Exception:
        pass  # SSE 失败不影响告警落库


__all__ = ["match_rules"]
