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


__all__ = ["match_rules"]
