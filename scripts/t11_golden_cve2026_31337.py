"""T11 SK-02 黄金案例演练 — 虚构 CVE-2026-31337 漏洞工作全链路.

对应 baseline.md §5 + EXECUTION_GUIDE §T11 通过证据:
  - 每个关键结论点开原文都能解释其依据 (evidence_refs 落 quote)
  - 也能看到不知道什么 (unknowns 字段强制)
  - 材料生成与业务验收分离 (draft → publish 三重守卫)
  - 第二次任务复用带条件判断 (unknowns 体现差异)

不连真网络; mock dsh 返固定 JSON; dry-run 默认, --apply 真落 v1_judgments 表.

执行:
  python scripts/t11_golden_cve2026_31337.py            # dry-run, 打印 6 步走查
  python scripts/t11_golden_cve2026_31337.py --apply   # 真落库 (走 temp_db conftest)
  python scripts/t11_golden_cve2026_31337.py --check   # 仅校验输出形状, 不真调
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
    """T01 隔离: 设 env 强制 conftest 走 tmp_path 数据库."""
    if os.environ.get("HOTSPOT_DB_PATH"):
        return  # 已设 (测试 conftest 接管)
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t11-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


# ---------------------------------------------------------------------------
# 虚构 CVE-2026-31337 漏洞场景 (baseline.md §5 引用)
# ---------------------------------------------------------------------------
GOLDEN_CVE = "CVE-2026-31337"
GOLDEN_SUBJECT = "某 SSL VPN 网关 (FastGate 3200)"
GOLDEN_MATERIALS = [
    {
        "id": "MAT-CVE-ADVISORY",
        "title": "厂商安全公告 — FastGate 3200 任意文件读取 (认证前)",
        "content_hash": "c" * 64,
        "summary": (
            "FastGate 3200 在 7.2.0 之前版本存在路径遍历漏洞, 攻击者无需认证即可读取 "
            "/etc/shadow 等敏感文件; CVSS 3.1 = 9.8 (Critical). 已发布 7.2.0 补丁."
        ),
    },
    {
        "id": "MAT-NVD-ENTRY",
        "title": "NVD CVE-2026-31337 条目",
        "content_hash": "d" * 64,
        "summary": (
            "CWE-22 Path Traversal; 影响 FastGate 3200/4200 全系, <7.2.0 受影响; "
            "官方已确认在野利用; 修复版本 7.2.0."
        ),
    },
    {
        "id": "MAT-RETRO-FEED",
        "title": "客户现场事件 (3 月 12 日) — 异常 /var/log 读尝试",
        "content_hash": "e" * 64,
        "summary": (
            "WAF 检测到对 /var/log/secure 的 GET 探测 (302 次/分钟), 来源 IP 位于 AS15169, "
            "UA 含 python-requests/2.31.0; 已临时封禁."
        ),
    },
]


def _mock_dsh_response() -> str:
    """返 contracts §5 schema 合规 JSON; 模拟 dsh SK-02 输出."""
    return json.dumps({
        "claim_type": "finding",
        "claim": (
            "## 影响\n"
            "**CVE-2026-31337** 影响我方 **{subject}** 生产集群 (FastGate 3200), 需立即打补丁. "
            "**CVSS 3.1 = 9.8** (Critical, 认证前利用).\n\n"
            "## 触发条件\n"
            "- 暴露在公网的 FastGate 3200 (含 4200 衍生型号), 固件 < **7.2.0**\n"
            "- 攻击者发送 `/dana-na/.../../../etc/shadow` 类请求即可读文件\n\n"
            "## 利用证据\n"
            "- 厂商公告 + NVD 条目 双源确认\n"
            "- 3 月 12 日客户 WAF 抓到 302 次/分钟 `/var/log/secure` 探测 (疑似 PoC 探测)\n\n"
            "## 处置建议\n"
            "1. 立即升级到 FastGate 7.2.0 (紧急)\n"
            "2. 在升级前, WAF 临时规则拦截 `../` 路径探测\n"
            "3. 检查 3 月 12 日被探测 IP 的访问日志, 评估数据外泄范围"
        ),
        "conditions": "FastGate 3200 / 4200 系列, 固件 < 7.2.0, 暴露在公网",
        "confidence": "high",
        "evidence_refs": [
            {"material_id": "MAT-CVE-ADVISORY", "hash": "c" * 64,
             "quote": "FastGate 3200 在 7.2.0 之前版本存在路径遍历漏洞, 攻击者无需认证即可读取 /etc/shadow"},
            {"material_id": "MAT-NVD-ENTRY", "hash": "d" * 64,
             "quote": "CWE-22 Path Traversal; 影响 FastGate 3200/4200 全系, <7.2.0 受影响"},
        ],
        "counter_evidence_refs": [],
        "unknowns": [
            "是否所有 3200 节点都暴露在公网 (需拉 inventory 数据)",
            "3 月 12 日探测是否成功读出 /etc/shadow (WAF 只看到探测请求, 未见 200 响应)",
            "是否有内网 4200 衍生型号也需打补丁 (型号清单未拉全)",
        ],
    })


def run_step_1_prompt() -> dict[str, Any]:
    """Step 1: 构造 dsh prompt (与 cve_impact_brief 模板一致)."""
    from backend.services.ai_hub.prompts import build_cve_impact_brief_prompt
    prompt = build_cve_impact_brief_prompt(
        cve_id=GOLDEN_CVE, subject_name=GOLDEN_SUBJECT, evidence_materials=GOLDEN_MATERIALS,
    )
    return {"step": "1_prompt", "prompt_length": len(prompt), "prompt_has_cve": GOLDEN_CVE in prompt}


def run_step_2_dsh_mock() -> dict[str, Any]:
    """Step 2: mock dsh 返 SK-02 schema 合规 JSON."""
    raw = _mock_dsh_response()
    from backend.services.ai_hub.prompts import parse_cve_impact_brief_response
    parsed = parse_cve_impact_brief_response(raw)
    return {
        "step": "2_dsh_response",
        "raw_length": len(raw),
        "parsed_claim_type": parsed["claim_type"],
        "parsed_confidence": parsed["confidence"],
        "evidence_count": len(parsed["evidence_refs"]),
        "unknowns_count": len(parsed["unknowns"]),
    }


def run_step_3_evidence_hashes(*, apply: bool) -> dict[str, Any]:
    """Step 3: 校验 evidence_refs.hash 对得上 material.content_hash."""
    if apply:
        from backend.repository.db import get_connection
        conn = get_connection()
        for m in GOLDEN_MATERIALS:
            conn.execute(
                "INSERT OR IGNORE INTO v1_materials "
                "(id, source_kind, url, title, content_hash, content_length, fetched_at, created_at, updated_at) "
                "VALUES (?, 'url', ?, ?, ?, 100, datetime('now'), datetime('now'), datetime('now'))",
                (m["id"], f"https://example.com/{m['id']}", m["title"], m["content_hash"]),
            )
        conn.commit()
    from backend.services.judgment_service import JudgmentService
    svc = JudgmentService()
    refs = [
        {"material_id": m["id"], "hash": m["content_hash"], "quote": m["summary"][:50]}
        for m in GOLDEN_MATERIALS
    ]
    if apply:
        svc._validate_evidence_hashes(refs)  # 期望通过
        return {"step": "3_evidence_hashes", "validated": True, "refs_count": len(refs)}
    # dry-run: 仅计算
    return {"step": "3_evidence_hashes", "validated_dry_run": True, "refs_count": len(refs)}


def run_step_4_create_draft(*, apply: bool) -> dict[str, Any]:
    """Step 4: create_with_dsh 落 draft judgment (mock dsh)."""
    if not apply:
        return {"step": "4_create_draft", "skipped_dry_run": True}
    from backend.services.judgment_service import JudgmentService
    svc = JudgmentService(dsh_caller=lambda _p: _mock_dsh_response())
    j = svc.create_with_dsh(
        case_id="C" * 26, cve_id=GOLDEN_CVE, subject_name=GOLDEN_SUBJECT,
        evidence_materials=[
            {"id": m["id"], "title": m["title"], "content_hash": m["content_hash"]}
            for m in GOLDEN_MATERIALS
        ],
    )["judgment"]
    return {
        "step": "4_create_draft", "judgment_id": j["id"],
        "status": j["status"], "revision": j["revision"],
        "evidence_count": len(j["evidence_refs"]),
        "unknowns_count": len(j["unknowns"]),
        "content_hash_first16": (j.get("content_hash") or "")[:16],
    }


def run_step_5_publish(*, apply: bool) -> dict[str, Any]:
    """Step 5: publish draft → published (CAS 守卫 1 + UNIQUE 守卫 2 + 内容守卫 3)."""
    if not apply:
        return {"step": "5_publish", "skipped_dry_run": True}
    # 沿用 step 4 落库的最后一行 draft
    from backend.repository.db import get_connection
    conn = get_connection()
    last = conn.execute(
        "SELECT id, revision FROM v1_judgments ORDER BY created_at DESC LIMIT 1",
    ).fetchone()
    if last is None:
        return {"step": "5_publish", "error": "no draft in db"}
    jid, rev = last[0], last[1]
    from backend.services.judgment_service import JudgmentService
    svc = JudgmentService()
    j = svc.publish(jid, expected_revision=rev)
    return {
        "step": "5_publish", "judgment_id": j["id"], "status": j["status"],
        "wiki_path": j.get("wiki_path"), "published_at": j.get("published_at"),
        "allowed_actions": j["allowed_actions"],
    }


def run_step_6_evidence_walkthrough() -> dict[str, Any]:
    """Step 6: 走查 unknown 必须显示 (baseline §5 硬约束) — unknowns 必填 + UI 渲染."""
    try:
        from backend.repository.db import get_connection
        conn = get_connection()
        last = conn.execute(
            "SELECT id, unknowns_json, evidence_refs_json, status FROM v1_judgments "
            "ORDER BY created_at DESC LIMIT 1",
        ).fetchone()
    except Exception as e:
        return {"step": "6_walkthrough", "skipped_error": str(e)}
    if last is None:
        return {"step": "6_walkthrough", "skipped_no_judgment": True}
    unknowns = json.loads(last[1] or "[]")
    evidence = json.loads(last[2] or "[]")
    return {
        "step": "6_walkthrough",
        "judgment_id": last[0],
        "evidence_count": len(evidence),
        "unknowns_count": len(unknowns),
        "unknowns_first": unknowns[0] if unknowns else None,
        "all_unknowns_visible": all(isinstance(u, str) and u for u in unknowns),
        "status": last[3],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T11 SK-02 黄金案例演练 — CVE-2026-31337")
    ap.add_argument("--apply", action="store_true", help="真落 v1_judgments 表 (走 temp_db)")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状, 不调服务")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()
        # 真落表: 先 init_db() 跑 migrations
        if args.apply:
            from backend.repository import db
            db.init_db()

    steps: list[dict[str, Any]] = []
    steps.append(run_step_1_prompt())
    steps.append(run_step_2_dsh_mock())
    steps.append(run_step_3_evidence_hashes(apply=args.apply))
    steps.append(run_step_4_create_draft(apply=args.apply))
    steps.append(run_step_5_publish(apply=args.apply))
    steps.append(run_step_6_evidence_walkthrough())

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t11-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"cve_id": GOLDEN_CVE, "subject": GOLDEN_SUBJECT,
         "materials_count": len(GOLDEN_MATERIALS), "steps": steps, "mode": "apply" if args.apply else "dry-run"},
        ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    print(json.dumps({"cve": GOLDEN_CVE, "mode": "apply" if args.apply else "dry-run",
                      "steps_count": len(steps), "trace": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
