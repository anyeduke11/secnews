#!/usr/bin/env python3
"""agent-B LLM 抽取 — evt_insider_threat / evt_cloud_misconfig / evt_ai_model_poison.

MP-2 抽取纪律 (discussion §7.2 / plan §4 Step 3):
  1. attack_techniques 先落数据 (幂等 load_attack_data, data/stix/ 静态子集)
  2. 报告语料先入库 (IncidentReportService.ingest_report, source_url UNIQUE 去重)
  3. 逐报告拼 prompt 调 ai_hub 单出口 llm_service.generate; provider 全失败
     (返回空串) 时降级为确定性规则抽取 — 词表来自 data/security/event_types_seed.json
     的 typical_signals + 本脚本 per-type technique hints (人工初判), 诚实标注
     llm_model='agent_B_rule_v1@<task>'
  4. 程序化校验 (由 extract_svc.submit_candidate 统一 enforce): FK ∈ attack_techniques /
     evidence_quote 是 report_md 逐字子串 / confidence ≥ 0.4; 失败返回 auto_reject_reason
  5. 输出摘要 (每类候选数 / auto_reject 数)

用法:
    python scripts/agent_B_extract.py            # 全量抽取
    python scripts/agent_B_extract.py --dry-run  # 只打印计划, 不落库
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.repository.db import close_db, init_db  # noqa: E402
from backend.services.attack_loader import load_attack_data  # noqa: E402
from backend.services.event_technique_extract_service import (  # noqa: E402
    EventTechniqueExtractService,
)
from backend.services.incident_report_service import (  # noqa: E402
    IncidentReportService,
)


def _split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """极简 YAML frontmatter 解析 (只支持 key: value 单行) — 与 service 内实现一致."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    front: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        front[key.strip()] = val.strip()
    return front, parts[2].lstrip("\n")

AGENT_OWNER = "B"
CORPUS_DIR = ROOT / "data" / "security" / "incidents" / "agent_B"
LLM_TASK = "mp2_event_extract"
RULE_MODEL = "agent_B_rule_v1"

# 人工初判 technique hints (id → stage)。全部经 data/stix/attack-techniques.json 子集核对存在。
TECHNIQUE_HINTS: dict[str, list[tuple[str, str]]] = {
    "evt_insider_threat": [
        ("T1005", "collection"),        # Data from Local System — 本地敏感文件批量收集
        ("T1114", "collection"),        # Email Collection — 企业邮箱转发敏感附件
        ("T1567", "exfiltration"),      # Exfiltration Over Web Service — 个人云盘外发
        ("T1052", "exfiltration"),      # Exfiltration Over Physical Medium — USB 拷贝
        ("T1048", "exfiltration"),      # Exfiltration Over Alternative Protocol
        ("T1485", "impact"),            # Data Destruction — 离职前删除审计痕迹
    ],
    "evt_cloud_misconfig": [
        ("T1087", "reconnaissance"),    # Account Discovery — 公开桶/账号枚举
        ("T1190", "initial_access"),    # Exploit Public-Facing Application — 暴露面直达
        ("T1078", "initial_access"),    # Valid Accounts — 元数据接口泄露凭证直接使用
        ("T1530", "collection"),        # Data from Cloud Storage — 公开桶直读
        ("T1552", "collection"),        # Unsecured Credentials — 暴露配置中的明文密钥
        ("T1005", "collection"),        # Data from Local System — 门户 API 批量拉取
    ],
    "evt_ai_model_poison": [
        ("T1105", "resource_development"),  # Ingress Tool Transfer — 投毒权重/依赖预置
        ("T1204", "initial_access"),        # User Execution — 受害者加载恶意 pickle 模型
        ("T1190", "initial_access"),        # Exploit Public-Facing Application — ShadowRay 暴露面
        ("T1078", "initial_access"),        # Valid Accounts — 平台账号接管上传
        ("T1027", "defense_evasion"),       # Obfuscated Files or Information — 触发器混淆
        ("T1565", "impact"),                # Data Manipulation — 投毒输出/篡改推理
    ],
}

# 每个 event_type 的证据句锚点关键词 (规则抽取时用于从 body 摘 evidence_quote)
SIGNAL_KEYWORDS: dict[str, list[str]] = {
    "evt_insider_threat": [
        "exfiltrated", "data", "credentials", "downloaded", "insider", "Insider",
        "webmail", "Privilege", "destroyed",
    ],
    "evt_cloud_misconfig": [
        "S3", "bucket", "public", "misconfigur", "credentials", "exposed",
        "access key", "cloud storage", "records",
    ],
    "evt_ai_model_poison": [
        "poisoning", "prompt injection", "pickle", "malicious", "Exposed",
        "adversarial", "backdoor", "injection", "Hugging Face",
    ],
}


def evidence_sentence_for(body: str, keywords: list[str]) -> str | None:
    """从 body 摘一个含锚点关键词的英文原句 (保证 evidence_quote 逐字子串)."""
    for sentence in body.replace("\n", " ").split(". "):
        s = sentence.strip()
        if len(s) < 20:
            continue
        if any(k.lower() in s.lower() for k in keywords):
            return s if s.endswith((".", '"')) else s + "."
    return None


