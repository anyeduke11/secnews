#!/usr/bin/env python3
"""agent_E_selfcheck.py — MP-2 agent-E 候选质量自审替身.

MP-2 方案 docs/PLAN_MP2_EVENT_TYPE_2026-09-13.md §4 Step 4 (agent-E 范围).

质量报告维度 (任务书 B.2):
  - 覆盖率: 候选覆盖几个 stage (监管通报类预期以 regulatory_notice 为主, ≥2 个 stage)
  - 置信度分布: 全部落在 [0.5, 1.0), 监管类预期 0.6~0.9
  - evidence_quote 通过率: 逐条重放 substring 校验 (含 NFC 归一化), 必须 100%
  - regulatory_only 占比: 监管通报类预期 ≥80%

退出码: 0 = 全部通过; 1 = 存在 FAIL 项 (CI/抽审可用)。

用法::

    .venv/bin/python scripts/agent_E_selfcheck.py          # 人类可读报告
    .venv/bin/python scripts/agent_E_selfcheck.py --json   # JSON 输出
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.db import get_connection, init_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MP-2 agent-E 候选质量自审")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    init_db()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT c.id, c.technique_id, c.stage, c.confidence, c.evidence_quote,
               c.regulatory_only, c.source_report_id, c.auto_reject_reason,
               r.report_md, r.source_url
        FROM event_technique_candidates c
        JOIN incident_reports r ON r.id = c.source_report_id
        WHERE c.event_type_id = 'evt_regulatory_notice'
        ORDER BY c.created_at ASC
        """
    ).fetchall()
    candidates = [dict(r) for r in rows]

    if not candidates:
        print("[FAIL] no candidates for evt_regulatory_notice — run agent_E_extract.py first")
        return 1

    # 1. evidence_quote 通过率 (重放 substring 校验, NFC 归一化)
    quote_pass = 0
    quote_failures: list[str] = []
    for c in candidates:
        normalized_quote = unicodedata.normalize("NFC", c["evidence_quote"])
        normalized_md = unicodedata.normalize("NFC", c["report_md"])
        if normalized_quote in normalized_md:
            quote_pass += 1
        else:
            quote_failures.append(c["id"])

    # 2. 置信度分布
    confidences = [float(c["confidence"]) for c in candidates]
    out_of_range = [c["id"] for c in candidates if not (0.5 <= float(c["confidence"]) < 1.0)]
    in_regulatory_band = [v for v in confidences if 0.6 <= v <= 0.9]

    # 3. stage 覆盖 + regulatory_only 占比
    stages = sorted({c["stage"] for c in candidates})
    n_regulatory_only = sum(1 for c in candidates if c["technique_id"] is None)

    report = {
        "event_type_id": "evt_regulatory_notice",
        "total_candidates": len(candidates),
        "evidence_quote_pass": quote_pass,
        "evidence_quote_fail": len(quote_failures),
        "evidence_quote_pass_rate": round(quote_pass / len(candidates), 3),
        "confidence_min": min(confidences),
        "confidence_max": max(confidences),
        "confidence_in_060_090_band": len(in_regulatory_band),
        "confidence_out_of_range": len(out_of_range),
        "stage_coverage": stages,
        "n_distinct_stages": len(stages),
        "regulatory_only": n_regulatory_only,
        "regulatory_only_ratio": round(n_regulatory_only / len(candidates), 3),
        "source_reports": len({c["source_report_id"] for c in candidates}),
    }

    checks = [
        ("evidence_quote_pass_rate=1.0", report["evidence_quote_fail"] == 0),
        ("confidence all in [0.5,1.0)", report["confidence_out_of_range"] == 0),
        ("stage coverage >= 2", report["n_distinct_stages"] >= 2),
        ("regulatory_only >= 80%", report["regulatory_only_ratio"] >= 0.8),
        (">= 5 source reports", report["source_reports"] >= 5),
    ]

    if args.json:
        print(json.dumps({**report, "checks": {name: ok for name, ok in checks}}, ensure_ascii=False, indent=2))
    else:
        print(f"== agent-E selfcheck: evt_regulatory_notice ==")
        for k, v in report.items():
            print(f"  {k}: {v}")
        print("-- checks --")
        for name, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    if not all(ok for _, ok in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
