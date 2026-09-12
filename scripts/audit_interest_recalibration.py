#!/usr/bin/env python3
"""audit_interest_recalibration — 兴趣引擎权重重校判定 (审计类, DB 只读).

Interest DEV_PLAN「两周后重校判据」脚本化 (POST_R2 设计包 T3):
真实信号 ≥100 条或上线满 14 天后, 与周审计同周期执行, 产出是否调整
SIGNAL_WEIGHTS / EVIDENCE_C 的建议。

判定规则 (实现在 interest_engine_service.evaluate_recalibration_rules, 可单测):
  R1 deep_read 锚偏移   favorite:deep_read 实际条数比偏离校准锚 (9:14) >30%
  R2 view 灌水降权      view 占比 >60% 且独立条目/信号 <50%
  R3 收敛进度           满 14 天 W30<10 → 建议 C=30→15 (加速 β 收敛)

用法:
  python scripts/audit_interest_recalibration.py            # 人类可读
  python scripts/audit_interest_recalibration.py --json     # 机读

只读约束: 零 SQL (SQL 集中 hotspot_repo.interest_* 只读函数); 常数改动
由 owner 裁决后手改 interest_engine_service.py 并走 commit — 本脚本绝不写。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.hotspot_repo import (  # noqa: E402
    interest_audit_w30_weight_sum,
    interest_signals_since,
)
from backend.services.interest_engine_service import (  # noqa: E402
    SIGNAL_WEIGHTS,
    evaluate_recalibration_rules,
)


def _iso_cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta_days(days)).isoformat()


def timedelta_days(days: int):
    from datetime import timedelta

    return timedelta(days=days)


def collect() -> dict:
    signals = interest_signals_since(_iso_cutoff(90))
    counts: Counter = Counter(s["signal_type"] for s in signals)
    distinct: dict[str, set] = {}
    earliest = None
    for s in signals:
        distinct.setdefault(s["signal_type"], set()).add(s["item_id"])
        if earliest is None or s["created_at"] < earliest:
            earliest = s["created_at"]
    days_observed = 0.0
    if earliest:
        try:
            days_observed = max(
                0.0,
                (datetime.now(timezone.utc) - datetime.fromisoformat(earliest)).total_seconds() / 86400.0,
            )
        except ValueError:
            pass
    w30 = interest_audit_w30_weight_sum(_iso_cutoff(30))
    suggestions = evaluate_recalibration_rules(
        dict(counts), {k: len(v) for k, v in distinct.items()}, w30, days_observed,
    )
    return {
        "signals_total": len(signals),
        "days_observed": round(days_observed, 1),
        "counts_by_type": dict(counts),
        "distinct_by_type": {k: len(v) for k, v in distinct.items()},
        "w30": round(w30, 2),
        "current_weights": dict(SIGNAL_WEIGHTS),
        "suggestions": suggestions,
    }


def _render(report: dict) -> int:
    print("== Interest Engine 权重重校判定 ==")
    print(
        f"  信号总量 {report['signals_total']} 条 / 观测 {report['days_observed']} 天 / "
        f"W30={report['w30']}"
    )
    print(f"  按 type: {report['counts_by_type']}")
    print(f"  独立条目: {report['distinct_by_type']}")
    if not report["suggestions"]:
        print("  结论: 不满足任何重校条件 — 常数维持不变")
        return 0
    print("  建议 (owner 裁决后手改 interest_engine_service.py 并 commit):")
    for s in report["suggestions"]:
        print(f"    [{s['rule']}] {s['current']} → {s['proposed']}")
        print(f"      依据: {s['reason']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="兴趣引擎权重重校判定 (DB 只读)")
    parser.add_argument("--json", action="store_true", help="机读输出")
    args = parser.parse_args()
    report = collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        return _render(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
