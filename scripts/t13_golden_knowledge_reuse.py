"""T13 SK-04/05/06 黄金案例演练 — 续接 T12 6 步 → T13 6 步.

T11 6 步 (judgment publish) + T12 6 步 (action → run → artifact accepted) →
T13 6 步 (knowledge 发布 → 复用 → 复查):
  ① knowledge_draft_from_action    验收后从 action 生成草稿
  ② knowledge_publish              落 wiki 不可变写
  ③ reuse_query                     新 case 检索知识
  ④ reuse_compare                   条件对比 (evidence_refs 交集)
  ⑤ reuse_apply                     落 receipt (v1_knowledge_refs 增)
  ⑥ review_due_scan                 到期触发 case blocker

不连真网络; mock dsh 返固定 JSON; dry-run 默认, --apply 真落 v1_knowledge 表.
执行:
  python scripts/t13_golden_knowledge_reuse.py            # dry-run
  python scripts/t13_golden_knowledge_reuse.py --apply    # 真落库
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_isolated_db() -> None:
    if os.environ.get("HOTSPOT_DB_PATH"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t13-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


# ---------------------------------------------------------------------------
# Mock 工具
# ---------------------------------------------------------------------------
def _dsh_response() -> str:
    return json.dumps({
        "title": "FastGate 3200 升级到 7.2.0 应对 CVE-2026-31337",
        "body": (
            "## 步骤\n"
            "1. 升级前 24h: WAF 加 ../ 路径拦截规则\n"
            "2. 升级窗口 (1h): 灰度 10% → 50% → 100%\n"
            "3. 升级后 7d: 监控 WAF 日志与异常登录\n\n"
            "## 适用边界\n- 暴露在公网\n- 固件 < 7.2.0"
        ),
        "prerequisites": [
            "FastGate 3200/4200 系列",
            "固件 < 7.2.0",
            "有 WAF 拦截配置权限",
        ],
        "counter_examples": [
            "内网部署且无对外接口",
            "固件已 ≥ 7.2.0",
        ],
        "evidence_refs": [
            {"material_id": "MAT-CVE-ADVISORY", "hash": "c" * 64,
             "quote": "FastGate 3200 路径遍历漏洞, CVSS 9.8"},
            {"material_id": "MAT-NVD-ENTRY", "hash": "d" * 64,
             "quote": "CWE-22 Path Traversal; <7.2.0 受影响"},
        ],
        "review_at": "2026-12-01T00:00:00+00:00",
        "expiry_at": None,
    })


def _seed_full_chain() -> dict[str, Any]:
    """T11+T12 完整链: case + judgment (published) + action (succeeded) + run + artifact (accepted)."""
    from backend.repository import db
    db.init_db()
    from backend.repository.db import get_connection
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    # case
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, tags_json) "
        "VALUES (?, 'CVE-2026-31337 修复', '如何升级 FastGate?', 1, ?, ?, '[]')",
        ("C" * 26, now, now),
    )
    # judgment (published)
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments (id, case_id, claim_type, claim, conditions, confidence, "
        "evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, content_hash, "
        "revision, published_at, created_at, updated_at) "
        "VALUES (?, ?, 'finding', '升级到 7.2.0', '生产', 'high', '[]', '[]', '[]', 'published', ?, 1, ?, ?, ?)",
        ("J" * 26, "C" * 26, "h" * 64, now, now, now),
    )
    # material
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, content_length, "
        "fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        ("MAT-CVE-ADVISORY", "x", "c" * 64),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, content_length, "
        "fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        ("MAT-NVD-ENTRY", "x", "d" * 64),
    )
    # action (succeeded)
    conn.execute(
        "INSERT OR IGNORE INTO v1_actions (id, case_id, judgment_id, title, plan, plan_hash, "
        "expected_artifacts_json, status, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, 't', '# p', ?, '[\"r\"]', 'succeeded', 2, ?, ?)",
        ("A" * 26, "C" * 26, "J" * 26, "h" * 64, now, now),
    )
    # artifact (accepted)
    conn.execute(
        "INSERT OR IGNORE INTO v1_artifacts (id, run_id, kind, title, content_hash, format, "
        "size_bytes, status, revision, created_at, updated_at) "
        "VALUES ('ART-T13', 'run_T13', 'report', '修复报告', ?, 'md', 100, 'accepted', 1, ?, ?)",
        ("a" * 64, now, now),
    )
    conn.commit()
    return {"case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26, "material_ids": ["MAT-CVE-ADVISORY", "MAT-NVD-ENTRY"]}


# ---------------------------------------------------------------------------
# 6 步
# ---------------------------------------------------------------------------
def run_step_1_knowledge_draft(*, apply: bool, seed: dict[str, Any]) -> dict[str, Any]:
    """① knowledge_draft_from_action: 验收后从 action 生成草稿 (T13 SK-04)."""
    if not apply:
        return {"step": "1_knowledge_draft", "skipped_dry_run": True}
    from backend.services.knowledge_service import KnowledgeService
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    k = svc.create_with_dsh(
        case_id=seed["case_id"], judgment_id=seed["judgment_id"],
        action_id=seed["action_id"], subject_name="某 SSL VPN 网关 (FastGate 3200)",
        cve_id="CVE-2026-31337", kind="playbook",
        evidence_materials=[
            {"id": m, "title": "T", "content_hash": h, "summary": "x"}
            for m, h in [("MAT-CVE-ADVISORY", "c" * 64), ("MAT-NVD-ENTRY", "d" * 64)]
        ],
    )["knowledge"]
    return {
        "step": "1_knowledge_draft", "knowledge_id": k["id"],
        "title": k["title"], "status": k["status"],
        "prerequisites_count": len(k["prerequisites"]),
        "counter_examples_count": len(k["counter_examples"]),
        "evidence_refs_count": len(k["evidence_refs"]),
    }


def run_step_2_publish(*, apply: bool, step1: dict[str, Any]) -> dict[str, Any]:
    """② knowledge_publish: 落 wiki 不可变写."""
    if not apply:
        return {"step": "2_publish", "skipped_dry_run": True}
    kid = step1["knowledge_id"]
    from backend.services.knowledge_service import KnowledgeService
    svc = KnowledgeService()
    out = svc.publish(kid, expected_revision=1)
    return {
        "step": "2_publish", "knowledge_id": kid,
        "status": out["status"], "wiki_path": out["wiki_path"],
        "allowed_actions": out["allowed_actions"],
    }


def run_step_3_reuse_query(*, apply: bool, step1: dict[str, Any]) -> dict[str, Any]:
    """③ reuse_query: §9.4 派生 {total, by_judgment, by_action, recent_30d}."""
    if not apply:
        return {"step": "3_reuse_query", "skipped_dry_run": True}
    from backend.services.knowledge_service import KnowledgeService
    svc = KnowledgeService()
    receipt = svc.get_reuse_receipt(step1["knowledge_id"])
    return {
        "step": "3_reuse_query", "receipt": receipt,
        "verdict": "高相关 (judgment+action 双引用, 复用价值高)" if receipt["total"] >= 2 else "部分相关",
    }


def run_step_4_reuse_compare(*, apply: bool, step1: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    """④ reuse_compare: 条件对比 (evidence_refs 交集比例)."""
    if not apply:
        return {"step": "4_reuse_compare", "skipped_dry_run": True}
    kid = step1["knowledge_id"]
    from backend.repository.db import get_connection
    from backend.services.knowledge_service import KnowledgeService
    svc = KnowledgeService()
    k = svc.get(kid)
    knowledge_evidence = {r["material_id"] for r in k.get("evidence_refs", [])}
    # 当前 case.judgment.evidence_refs 取交集
    conn = get_connection()
    judgment_evidence_rows = conn.execute(
        "SELECT evidence_refs_json FROM v1_judgments WHERE id = ?", (seed["judgment_id"],),
    ).fetchone()
    judgment_evidence = set(json.loads(judgment_evidence_rows[0] or "[]") if judgment_evidence_rows else [])
    intersection = knowledge_evidence & judgment_evidence
    # 假设 judgment 当前 evidence 包含 MAT-CVE-ADVISORY → 交集 1
    return {
        "step": "4_reuse_compare",
        "knowledge_evidence": list(knowledge_evidence),
        "judgment_evidence": list(judgment_evidence),
        "intersection": list(intersection),
        "intersection_ratio": len(intersection) / max(1, len(knowledge_evidence)),
        "verdict": "可复用" if intersection else "需补充材料",
    }


def run_step_5_reuse_apply(*, apply: bool, step1: dict[str, Any]) -> dict[str, Any]:
    """⑤ reuse_apply: 落 receipt (v1_knowledge_refs 增, 已在 create_with_dsh 自动落)."""
    if not apply:
        return {"step": "5_reuse_apply", "skipped_dry_run": True}
    from backend.repository.db import get_connection
    kid = step1["knowledge_id"]
    conn = get_connection()
    rows = conn.execute(
        "SELECT source_type, source_id, role FROM v1_knowledge_refs WHERE knowledge_id = ?", (kid,),
    ).fetchall()
    return {
        "step": "5_reuse_apply",
        "refs_count": len(rows), "refs": [(r[0], r[1], r[2]) for r in rows],
    }


def run_step_6_review_due_scan(*, apply: bool, step1: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    """⑥ review_due_scan: SK-06 复查扫描, 倒拨 review_at 触发挂 case blocker."""
    if not apply:
        return {"step": "6_review_due_scan", "skipped_dry_run": True}
    kid = step1["knowledge_id"]
    from backend.repository.db import get_connection
    from backend.services.knowledge_service import KnowledgeService
    conn = get_connection()
    # 倒拨 review_at
    conn.execute("UPDATE v1_knowledge SET review_at = ? WHERE id = ?",
                  ("2020-01-01T00:00:00+00:00", kid))
    conn.commit()
    # 跑 scan + mark_blocker
    svc = KnowledgeService()
    items = svc.scan_review_due("2026-12-01T00:00:00+00:00")
    blocked = 0
    for k in items:
        if k["id"] == kid:
            # 找关联 case
            case_rows = conn.execute(
                "SELECT DISTINCT a.case_id FROM v1_knowledge_refs kr "
                "INNER JOIN v1_actions a ON kr.source_type='action' AND a.id = kr.source_id "
                "WHERE kr.knowledge_id = ?", (kid,),
            ).fetchall()
            for r in case_rows:
                if svc.mark_case_blocker(r[0], kid):
                    blocked += 1
    # 验证 case blocker
    case_row = conn.execute(
        "SELECT tags_json FROM v1_cases WHERE id = ?", (seed["case_id"],),
    ).fetchone()
    tags = json.loads(case_row[0] or "[]")
    has_blocker = any(f"knowledge_review_due:{kid}" == t for t in tags)
    return {
        "step": "6_review_due_scan", "scanned": len(items), "blocked": blocked,
        "case_has_blocker": has_blocker, "tags": tags,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T13 SK-04/05/06 黄金案例演练")
    ap.add_argument("--apply", action="store_true", help="真落 v1_knowledge 表 (走 temp_db conftest)")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状, 不调服务")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()
        if args.apply:
            seed = _seed_full_chain()
        else:
            seed = {"case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26, "material_ids": []}
    else:
        seed = {}

    steps: list[dict[str, Any]] = []
    step1 = run_step_1_knowledge_draft(apply=args.apply, seed=seed)
    steps.append(step1)
    steps.append(run_step_2_publish(apply=args.apply, step1=step1))
    steps.append(run_step_3_reuse_query(apply=args.apply, step1=step1))
    steps.append(run_step_4_reuse_compare(apply=args.apply, step1=step1, seed=seed))
    steps.append(run_step_5_reuse_apply(apply=args.apply, step1=step1))
    steps.append(run_step_6_review_due_scan(apply=args.apply, step1=step1, seed=seed))

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t13-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"cve_id": "CVE-2026-31337", "subject": "FastGate 3200 升级 playbook",
         "steps": steps, "mode": "apply" if args.apply else "dry-run"},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(json.dumps({
        "cve": "CVE-2026-31337", "mode": "apply" if args.apply else "dry-run",
        "steps_count": len(steps), "trace": str(out_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
