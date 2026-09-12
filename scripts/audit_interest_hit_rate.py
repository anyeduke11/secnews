#!/usr/bin/env python3
"""audit_interest_hit_rate — 兴趣引擎周审计·命中率代理指标 (审计类, DB 只读).

Interest PRD R2 (docs/INTEREST_ENGINE_PRD_v1.0.md §6): 周审计附命中率代理
指标, 与词表周审计 (check_practice_domain_lexicon.py) 同周期执行。

产出的代理指标 (真值 = 用户主观相关性, 不可直接测, 故为代理):
  1. 信号健康   近 7/30/90d 信号量、按 type / domain 分布、去重后独立条目数
  2. 收敛进度   W30 (30d 信号权重和) 相对 C=30 的 β 饱和度 (DEV_PLAN 两周重校判据)
  3. 漂移状态   行为 top3 vs 显式勾选重合 <2 (复算 PRD §6 口径, 不写库)
  4. Feed 覆盖  近 N 条资讯中落进增强域 (m>1.0) 的占比 — 引擎实际影响面的代理

用法:
  python scripts/audit_interest_hit_rate.py            # 人类可读报告
  python scripts/audit_interest_hit_rate.py --json     # 机读 (进 RUNBOOK 台账)
  python scripts/audit_interest_hit_rate.py --feed-n 200

只读约束: 本脚本零 SQL (SQL 集中在 hotspot_repo.interest_audit_* 只读函数,
新脚本文件含 SQL 会被安全扫描器整文件拦截, 见 DEV-0182/0183); 绝不调
InterestEngineService.aggregate() (它会 upsert interest_domain_weights)。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.hotspot_repo import (  # noqa: E402
    interest_audit_recent_titles,
    interest_audit_signal_stats,
    interest_audit_stored_weights,
    interest_audit_w30_weight_sum,
)

_INTEREST_KEY = "interest.practice_domains"
_FEED_N_CHOICES = (50, 100, 200, 500)


def _iso_cutoff(days: int) -> str:
    """Python 预计算 ISO cutoff (与 interest_signals 写入格式一致)。"""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _explicit_profile() -> list[str]:
    try:
        from backend.repository.settings_repo import SettingsRepository

        v = SettingsRepository().get(_INTEREST_KEY, [])
        return [d for d in v if isinstance(d, str)] if isinstance(v, list) else []
    except Exception:
        return []


def _drift(stored: dict, explicit: list[str]) -> dict:
    """复算 PRD §6 漂移口径: 行为 top3 与勾选重合 <2 → 提示 (绝不改画像)。

    与 service.detect_drift 同规则: 行为域不足 3 个不构成 top3, 不判。
    """
    behavioral = sorted(
        ((d, v["behavioral_score"]) for d, v in stored.items() if v["behavioral_score"] > 0),
        key=lambda p: p[1], reverse=True,
    )
    top = [d for d, _ in behavioral[:3]]
    overlap = len(set(top) & set(explicit))
    return {
        "behavioral_top3": top,
        "explicit_domains": sorted(explicit),
        "overlap": overlap,
        "detected": bool(explicit) and len(top) == 3 and overlap < 2,
    }


def _feed_boost_coverage(n: int) -> dict:
    """近 N 条资讯落进增强域 (m>1.0 ⟺ S(d)>0.5) 的占比 — 影响面代理。"""
    from backend.services.auto_classifier import classify_practice_domain

    stored = interest_audit_stored_weights()
    boosted = {d for d, v in stored.items() if v["blended_score"] > 0.5}
    titles = interest_audit_recent_titles(n)
    hit = 0
    attributed = 0
    for title in titles:
        d = classify_practice_domain([], title=title)
        if d is not None:
            attributed += 1
            if d in boosted:
                hit += 1
    total = len(titles)
    return {
        "sample": total,
        "attributed": attributed,
        "hit_boosted": hit,
        "hit_rate": round(hit / total, 4) if total else 0.0,
        "attribution_rate": round(attributed / total, 4) if total else 0.0,
        "boosted_domains": sorted(boosted),
    }


def collect(feed_n: int) -> dict:
    from backend.services.interest_engine_service import BETA_MAX, EVIDENCE_C

    w30 = interest_audit_w30_weight_sum(_iso_cutoff(30))
    return {
        "windows": [
            {"days": d, **interest_audit_signal_stats(_iso_cutoff(d))} for d in (7, 30, 90)
        ],
        "convergence": {
            "w30": round(w30, 2),
            "c_constant": EVIDENCE_C,
            "beta_max": BETA_MAX,
            "beta_eff": round(BETA_MAX * min(1.0, w30 / EVIDENCE_C), 4),
            "saturation": round(min(1.0, w30 / EVIDENCE_C), 4),
        },
        "drift": _drift(interest_audit_stored_weights(), _explicit_profile()),
        "feed_boost_coverage": _feed_boost_coverage(feed_n),
    }


def _render(report: dict) -> str:
    lines: list[str] = ["== Interest Engine 周审计·命中率代理 =="]
    for w in report["windows"]:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(w["by_type"].items())) or "-"
        lines.append(
            f"  {w['days']}d: 信号 {w['total']} 条 / 独立条目 {w['distinct_items']} "
            f"[{parts}]"
        )
    dom: Counter = Counter()
    for w in report["windows"]:
        if w["days"] == 30:
            dom = Counter(w["by_domain"])
    if dom:
        lines.append("  30d 按域: " + ", ".join(f"{d}×{c}" for d, c in dom.most_common()))
    cv = report["convergence"]
    lines.append(
        f"  收敛: W30={cv['w30']} / C={cv['c_constant']} → β_eff={cv['beta_eff']} "
        f"(饱和度 {cv['saturation']:.0%})"
    )
    dr = report["drift"]
    state = "⚠ 漂移" if dr["detected"] else "OK"
    lines.append(
        f"  漂移[{state}]: 行为top3={dr['behavioral_top3']} vs 勾选={dr['explicit_domains']} "
        f"(重合 {dr['overlap']})"
    )
    fb = report["feed_boost_coverage"]
    lines.append(
        f"  Feed 覆盖: 近 {fb['sample']} 条中 {fb['hit_boosted']} 条落增强域 "
        f"(命中率 {fb['hit_rate']:.1%}, 归因率 {fb['attribution_rate']:.1%}, "
        f"增强域={fb['boosted_domains']})"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="兴趣引擎周审计·命中率代理指标 (DB 只读)")
    parser.add_argument("--json", action="store_true", help="机读输出")
    parser.add_argument("--feed-n", type=int, choices=_FEED_N_CHOICES, default=200,
                        help="Feed 覆盖采样条数 (固定档位)")
    args = parser.parse_args()
    report = collect(args.feed_n)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
