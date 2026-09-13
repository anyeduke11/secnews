#!/usr/bin/env python
"""MP-2 agent-A 抽取脚本 — 对 5 类通用高优事件类型跑 LLM 抽取 + 候选落库.

用法
----
    cd <repo root>
    .venv/bin/python scripts/agent_A_extract.py [--dry-run]

流程
----
1. 初始化 DB (apply_migrations, 幂等)
2. ensure attack_techniques 有数据 (attack_loader.load_attack_data)
3. 对 5 类事件类型逐类:
   a. bulk_ingest_from_dir(data/security/incidents/agent_A/<event_type>/)
   b. 逐 report 调 EventTechniqueExtractService.extract_for_report
      (ai_hub 不可用时自动降级 mock-extract-v1)
4. 打印统计: 每类 reports / extracted / inserted / rejected

只写 event_technique_candidates (owner_status='pending'), 不写 event_technique_map
(owner 人审是必经步骤 — DISCUSSION §7.3)。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.logging_config import setup as setup_logging  # noqa: E402
from backend.repository.db import init_db  # noqa: E402
from backend.repository.event_technique_repo import (  # noqa: E402
    EventTechniqueCandidateRepo,
    EventTypeRepo,
)
from backend.services.attack_loader import load_attack_data  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    MOCK_LLM_MODEL,
    EventTechniqueExtractService,
)
from backend.services.incident_report_service import IncidentReportService  # noqa: E402

AGENT_OWNER = "A"
EVENT_TYPES = [
    "evt_ransomware",
    "evt_phishing_social",
    "evt_web_app_intrusion",
    "evt_supply_chain",
    "evt_brute_force",
]
CORPUS_DIR = REPO_ROOT / "data" / "security" / "incidents" / "agent_A"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计不落库")
    parser.add_argument(
        "--llm-model", default=MOCK_LLM_MODEL,
        help="LLM 模型标识 (默认 mock-extract-v1; ai_hub 配置好可切真实模型)",
    )
    args = parser.parse_args()

    setup_logging("INFO" if not args.dry_run else "WARNING")

    # 1. DB init (migration 117 幂等应用)
    init_db()

    # 2. attack_techniques FK 目标就位
    loaded = load_attack_data()
    print(f"attack_techniques loaded: {loaded['techniques']} techniques")

    svc = EventTechniqueExtractService()
    report_svc = IncidentReportService()
    et_repo = EventTypeRepo()
    cand_repo = EventTechniqueCandidateRepo()

    available_types = {t["id"] for t in et_repo.list_all(agent_owner=AGENT_OWNER)}
    print(f"event_types seeded by agent-{AGENT_OWNER}: {sorted(available_types)}")

    grand = {"reports": 0, "extracted": 0, "inserted": 0, "rejected": 0}
    for et_id in EVENT_TYPES:
        if et_id not in available_types:
            print(f"[SKIP] {et_id} not seeded (期望由 agent-{AGENT_OWNER} seed)")
            continue
        et_dir = CORPUS_DIR / et_id
        if not et_dir.exists():
            print(f"[SKIP] {et_id}: corpus dir missing {et_dir}")
            continue

        # a. 语料入库 (幂等, source_url UNIQUE)
        ingest = report_svc.bulk_ingest_from_dir(et_dir, et_id, agent_owner=AGENT_OWNER)
        reports = report_svc.list_reports_by_event_type(et_id, limit=50)
        print(f"\n== {et_id}: corpus files={ingest['total']} ingested={ingest['ingested']} "
              f"skipped={ingest['skipped_existing']} errors={len(ingest['errors'])}")

        if args.dry_run:
            grand["reports"] += len(reports)
            continue

        # b. 抽取 + 校验 + 落候选池
        ins = rej = ext = 0
        for r in reports:
            result = asyncio.run(svc.extract_for_report(
                report_id=r["id"],
                event_type_id=et_id,
                llm_model=args.llm_model,
                agent_owner=AGENT_OWNER,
            ))
            ext += result["candidates_extracted"]
            ins += result["candidates_inserted"]
            rej += len(result["candidates_rejected"])
        print(f"   extracted={ext} inserted={ins} rejected={rej}")
        grand["reports"] += len(reports)
        grand["extracted"] += ext
        grand["inserted"] += ins
        grand["rejected"] += rej

    print(f"\n==== TOTAL: reports={grand['reports']} extracted={grand['extracted']} "
          f"inserted={grand['inserted']} rejected={grand['rejected']}")

    if not args.dry_run:
        # 终态统计
        for et_id in EVENT_TYPES:
            stats = cand_repo.count_by_event_type(et_id)
            print(f"  {et_id}: pending={stats.get('pending', 0)} total={stats.get('total', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
