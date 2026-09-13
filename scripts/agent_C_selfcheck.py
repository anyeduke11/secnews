#!/usr/bin/env python3
"""agent-C 自审替身 — evt_fraud 候选质量报告.

按 PLAN_MP2_EVENT_TYPE_2026-09-13.md §4 Step 4 输出:
  - 覆盖率 (覆盖 ATT&CK tactic / stage 数)
  - 置信度分布 (min/mean/max, 0.5~0.8 区间占比)
  - evidence_quote 通过率 (重新逐条 substring 复验)
  - social_engineering_only 占比 (反诈特性)

用法: .venv/bin/python scripts/agent_C_selfcheck.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.repository.db import apply_migrations, get_connection  # noqa: E402
from backend.services.attack_loader import load_attack_data  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)

EXPECTED_MIN_CANDIDATES = 10
EXPECTED_MIN_REPORTS = 5
EXPECTED_MIN_STAGES = 4


def main() -> int:
    conn = get_connection()
    apply_migrations(conn)
    load_attack_data()

    n_reports = conn.execute("SELECT COUNT(*) AS n FROM incident_reports").fetchone()["n"]
    rows = conn.execute(
        "SELECT c.*, r.report_md FROM event_technique_candidates c "
        "JOIN incident_reports r ON r.id = c.source_report_id "
        "WHERE c.event_type_id = 'evt_fraud'"
    ).fetchall()

    ext = EventTechniqueExtractService()
    stages = sorted({r["stage"] for r in rows})
    tech_rows = [r for r in rows if r["technique_id"]]
    seo_rows = [r for r in rows if not r["technique_id"]]
    confs = [r["confidence"] for r in rows]
    quote_pass = sum(1 for r in rows if ext._quote_in_report(r["evidence_quote"], r["report_md"]))
    fk_pass = sum(1 for r in tech_rows if ext._fk_exists(r["technique_id"]))
    conf_in_range = sum(1 for c in confs if 0.5 <= c <= 0.8)
    auto_rejected = conn.execute(
        "SELECT COUNT(*) AS n FROM event_technique_candidates WHERE auto_reject_reason IS NOT NULL"
    ).fetchone()["n"]

    report = {
        "event_type": "evt_fraud",
        "reports": n_reports,
        "candidates": len(rows),
        "stages_covered": stages,
        "stage_count": len(stages),
        "technique_mapped": len(tech_rows),
        "social_engineering_only": len(seo_rows),
        "seo_ratio": round(len(seo_rows) / len(rows), 2) if rows else 0.0,
        "confidence": {
            "min": min(confs) if confs else None,
            "mean": round(sum(confs) / len(confs), 3) if confs else None,
            "max": max(confs) if confs else None,
            "in_050_080_range": conf_in_range,
        },
        "evidence_quote_pass_rate": round(quote_pass / len(rows), 3) if rows else 0.0,
        "technique_fk_pass_rate": round(fk_pass / len(tech_rows), 3) if tech_rows else None,
        "auto_reject_rows": auto_rejected,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 自审门槛 (反诈: 报告 ≥5 / 候选 ≥10 / stage ≥4 / quote 通过率 =1.0 / FK 通过率 =1.0)
    failures = []
    if n_reports < EXPECTED_MIN_REPORTS:
        failures.append(f"reports {n_reports} < {EXPECTED_MIN_REPORTS}")
    if len(rows) < EXPECTED_MIN_CANDIDATES:
        failures.append(f"candidates {len(rows)} < {EXPECTED_MIN_CANDIDATES}")
    if len(stages) < EXPECTED_MIN_STAGES:
        failures.append(f"stages {len(stages)} < {EXPECTED_MIN_STAGES}")
    if rows and quote_pass != len(rows):
        failures.append(f"evidence_quote pass {quote_pass}/{len(rows)}")
    if tech_rows and fk_pass != len(tech_rows):
        failures.append(f"technique FK pass {fk_pass}/{len(tech_rows)}")
    if not seo_rows:
        failures.append("no social_engineering_only rows (反诈语料应存在社工链路候选)")

    if failures:
        print("SELF-CHECK FAIL:", "; ".join(failures), file=sys.stderr)
        return 1
    print("SELF-CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
