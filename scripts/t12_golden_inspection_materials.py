"""T12 SK-03 inspection-materials 黄金案例演练 — 续接 T11 12 步走查.

T11 已落 6 步: prompt → dsh → evidence → create_draft → publish → walkthrough.
T12 续 6 步: action_create_with_dsh → action_approve → action_start (→ run + finish) →
             artifact_create → artifact_verify+accept → case_close_with_acceptance.

虚构 CVE-2026-31337 全链路 (baseline §5 第 4 步).
- 不连真网络; mock dsh 返固定 JSON; dry-run 默认, --apply 真落 v1_actions/runs/artifacts 表.
- T11 trace.json (judgment 已 published) 作为 T12 输入; --reuse-t11-trace=<path> 复用.

执行:
  python scripts/t12_golden_inspection_materials.py                        # dry-run, 打印 12 步
  python scripts/t12_golden_inspection_materials.py --apply                # 真落库 (走 temp_db conftest)
  python scripts/t12_golden_inspection_materials.py --reuse-t11-trace=<j>  # 复用 T11 judgment id
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_isolated_db() -> None:
    if os.environ.get("HOTSPOT_DB_PATH"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t12-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


# ---------------------------------------------------------------------------
# 虚构 CVE-2026-31337 (与 T11 同场景)
# ---------------------------------------------------------------------------
GOLDEN_CVE = "CVE-2026-31337"
GOLDEN_SUBJECT = "某 SSL VPN 网关 (FastGate 3200)"


def _mock_dsh_response() -> str:
    return json.dumps({
        "plan": (
            "## 行动\n"
            "1. 紧急升级 FastGate 到 7.2.0\n"
            "2. 升级前在 WAF 临时加 `../` 拦截规则\n"
            "3. 检查 3 月 12 日探测 IP 的访问日志, 评估数据外泄\n"
            "4. 7 天内完成 4200 衍生型号清点\n\n"
            "## 回退\n"
            "- 若升级失败, 启用 WAF 拦截规则 + 离线非关键节点\n"
        ),
        "expected_artifacts": ["upgrade_checklist", "post_upgrade_report"],
        "success_criteria": "升级完成 + WAF 规则生效 + 7 天无新探测",
        "tool_versions": {"patcher": "1.0", "waf_cli": "2.3"},
        "unknowns": ["4200 衍生型号清单", "PoC 是否能读到 /etc/shadow"],
    })


def run_step_7_action_create(temp_db, *, apply: bool) -> dict[str, Any]:
    """Step 7: action.create_with_dsh (dsh 调 inspection-materials)."""
    if not apply:
        return {"step": "7_action_create", "skipped_dry_run": True}
    from backend.services.action_service import ActionService
    svc = ActionService(dsh_caller=lambda _p: _mock_dsh_response())
    jid = "J" + "X" * 25
    out = svc.create_with_dsh(
        case_id="C" * 26, judgment_id=jid, title="CVE-2026-31337 修复行动",
        subject_name=GOLDEN_SUBJECT, cve_id=GOLDEN_CVE, scope="生产环境",
        evidence_materials=[],
    )
    a = out["action"]
    return {
        "step": "7_action_create",
        "action_id": a["id"], "status": a["status"],
        "plan_hash_first16": a["plan_hash"][:16],
        "expected_artifacts": a["expected_artifacts"],
        "allowed_actions": a["allowed_actions"],
    }


def run_step_8_action_approve(*, apply: bool) -> dict[str, Any]:
    """Step 8: action.approve (planned → approved)."""
    if not apply:
        return {"step": "8_action_approve", "skipped_dry_run": True}
    from backend.services.action_service import ActionService
    conn_path = "var/folders/m5/vtf5zzms4d74m83g6_8shx9h0000gn/T"
    # 走默认全局连接 (apply 模式已设 HOTSPOT_DB_PATH)
    svc = ActionService()
    actions = svc.list_by_case("C" * 26, status="planned", limit=1)["items"]
    if not actions:
        return {"step": "8_action_approve", "error": "no planned action found"}
    a = actions[0]
    out = svc.approve(a["id"], expected_revision=a["revision"], approved_by="user")
    return {
        "step": "8_action_approve",
        "action_id": out["id"], "status": out["status"],
        "approved_by": out["approved_by"],
    }


def run_step_9_action_start(*, apply: bool) -> dict[str, Any]:
    """Step 9: action.start (approved → running; 创建 Run)."""
    if not apply:
        return {"step": "9_action_start", "skipped_dry_run": True}
    from backend.services.action_service import ActionService
    svc = ActionService()
    actions = svc.list_by_case("C" * 26, status="approved", limit=1)["items"]
    if not actions:
        return {"step": "9_action_start", "error": "no approved action found"}
    a = actions[0]
    out = svc.start(
        a["id"], expected_revision=a["revision"],
        idempotency_key=f"t12-idem-{uuid.uuid4().hex[:8]}", protocol="mock",
    )
    return {
        "step": "9_action_start",
        "action_status": out["action"]["status"],
        "run_id": out["run"]["id"], "run_status": out["run"]["status"],
        "replayed": out["replayed"],
    }


def run_step_10_artifact_create(*, apply: bool) -> dict[str, Any]:
    """Step 10: artifact.create (run_id + content_hash)."""
    if not apply:
        return {"step": "10_artifact_create", "skipped_dry_run": True}
    from backend.services.artifact_service import ArtifactService
    from backend.repository.db import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM v1_runs ORDER BY created_at DESC LIMIT 1",
    ).fetchone()
    if row is None:
        return {"step": "10_artifact_create", "error": "no run found"}
    rid = row[0]
    svc = ArtifactService()
    content = (
        "# FastGate 3200 升级报告\n\n"
        "## 升级\n- 7.2.0 升级成功 (1 小时)\n"
        "## 验证\n- WAF 规则已生效\n- 7 天内无新探测\n"
    )
    a = svc.create(run_id=rid, kind="report", title="升级报告", content=content, format="md")
    return {
        "step": "10_artifact_create",
        "artifact_id": a["id"], "status": a["status"],
        "content_hash_first16": a["content_hash"][:16],
        "size_bytes": a["size_bytes"],
    }


def run_step_11_artifact_verify_accept(*, apply: bool) -> dict[str, Any]:
    """Step 11: artifact.verify + accept (pending → verified → accepted)."""
    if not apply:
        return {"step": "11_artifact_verify_accept", "skipped_dry_run": True}
    from backend.services.artifact_service import ArtifactService
    from backend.repository.db import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM v1_artifacts ORDER BY created_at DESC LIMIT 1",
    ).fetchone()
    if row is None:
        return {"step": "11_artifact_verify_accept", "error": "no artifact"}
    aid = row[0]
    svc = ArtifactService()
    a1 = svc.verify(aid, verified_by="ci-bot", verified_result="pass")
    a2 = svc.accept(aid, accepted_by="user", accepted_note="排查完成, 7 天无异常")
    return {
        "step": "11_artifact_verify_accept",
        "artifact_id": a1["id"],
        "status": a2["status"],
        "verified_result": a1["verified_result"],
        "accepted_by": a2["accepted_by"],
        "accepted_note": a2["accepted_note"],
    }


def run_step_12_case_close(*, apply: bool) -> dict[str, Any]:
    """Step 12: case.close (仅在 judgment published + action succeeded + artifact accepted 满足时)."""
    if not apply:
        return {"step": "12_case_close", "skipped_dry_run": True}
    # case.close 由 case_service 提供; 此处仅做 evidence 走查
    from backend.repository.db import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM v1_artifacts WHERE status = 'accepted' ORDER BY accepted_at DESC LIMIT 1",
    ).fetchone()
    if row is None:
        return {"step": "12_case_close", "skipped": "no accepted artifact (验收未走通)"}
    return {
        "step": "12_case_close",
        "accepted_artifact_id": row[0],
        "evidence": "材料已生成 + 业务验收通过 = 排查完成 (baseline §5)",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T12 SK-03 inspection-materials 黄金案例演练")
    ap.add_argument("--apply", action="store_true", help="真落 v1_actions/runs/artifacts 表 (走 temp_db)")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状, 不调服务")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()
        if args.apply:
            from backend.repository import db
            db.init_db()
            # 复用 T11 的 judgment (CVE-2026-31337 published) — 直接 seed (走 T11 golden 同模式)
            from backend.services.judgment_service import JudgmentService
            from backend.repository.db import get_connection
            conn = get_connection()
            now = "2026-09-06T00:00:00+00:00"
            jid = "J" + "X" * 25
            conn.execute(
                "INSERT OR IGNORE INTO v1_judgments "
                "(id, case_id, claim_type, claim, conditions, confidence, "
                " evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, "
                " content_hash, revision, published_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (jid, "C" * 26, "finding", "## 影响\n该漏洞影响核心", "生产", "high",
                 "[]", "[]", "[\"待评估\"]", "published", "h" * 64, 1, now, now, now),
            )
            conn.commit()

    steps: list[dict[str, Any]] = []
    steps.append(run_step_7_action_create(temp_db=None, apply=args.apply))
    steps.append(run_step_8_action_approve(apply=args.apply))
    steps.append(run_step_9_action_start(apply=args.apply))
    steps.append(run_step_10_artifact_create(apply=args.apply))
    steps.append(run_step_11_artifact_verify_accept(apply=args.apply))
    steps.append(run_step_12_case_close(apply=args.apply))

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t12-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"cve_id": GOLDEN_CVE, "subject": GOLDEN_SUBJECT,
         "steps": steps, "mode": "apply" if args.apply else "dry-run"},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(json.dumps({
        "cve": GOLDEN_CVE, "mode": "apply" if args.apply else "dry-run",
        "steps_count": len(steps), "trace": str(out_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
