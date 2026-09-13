#!/usr/bin/env python3
"""agent_D_selfcheck.py — MP-2 evt_data_breach 候选质量自审替身.

用法
----
    cd /path/to/hotspot-mp2-agent-D && .venv/bin/python scripts/agent_D_selfcheck.py

自审维度 (plan §4 Step 4)
----
1. 语料量: agent-D 类报告 ≥3 份 (备降级线 ≥1)
2. 候选量: ≥6 条 pending 候选
3. evidence_quote 逐字子串回验 (独立于抽取路径重算)
4. FK 回验 (technique_id ∈ attack_techniques)
5. confidence 分布 + stage 覆盖 (低覆盖 <3 tactic 触发 WARN, 不阻断)
6. source_url 真实性格式 (http/https)
7. owner_status 全 pending (本 agent 不越权直接写 map)

exit 0 = 全部硬指标通过; exit 1 = 任一硬指标失败
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.repository.db import apply_migrations, get_connection  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)

AGENT_OWNER = "D"
EVENT_TYPE_ID = "evt_data_breach"

failures: list[str] = []
warnings: list[str] = []


def check(name: str, ok: bool, detail: str, *, hard: bool = True) -> None:
    mark = "PASS" if ok else ("FAIL" if hard else "WARN")
    print(f"  [{mark}] {name}: {detail}")
    if not ok:
        (failures if hard else warnings).append(f"{name}: {detail}")


def main() -> int:
    apply_migrations(get_connection())
    conn = get_connection()
    svc = EventTechniqueExtractService()

    print(f"[agent-D selfcheck] event_type={EVENT_TYPE_ID}")

    # 1. 语料量
    reports = conn.execute(
        "SELECT id, source_url, industry FROM incident_reports WHERE agent_owner = ?",
        (AGENT_OWNER,),
    ).fetchall()
    check("report_count>=3", len(reports) >= 3, f"{len(reports)} reports")

    # 2. 候选量
    cands = conn.execute(
        "SELECT * FROM event_technique_candidates WHERE agent_owner = ?",
        (AGENT_OWNER,),
    ).fetchall()
    cands = [dict(c) for c in cands]
    check("candidates>=6", len(cands) >= 6, f"{len(cands)} candidates")

    # 3+4. quote/FK 逐条回验
    report_map = {r["id"]: dict(r) for r in reports}
    tech_ids = {
        row["id"]
        for row in conn.execute("SELECT id FROM attack_techniques").fetchall()
    }
    quote_ok = fk_ok = 0
    for c in cands:
        rep = report_map.get(c["source_report_id"])
        if rep and c["evidence_quote"] in rep_source_md(conn, c["source_report_id"]):
            quote_ok += 1
        if c["technique_id"] in tech_ids:
            fk_ok += 1
    check("evidence_quote substring", quote_ok == len(cands), f"{quote_ok}/{len(cands)} pass")
    check("technique FK", fk_ok == len(cands), f"{fk_ok}/{len(cands)} pass")

    # 5. 覆盖率/置信度 (soft)
    cov = svc.coverage_report(AGENT_OWNER)
    check(
        "stage coverage>=3 (soft)",
        len(cov["by_stage"]) >= 3,
        f"{len(cov['by_stage'])} tactics: {sorted(cov['by_stage'])}",
        hard=False,
    )
    check(
        "mean confidence>=0.7 (soft)",
        cov["mean_confidence"] >= 0.7,
        f"mean={cov['mean_confidence']}",
        hard=False,
    )
    check(
        "unique techniques>=5 (soft)",
        cov["unique_techniques"] >= 5,
        f"{cov['unique_techniques']} unique techniques",
        hard=False,
    )

    # 6. source_url 格式
    urls_ok = all(str(r["source_url"]).startswith(("http://", "https://")) for r in reports)
    check("source_url http(s)", urls_ok, f"{sum(1 for r in reports if str(r['source_url']).startswith('http'))}/{len(reports)}")

    # 7. 全 pending (未越权写 map)
    non_pending = [c for c in cands if c["owner_status"] != "pending"]
    map_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM event_technique_map WHERE event_type_id = ?",
        (EVENT_TYPE_ID,),
    ).fetchone()["n"]
    check("all pending (no map bypass)", not non_pending and map_rows == 0,
          f"non_pending={len(non_pending)} map_rows={map_rows}")

    print(f"\n[agent-D selfcheck] result: {'PASS' if not failures else 'FAIL'} "
          f"(hard failures={len(failures)}, warnings={len(warnings)})")
    return 0 if not failures else 1


def rep_source_md(conn, report_id: str) -> str:
    row = conn.execute(
        "SELECT report_md FROM incident_reports WHERE id = ?", (report_id,)
    ).fetchone()
    return row["report_md"] if row else ""


if __name__ == "__main__":
    raise SystemExit(main())
