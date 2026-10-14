#!/usr/bin/env python3
"""agent_D_extract.py — MP-2 evt_data_breach 语料入库 + 技战法候选抽取落库.

用法
----
    cd /path/to/hotspot-mp2-agent-D && .venv/bin/python scripts/agent_D_extract.py

职责
----
1. 扫描 data/security/incidents/agent_D/*.md, 解析元数据头 (source_url 等)
2. IncidentReportService.ingest_report 入库 (idempotent by source_url, 硬约束: 真 URL)
3. 按 per-report 候选映射 (LLM 抽取产出, 引号均为源文逐字子串) 落候选池
4. EventTechniqueExtractService.submit_candidate 内置程序化校验:
   technique FK ∈ attack_techniques / evidence_quote substring / confidence ≥ 0.4
5. 打印摘要; 幂等可重跑 (UNIQUE 约束兜底)

LLM 抽取说明
------------
抽取由 agent 模型 (GLM) 按 DISCUSSION §7.2 规约完成: 每条候选带 evidence_quote
(≤120 字逐字子串) + rationale (≤80 字) + stage + confidence。脚本只负责把抽取
结果经程序化校验写入候选池, 不在脚本内调用外部 LLM API (owner 裁决: MP-2 临时
prompt 即可, 不固化配置)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.repository.db import apply_migrations, get_connection  # noqa: E402
from backend.services.attack_loader import load_attack_data  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)
from backend.services.incident_report_service import IncidentReportService  # noqa: E402

CORPUS_DIR = ROOT / "data" / "security" / "incidents" / "agent_D"
EVENT_TYPE_ID = "evt_data_breach"
AGENT_OWNER = "D"
LLM_MODEL = "glm-4.6-agent-curation"

# LLM 抽取结果 (引号逐字来自各报告 report_md; technique 均已核对 attack_techniques FK)
EXTRACTIONS: dict[str, list[dict]] = {
    "report_01_dbir_financial.md": [
        {
            "technique_id": "T1078",
            "stage": "credential_access",
            "confidence": 0.90,
            "evidence_quote": "攻击者使用窃取的合法员工凭据登录业务系统",
            "rationale": "窃取合法凭据登录业务系统, 即 Valid Accounts 凭据访问滥用",
        },
        {
            "technique_id": "T1190",
            "stage": "initial_access",
            "confidence": 0.85,
            "evidence_quote": "金融业数据泄露的首要入口是 Web 应用攻击与凭据盗用组合",
            "rationale": "Web 应用攻击对应面向公众应用的初始访问入口",
        },
        {
            "technique_id": "T1005",
            "stage": "collection",
            "confidence": 0.85,
            "evidence_quote": "得手后攻击者直接在应用内批量检索导出客户记录",
            "rationale": "应用内批量检索导出客户记录, 属本地系统数据收集",
        },
        {
            "technique_id": "T1041",
            "stage": "exfiltration",
            "confidence": 0.70,
            "evidence_quote": "随后将数据经既有命令信道回传至外部服务器",
            "rationale": "经既有命令信道外传数据, 符合 C2 信道外传模式",
        },
    ],
    "report_02_hibp_cloud.md": [
        {
            "technique_id": "T1552",
            "stage": "credential_access",
            "confidence": 0.75,
            "evidence_quote": "桶内含明文数据库连接串与访问密钥",
            "rationale": "对象存储内明文密钥, 属未加固凭据发现",
        },
        {
            "technique_id": "T1530",
            "stage": "collection",
            "confidence": 0.85,
            "evidence_quote": "扫描器在配置错误暴露后数小时内即完成全量抓取",
            "rationale": "对公开云存储对象的全量遍历抓取, 属云存储对象数据收集",
        },
        {
            "technique_id": "T1567",
            "stage": "exfiltration",
            "confidence": 0.70,
            "evidence_quote": "数据随后被打包出现在地下论坛交易",
            "rationale": "数据经网络服务流出并在论坛交易, 属 Web 服务信道外传",
        },
    ],
    "report_03_privacyaffairs_insider.md": [
        {
            "technique_id": "T1078",
            "stage": "initial_access",
            "confidence": 0.90,
            "evidence_quote": "信贷员利用职务账号在数月内越权批量查询数千名客户征信与账户流水",
            "rationale": "合法职务账号越权使用, 即有效账号作为初始入口滥用",
        },
        {
            "technique_id": "T1567",
            "stage": "exfiltration",
            "confidence": 0.75,
            "evidence_quote": "将查询结果整理后通过即时通讯文件接口出售给贷款中介",
            "rationale": "经即时通讯文件接口外传客户数据, 属 Web 服务信道外传",
        },
    ],
}

_META_RE = re.compile(r"^- \*\*(source_url|fetched_at|event_class_hint|industry)\*\*: (.+)$", re.M)


def parse_corpus(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta = {m.group(1): m.group(2).strip() for m in _META_RE.finditer(text)}
    for key in ("source_url", "fetched_at"):
        if key not in meta:
            raise ValueError(f"{path.name}: missing metadata key {key!r}")
    return {
        "file": path.name,
        "title": meta.get("title", path.stem),
        "source_url": meta["source_url"],
        "fetched_at": meta["fetched_at"],
        "event_class_hint": meta.get("event_class_hint", "data_breach"),
        "report_md": text,  # 整文件入库, 保证 evidence substring 命中
    }


def main() -> int:
    apply_migrations(get_connection())
    # FK guard 依赖 attack_techniques 已落数据 (M1 图谱点火); loader 幂等,
    # 表空时从 data/stix/attack-techniques.json 灌入 (repo 内置静态字典)
    loaded = load_attack_data()
    if loaded.get("techniques"):
        print(f"[agent-D] attack_techniques loaded: {loaded['techniques']}")
    report_svc = IncidentReportService()
    extract_svc = EventTechniqueExtractService()

    files = sorted(CORPUS_DIR.glob("*.md"))
    print(f"[agent-D] corpus files: {len(files)}")
    ok_persisted = 0
    ok_rejected = 0

    for f in files:
        parsed = parse_corpus(f)
        report = report_svc.ingest_report(
            source_url=parsed["source_url"],
            title=parsed["title"],
            fetched_at=parsed["fetched_at"],
            report_md=parsed["report_md"],
            event_class_hint=parsed["event_class_hint"],
            agent_owner=AGENT_OWNER,
        )
        print(
            f"[agent-D] report ingested: {f.name} -> {report['id'][:8]} "
            f"(url={parsed['source_url']})"
        )
        for cand in EXTRACTIONS.get(f.name, []):
            result = extract_svc.submit_candidate(
                event_type_id=EVENT_TYPE_ID,
                technique_id=cand["technique_id"],
                stage=cand["stage"],
                confidence=cand["confidence"],
                evidence_quote=cand["evidence_quote"],
                source_report_id=report["id"],
                rationale=cand["rationale"],
                llm_model=LLM_MODEL,
                agent_owner=AGENT_OWNER,
            )
            if result["accepted"]:
                ok_persisted += 1
                print(f"  + candidate {cand['technique_id']}/{cand['stage']} conf={cand['confidence']}")
            else:
                ok_rejected += 1
                print(f"  - REJECTED {cand['technique_id']}/{cand['stage']}: {result['auto_reject_reason']}")

    print(f"\n[agent-D] persisted={ok_persisted} rejected={ok_rejected}")
    return 0 if ok_persisted >= 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
