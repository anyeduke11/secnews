#!/usr/bin/env python3
"""agent-C LLM 抽取替身 — evt_fraud (反诈) 事件类型候选落库.

规约 (PLAN_MP2_EVENT_TYPE_2026-09-13.md §7 + MP-2 反诈专用规则):
  1. technique_id 在 attack_techniques 存在 (FK 校验由 extract service.submit_candidate enforce)
  2. evidence_quote 必须是 report_md 原文子串 (NFKC + 空白折叠后逐字命中)
  3. confidence ≥ 0.4 才入候选池
  4. stage 必填
  5. 反诈策展: 社会工程链路候选 technique_id=NULL。schema 阶段
     (event_technique_candidates.technique_id NOT NULL) 无法承载 → submit_candidate 显式
     返回 'unsupported:null_technique' 并跳过 (不静默); 仅 FK 合法候选落库
  6. 同源同位置去重 (UNIQUE(event_type, technique, report) 兜底 → duplicate_candidate)
  7. owner_status 一律 'pending', 不写 event_technique_map

用法:
  PYTHONPATH=backend .venv/bin/python scripts/agent_C_extract.py
  PYTHONPATH=backend .venv/bin/python scripts/agent_C_extract.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 保证可从仓库根 import backend 包
sys.path.insert(0, str(ROOT))

from backend.repository.db import apply_migrations, get_connection  # noqa: E402
from backend.services.attack_loader import load_attack_data  # noqa: E402
from backend.services.event_technique_extract_service import EventTechniqueExtractService  # noqa: E402
from backend.services.incident_report_service import IncidentReportService  # noqa: E402

CORPUS_DIR = ROOT / "data" / "security" / "incidents" / "agent_C"
AGENT_OWNER = "C"
LLM_MODEL = "agent-C-curated-extractor-v1"  # 抽取替身: 策展候选集 (无 ai_hub 依赖)


def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """简单 YAML frontmatter 解析: --- 包围的 key: value 头部 + body."""
    if not md_text.startswith("---"):
        return {}, md_text
    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return {}, md_text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, parts[2].strip()


# ── 候选集 (策展: 每条 evidence_quote 均为对应报告 body 逐字子串) ─────────────

CANDIDATES: list[dict] = [
    # ── rep-pboc: 央行支付结算司通报 ──
    {"file": "pboc_payment_fraud_2024.md", "technique_id": None, "stage": "initial_access_victim",
     "confidence": 0.75, "is_social_engineering_only": True,
     "evidence_quote": "冒充平台客服致电受害者, 以\"理赔\"\"退款\"\"账户异常\"为由诱导受害者开启屏幕共享",
     "rationale": "冒充客服属受害者侧社会工程, ATT&CK 无直接命中, 落 social_engineering_only"},
    {"file": "pboc_payment_fraud_2024.md", "technique_id": "T1098", "stage": "credential_access",
     "confidence": 0.7, "is_social_engineering_only": False,
     "evidence_quote": "通过\"换绑手机号\"流程实施账户接管",
     "rationale": "换绑手机号=账户操纵, 对应 ATT&CK T1098 Account Manipulation"},
    {"file": "pboc_payment_fraud_2024.md", "technique_id": "T1557", "stage": "credential_access",
     "confidence": 0.65, "is_social_engineering_only": False,
     "evidence_quote": "通过伪基站 + 短信嗅探, 在用户不泄露验证码的前提下完成小额免密支付",
     "rationale": "短信嗅探拦截 OTP 属中间人收集, 对应 T1557 Adversary-in-the-Middle"},
    {"file": "pboc_payment_fraud_2024.md", "technique_id": None, "stage": "initial_access_victim",
     "confidence": 0.7, "is_social_engineering_only": True,
     "evidence_quote": "伪造\"高收益低风险\"理财项目",
     "rationale": "虚假投资引流为纯社工话术, technique 缺失, stage 必命中"},
    # ── rep-cba: 银行业协会反诈报告 ──
    {"file": "cba_anti_fraud_2024.md", "technique_id": None, "stage": "reconnaissance",
     "confidence": 0.7, "is_social_engineering_only": True,
     "evidence_quote": "伪装\"离异金融高管\"\"海外投资顾问\"等身份",
     "rationale": "杀猪盘人设伪造属攻击者侦察/资源阶段, 无直接 ATT&CK 技术"},
    {"file": "cba_anti_fraud_2024.md", "technique_id": None, "stage": "impact_financial_loss",
     "confidence": 0.8, "is_social_engineering_only": True,
     "evidence_quote": "诱导受害者向指定账户大额转账",
     "rationale": "受害者在信任建立后被诱导加码入金, 财务损失阶段"},
    {"file": "cba_anti_fraud_2024.md", "technique_id": "T1204", "stage": "execution",
     "confidence": 0.6, "is_social_engineering_only": False,
     "evidence_quote": "受害者被引导下载仿冒交易 APP",
     "rationale": "诱导用户执行(安装仿冒 APP), 对应 T1204 User Execution"},
    {"file": "cba_anti_fraud_2024.md", "technique_id": None, "stage": "impact_financial_loss",
     "confidence": 0.7, "is_social_engineering_only": True,
     "evidence_quote": "收取\"手续费\"\"保证金\"\"验资款\"等名义骗取资金",
     "rationale": "虚假贷款费用诈骗为纯话术, technique 缺失"},
    # ── rep-ic3: FBI IC3 Elder Fraud ──
    {"file": "ic3_elder_fraud_2024.md", "technique_id": None, "stage": "initial_access_victim",
     "confidence": 0.75, "is_social_engineering_only": True,
     "evidence_quote": "pose as bank fraud investigators, federal agents, or tech support staff",
     "rationale": "冒充公职/技术支持属受害者侧社工, technique 缺失"},
    {"file": "ic3_elder_fraud_2024.md", "technique_id": None, "stage": "impact_financial_loss",
     "confidence": 0.75, "is_social_engineering_only": True,
     "evidence_quote": "funds must be moved to a \"safe government account\" via wire transfer",
     "rationale": "引导转账至\"安全账户\"为财务损失动作"},
    {"file": "ic3_elder_fraud_2024.md", "technique_id": None, "stage": "resource_development",
     "confidence": 0.6, "is_social_engineering_only": True,
     "evidence_quote": "typically cryptocurrency trading on spoofed platforms",
     "rationale": "仿冒交易平台属诈骗资源开发, ATT&CK 企业域无命中"},
    # ── rep-interpol: INTERPOL Financial Crimes ──
    {"file": "interpol_financial_crimes_2024.md", "technique_id": "T1566", "stage": "initial_access",
     "confidence": 0.65, "is_social_engineering_only": False,
     "evidence_quote": "register look-alike domains, and insert themselves into ongoing correspondence",
     "rationale": "仿冒域名插入邮件会话属钓鱼, 对应 T1566 Phishing"},
    {"file": "interpol_financial_crimes_2024.md", "technique_id": "T1557", "stage": "credential_access",
     "confidence": 0.7, "is_social_engineering_only": False,
     "evidence_quote": "disclosing one-time passwords or approving push notifications, enabling immediate account takeover",
     "rationale": "电话诱导泄露 OTP 属社工型凭据收集, 结合 vishing 代理对应 T1557"},
    {"file": "interpol_financial_crimes_2024.md", "technique_id": None, "stage": "impact_financial_loss",
     "confidence": 0.55, "is_social_engineering_only": True,
     "evidence_quote": "laundered through networks of recruited or unwitting money mules",
     "rationale": "资金经骡子网络洗出为损失转移环节, 企业域无直接技术"},
    # ── rep-chainalysis: Chainalysis Crypto Crime ──
    {"file": "chainalysis_crypto_crime_2025.md", "technique_id": None, "stage": "resource_development",
     "confidence": 0.7, "is_social_engineering_only": True,
     "evidence_quote": "Operators run large-scale social media campaigns",
     "rationale": "大规模社媒引流属诈骗资源开发, technique 缺失"},
    {"file": "chainalysis_crypto_crime_2025.md", "technique_id": None, "stage": "impact_financial_loss",
     "confidence": 0.6, "is_social_engineering_only": True,
     "evidence_quote": "consolidated into intermediary wallets, and then bridged or swapped through mixers",
     "rationale": "链上归集/混币洗出为资金损失转移, ATT&CK 企业域无命中"},
    {"file": "chainalysis_crypto_crime_2025.md", "technique_id": None, "stage": "initial_access_victim",
     "confidence": 0.6, "is_social_engineering_only": True,
     "evidence_quote": "downloading custom apps that display fabricated balances",
     "rationale": "诱导安装假余额 APP 属受害者侧社工执行"},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = get_connection()
    apply_migrations(conn)
    load_attack_data()

    print("[1/2] load incident reports ...")
    report_svc = IncidentReportService()
    file_to_id: dict[str, str] = {}
    for path in sorted(CORPUS_DIR.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if args.dry_run:
            file_to_id[path.name] = f"dry:{path.name}"
            continue
        # ingest_report 自身按 source_url 幂等去重
        r = report_svc.ingest_report(
            source_url=meta["source_url"],
            title=meta.get("title", path.stem),
            fetched_at=meta.get("fetched_at", ""),
            report_md=body,
            event_class_hint=meta.get("event_class_hint"),
            agent_owner=AGENT_OWNER,
        )
        file_to_id[path.name] = r["id"]
        print(f"  report {path.name}: {'created' if r['new'] else 'exists'} -> {r['id']}")

    if args.dry_run:
        print("dry-run stop")
        return 0

    print("[2/2] submit candidates ...")
    ext = EventTechniqueExtractService()
    accepted = rejected = deduped = unsupported = 0
    for cand in CANDIDATES:
        rid = file_to_id.get(cand["file"])
        if not rid:
            continue
        r = ext.submit_candidate(
            event_type_id="evt_fraud",
            technique_id=cand["technique_id"],
            stage=cand["stage"],
            confidence=cand["confidence"],
            evidence_quote=cand["evidence_quote"],
            rationale=cand["rationale"],
            source_report_id=rid,
            llm_model=LLM_MODEL,
            agent_owner=AGENT_OWNER,
        )
        reason = r["auto_reject_reason"]
        if r["accepted"]:
            accepted += 1
        elif reason == "duplicate_candidate":
            deduped += 1
        elif reason and reason.startswith("unsupported:"):
            unsupported += 1
            print(f"  不支持(跳过): {cand['file']} reason={reason} quote={cand['evidence_quote'][:30]}...")
        else:
            rejected += 1
            print(f"  REJECTED ({reason}): {cand['evidence_quote'][:40]}...")
    print(
        f"accepted={accepted} rejected={rejected} "
        f"deduped={deduped} unsupported={unsupported}"
    )
    stats = ext.candidate_repo.count_by_event_type("evt_fraud")
    print(json.dumps(stats, ensure_ascii=False))
    # 成功门槛 = FK 合法候选数 (12 条 NULL-technique 策展候选按 schema 不可承载, 不计入)
    return 0 if accepted >= 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