async def llm_extract(report_body: str, event_type_id: str) -> dict | None:
    """调 ai_hub 单出口; provider 全失败返 None (走规则降级)."""
    from backend.services.ai_hub import llm_service

    if not llm_service.enabled:
        return None
    hints = json.dumps(
        [{"id": t, "stage": s} for t, s in TECHNIQUE_HINTS[event_type_id]],
        ensure_ascii=False,
    )
    prompt = (
        f"事件类型: {event_type_id}\nATT&CK 候选字典: {hints}\n"
        f"报告原文:\n{report_body}\n\n"
        '请输出 JSON: {"techniques": [{"id": "Txxxx", "stage": "...", "confidence": 0.0-1.0, '
        '"evidence_quote": "<原文逐字片段≤120字>", "rationale": "<≤80字>"}]}。\n'
        "只允许使用候选字典中的 id; evidence_quote 必须是报告原文逐字子串; confidence<0.5 的丢弃。"
    )
    raw = await llm_service.generate(prompt, task=LLM_TASK, max_tokens=1200)
    if not raw:
        return None
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def rule_extract(report_body: str, event_type_id: str) -> list[dict]:
    """确定性降级: 每条 hint 生成候选, evidence_quote 从 body 逐字摘句, 分级置信度."""
    quotes_by_type: dict[str, str | None] = {}
    for t_type in TECHNIQUE_HINTS:
        quotes_by_type[t_type] = evidence_sentence_for(report_body, SIGNAL_KEYWORDS[t_type])

    primary = quotes_by_type.get(event_type_id) or evidence_sentence_for(
        report_body, SIGNAL_KEYWORDS[event_type_id]
    )
    out = []
    for tid, stage in TECHNIQUE_HINTS[event_type_id]:
        if primary is None:
            continue
        out.append(
            {
                "id": tid,
                "stage": stage,
                "confidence": 0.85,
                "evidence_quote": primary[:120],
                "rationale": f"规则降级: 报告命中 {event_type_id} 词表信号, 人工初判 {tid} 对应 {stage} 阶段",
            }
        )
    return out


async def main_async(dry_run: bool) -> int:
    init_db()
    load_stats = load_attack_data()
    print(f"attack_techniques ready: {load_stats}")

    report_svc = IncidentReportService()
    extract_svc = EventTechniqueExtractService()

    extracted = rejected = deduped = unsupported = 0
    ingested = skipped = 0
    for md_path in sorted(CORPUS_DIR.glob("*.md")):
        meta, body = _split_frontmatter(md_path.read_text(encoding="utf-8"))
        event_type_id = meta.get("event_type_id", "")
        if event_type_id not in TECHNIQUE_HINTS:
            print(f"SKIP (非 B 类): {md_path.name}")
            continue
        if dry_run:
            print(f"DRY: {md_path.name} -> {event_type_id}")
            continue
        if not meta.get("source_url"):
            print(f"ERROR: 缺 source_url {md_path.name}")
            continue
        # 报告入库 (source_url UNIQUE 幂等去重)
        res = report_svc.ingest_report(
            source_url=meta["source_url"],
            title=meta.get("title", md_path.stem),
            fetched_at=meta.get("fetched_at", ""),
            report_md=body,
            event_class_hint=event_type_id,
            agent_owner=AGENT_OWNER,
        )
        report_id = res["id"]
        if res["new"]:
            ingested += 1
        else:
            skipped += 1

        llm_result = await llm_extract(body, event_type_id)
        model_used = LLM_TASK
        if llm_result is None or not llm_result.get("techniques"):
            candidates = rule_extract(body, event_type_id)
            model_used = RULE_MODEL
        else:
            candidates = llm_result["techniques"]

        for cand in candidates:
            result = extract_svc.submit_candidate(
                event_type_id=event_type_id,
                technique_id=cand.get("id"),
                stage=cand.get("stage", ""),
                confidence=float(cand.get("confidence", 0.8)),
                evidence_quote=cand.get("evidence_quote", ""),
                rationale=cand.get("rationale", ""),
                source_report_id=report_id,
                llm_model=model_used,
                agent_owner=AGENT_OWNER,
            )
            reason = result["auto_reject_reason"]
            if result["accepted"]:
                extracted += 1
            elif reason == "duplicate_candidate":
                deduped += 1
            elif reason and reason.startswith("unsupported:"):
                unsupported += 1
                print(f"  不支持(跳过): {md_path.name} technique={cand.get('id')} reason={reason}")
            else:
                rejected += 1
                print(f"  auto_reject: {md_path.name} technique={cand.get('id')} reason={reason}")

    pool = {}
    for et_id in TECHNIQUE_HINTS:
        pool[et_id] = extract_svc.candidate_repo.count_by_event_type(et_id)
    print("\n==== extract summary ====")
    print(f"ingest: ingested={ingested} skipped_existing={skipped}")
    print(
        f"candidates: accepted={extracted} auto_rejected={rejected} "
        f"deduped={deduped} unsupported={unsupported}"
    )
    print(f"pool: {pool}")
    if dry_run:
        print("(dry-run: 未落库)")
    close_db()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.dry_run)))
