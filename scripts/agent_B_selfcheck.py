#!/usr/bin/env python3
"""agent-B 自审替身 — 候选池质量报告 (plan §4 Step 4).

对 3 个 B 类 event_type 各生成:
  - 候选覆盖率 (命中 ATT&CK tactic 数, 经 attack_techniques JOIN)
  - 置信度分布 (min/mean/max)
  - evidence_quote 子串通过率 (程序化复检)
  - 追溯链完整性 (candidate → report → source_url)

退出码: 任一类 quote 通过率 <100% 或 候选数 <6 → 1 (触发补抽), 否则 0。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.repository.db import close_db, get_connection, init_db  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)

AGENT_OWNER = "B"
EVENT_TYPES = ["evt_insider_threat", "evt_cloud_misconfig", "evt_ai_model_poison"]
MIN_CANDIDATES_PER_TYPE = 6


def main() -> int:
    init_db()
    conn = get_connection()
    extract_svc = EventTechniqueExtractService()

    overall_ok = True
    print("==== agent-B selfcheck ====")
    for event_type_id in EVENT_TYPES:
        rows = conn.execute(
            """
            SELECT c.id, c.technique_id, c.stage, c.confidence, c.evidence_quote,
                   c.auto_reject_reason, c.source_report_id, t.tactic,
                   r.source_url, r.report_md
            FROM event_technique_candidates c
            JOIN incident_reports r ON r.id = c.source_report_id
            LEFT JOIN attack_techniques t ON t.id = c.technique_id
            WHERE c.event_type_id = ?
            """,
            (event_type_id,),
        ).fetchall()

        total = len(rows)
        valid = [r for r in rows if not r["auto_reject_reason"]]
        tactics = sorted({r["tactic"] for r in valid if r["tactic"]})
        quotes_pass = sum(1 for r in valid if r["evidence_quote"] in (r["report_md"] or ""))
        trace_pass = sum(1 for r in valid if r["source_url"])
        confs = [r["confidence"] for r in valid] or [0.0]

        ok = (
            total >= MIN_CANDIDATES_PER_TYPE
            and quotes_pass == len(valid)
            and trace_pass == len(valid)
            and len(valid) > 0
        )
        overall_ok = overall_ok and ok
        print(f"\n[{event_type_id}]")
        print(f"  candidates: {total} (valid={len(valid)}, auto_rejected={total - len(valid)})")
        print(f"  tactic_coverage: {len(tactics)} {tactics}")
        print(f"  confidence: min={min(confs):.2f} mean={sum(confs) / len(confs):.2f} max={max(confs):.2f}")
        print(f"  quote_pass_rate: {quotes_pass}/{len(valid)}")
        print(f"  trace_chain_pass: {trace_pass}/{len(valid)}")
        print(f"  verdict: {'PASS' if ok else 'FAIL (触发补抽)'}")

    print("\n==== pool totals ====")
    print(extract_svc.stats())
    close_db()
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
