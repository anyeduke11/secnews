#!/usr/bin/env python
"""MP-2 agent-A 自审脚本 — owner 替身辅助统计 (不是真审).

用法
----
    .venv/bin/python scripts/agent_A_selfcheck.py [--suggest-threshold 0.7]

输出
----
1. 每类事件类型的候选统计: 数量 / 置信度分布 / stage 覆盖 / technique 覆盖
2. 全量守卫复核: FK / evidence_quote substring / confidence 阈值 (独立于 pytest 再跑一遍)
3. "建议批准"清单: confidence >= threshold 的 pending candidates (owner 人审参考)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.logging_config import setup as setup_logging  # noqa: E402
from backend.repository.db import get_connection, init_db  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    _normalize_text,
)

AGENT_OWNER = "A"
EVENT_TYPES = [
    "evt_ransomware", "evt_phishing_social", "evt_web_app_intrusion",
    "evt_supply_chain", "evt_brute_force",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suggest-threshold", type=float, default=0.7)
    args = parser.parse_args()
    setup_logging("ERROR")

    init_db()
    conn = get_connection()

    valid_tids = {str(r["id"]) for r in conn.execute("SELECT id FROM attack_techniques").fetchall()}
    reports = {
        str(r["id"]): dict(r)
        for r in conn.execute("SELECT id, report_md, source_url FROM incident_reports").fetchall()
    }

    total_candidates = 0
    guard_failures: list[str] = []
    suggest_lists: dict[str, list[dict]] = {}

    print("=" * 72)
    print(f"agent-{AGENT_OWNER} 自审报告 (owner 替身辅助, 非真审)")
    print(f"建议批准阈值: confidence >= {args.suggest_threshold}")
    print("=" * 72)

    for et_id in EVENT_TYPES:
        rows = conn.execute(
            "SELECT * FROM event_technique_candidates WHERE event_type_id = ? AND agent_owner = ?",
            (et_id, AGENT_OWNER),
        ).fetchall()
        rows = [dict(r) for r in rows]
        total_candidates += len(rows)
        print(f"\n## {et_id} — {len(rows)} candidates")

        if not rows:
            print("  (无候选 — 需补抽)")
            continue

        # 统计
        confs = [r["confidence"] for r in rows]
        stages = Counter(r["stage"] for r in rows)
        tids = Counter(r["technique_id"] for r in rows)
        quote_pass = 0
        for r in rows:
            md = reports.get(r["source_report_id"], {}).get("report_md", "")
            if _normalize_text(r["evidence_quote"]) in _normalize_text(md):
                quote_pass += 1
            else:
                guard_failures.append(f"{et_id}/{r['id']}: quote_not_found")
            if r["technique_id"] not in valid_tids:
                guard_failures.append(f"{et_id}/{r['id']}: fk_invalid {r['technique_id']}")
            if r["confidence"] < CONFIDENCE_THRESHOLD:
                guard_failures.append(f"{et_id}/{r['id']}: conf_below_threshold")

        print(f"  confidence: min={min(confs):.2f} avg={sum(confs)/len(confs):.2f} max={max(confs):.2f}")
        print(f"  stage 覆盖 ({len(stages)}): {dict(stages)}")
        print(f"  technique 覆盖: {len(tids)} 个唯一 T-id → {sorted(tids)}")
        print(f"  evidence_quote 通过率: {quote_pass}/{len(rows)}")

        # 建议批准清单
        suggested = [r for r in rows if r["confidence"] >= args.suggest_threshold]
        suggest_lists[et_id] = [
            {
                "id": r["id"],
                "technique_id": r["technique_id"],
                "stage": r["stage"],
                "confidence": r["confidence"],
                "evidence_quote": r["evidence_quote"][:60],
            }
            for r in sorted(suggested, key=lambda x: -x["confidence"])
        ]
        print(f"  建议批准 (>= {args.suggest_threshold}): {len(suggested)} 条")

    # 汇总
    print("\n" + "=" * 72)
    print(f"TOTAL candidates: {total_candidates}")
    print(f"守卫复核失败: {len(guard_failures)}")
    for f in guard_failures[:10]:
        print(f"  ! {f}")

    # 建议批准清单 JSON (给 owner / 前端消费)
    out_path = REPO_ROOT / "data" / "security" / "incidents" / "agent_A" / "_selfcheck_suggest.json"
    out_path.write_text(
        json.dumps({"threshold": args.suggest_threshold, "suggest": suggest_lists}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    suggested_total = sum(len(v) for v in suggest_lists.values())
    print(f"\n建议批准清单 ({suggested_total} 条) → {out_path}")
    print("提醒: 自审不等于真审 — 最终以 owner 人审为准 (DISCUSSION §7.3)")
    return 1 if guard_failures else 0


if __name__ == "__main__":
    sys.exit(main())
