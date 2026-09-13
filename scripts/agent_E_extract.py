#!/usr/bin/env python3
"""agent_E_extract.py — MP-2 agent-E 监管通报类 LLM 抽取落库脚本.

MP-2 方案 docs/PLAN_MP2_EVENT_TYPE_2026-09-13.md §4 Step 2~3 (agent-E 范围).

流程:
  1. 读 data/security/incidents/agent_E/*.md 语料 → incident_reports 入库 (source_url 去重)
  2. 按报告逐条生成候选 (regulatory_only 模式: technique_id 可 NULL, stage + evidence_quote 必填)
  3. EventTechniqueExtractService 程序化校验 → event_technique_candidates (pending)

监管通报特殊性 (任务书 B.1):
  - technique 映射常为空 (监管文件描述行业层面而非具体技术) → regulatory_only=1
  - stage 必填 + evidence_quote 必填 (源文子串)
  - confidence 0.6~0.9 (口径明确)

LLM 说明: 本期候选由语料内 "抽取提示" 注记的确定性替身生成 (llm_model=
"mp2-agent-E/seed-extractor-v0"); 主会话合并 A→B→C→D→E 后, 真实 LLM 调用统一
走 ai_hub (红线不碰, 本脚本不 import ai_hub)。

用法::

    .venv/bin/python scripts/agent_E_extract.py            # 语料入库 + 抽取落库
    .venv/bin/python scripts/agent_E_extract.py --dry-run  # 只打印, 不写库
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.db import get_connection, init_db  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)
from backend.services.incident_report_service import IncidentReportService  # noqa: E402

CORPUS_DIR = REPO_ROOT / "data" / "security" / "incidents" / "agent_E"
LLM_MODEL = "mp2-agent-E/seed-extractor-v0"

# 候选 spec: report 文件名 → 候选列表 (evidence_quote 必须是 body 精确子串)
# technique_id=None → regulatory_only 候选 (监管口径, 无具体技术映射)
CANDIDATE_SPEC: dict[str, list[dict]] = {
    "2026_pbc_payment_penalty.md": [
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.9,
            "evidence_quote": "未按规定履行客户身份识别义务、未按规定报送可疑交易报告",
            "rationale": "处罚事由为行业层面反洗钱与可疑交易监测缺位, 无具体攻击技术",
        },
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.75,
            "evidence_quote": "切实防范支付业务被用于电信网络诈骗、赌博等违法犯罪活动的资金转移通道",
            "rationale": "监管要求指向资金转移通道风险防控, 属行业警示口径",
        },
    ],
    "2026_nfra_data_security.md": [
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.85,
            "evidence_quote": "未建立数据分类分级制度，重要数据与一般数据混存混传",
            "rationale": "通报列举数据安全管理缺陷, 属合规口径而非攻击路径",
        },
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.7,
            "evidence_quote": "信息系统日志留存不满足监管要求的六个月期限",
            "rationale": "日志留存不足削弱检测能力, 属监管检查发现的管理问题",
        },
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.65,
            "evidence_quote": "外包开发人员权限管理失控，存在超范围访问生产数据的情形",
            "rationale": "第三方权限失控属内控缺陷, 通报未描述具体技术路径",
        },
    ],
    "2026_cac_app_privacy.md": [
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.85,
            "evidence_quote": "未经用户同意收集通讯录、位置等个人信息",
            "rationale": "通报认定违规收集个人信息, 行业治理口径",
        },
        {
            "technique_id": None,
            "stage": "collection",
            "confidence": 0.6,
            "evidence_quote": "超范围收集与所提供服务无关的个人信息",
            "rationale": "超范围收集语义上对应 collection 阶段, 但通报未描述技术路径",
        },
    ],
    "2026_csrc_sec_report_penalty.md": [
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.9,
            "evidence_quote": "公司未在规定时限内向监管部门报告",
            "rationale": "处罚针对事件报告合规缺陷, 与攻击技术无映射",
        },
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.8,
            "evidence_quote": "不得迟报、漏报、瞒报",
            "rationale": "监管重申分级报告义务, 属行业纪律口径",
        },
    ],
    "2026_mps_pii_crackdown.md": [
        {
            "technique_id": None,
            "stage": "regulatory_notice",
            "confidence": 0.8,
            "evidence_quote": "加强内部人员行为审计与最小权限管理",
            "rationale": "公安提醒指向内控要求, 行业警示而非单事件分析",
        },
        {
            "technique_id": None,
            "stage": "exfiltration",
            "confidence": 0.65,
            "evidence_quote": "违规查询并批量导出客户账户信息后向黑灰产团伙出售",
            "rationale": "内部人员批量导出语义上对应 exfiltration, 通报未给出技术细节",
        },
    ],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MP-2 agent-E 监管通报抽取落库")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划, 不写库")
    args = parser.parse_args(argv)

    init_db()
    report_svc = IncidentReportService()
    extract_svc = EventTechniqueExtractService()

    corpus_files = sorted(CORPUS_DIR.glob("*.md"))
    if len(corpus_files) < 5:
        print(f"[FAIL] corpus files < 5: {len(corpus_files)}")
        return 1

    total_inserted = 0
    total_rejected = 0
    conn = get_connection()
    for md_path in corpus_files:
        if args.dry_run:
            print(f"[dry-run] would ingest {md_path.name} ({len(CANDIDATE_SPEC.get(md_path.name, []))} candidates)")
            continue
        report = report_svc.add_report_from_corpus(md_path, event_class_hint="evt_regulatory_notice")
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM event_technique_candidates WHERE source_report_id = ?",
            (report["id"],),
        ).fetchone()
        if existing and existing["n"] > 0:
            print(f"[skip] {md_path.name}: report {report['id']} already has {existing['n']} candidates")
            continue
        result = extract_svc.extract_one(
            llm_output={
                "source_report_id": report["id"],
                "techniques": [
                    {**c, "id": c.get("technique_id")} for c in CANDIDATE_SPEC.get(md_path.name, [])
                ],
            },
            event_type_id="evt_regulatory_notice",
            llm_model=LLM_MODEL,
            agent_owner="E",
        )
        total_inserted += result.inserted
        total_rejected += result.rejected
        print(
            f"[ok] {md_path.name}: report={report['id']} "
            f"inserted={result.inserted} rejected={result.rejected} "
            f"reject_reasons={[r['auto_reject_reason'] for r in result.rejected_candidates]}"
        )

    if not args.dry_run:
        n_cand = conn.execute(
            "SELECT COUNT(*) AS n FROM event_technique_candidates WHERE event_type_id='evt_regulatory_notice'"
        ).fetchone()["n"]
        n_reg = conn.execute(
            "SELECT COUNT(*) AS n FROM event_technique_candidates WHERE event_type_id='evt_regulatory_notice' AND technique_id IS NULL"
        ).fetchone()["n"]
        n_reports = conn.execute("SELECT COUNT(*) AS n FROM incident_reports").fetchone()["n"]
        print(f"[summary] reports={n_reports} candidates={n_cand} regulatory_only={n_reg} inserted_now={total_inserted} rejected_now={total_rejected}")
        if n_cand < 10:
            print("[FAIL] candidates < 10")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
