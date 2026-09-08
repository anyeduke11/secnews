"""v085 seed: dev 库评审 fixture 自建 (t085, 沿用 t11 mock-dsh 注入先例)。

用途: v0.8.5 demo 评审 + G3 变异链提供真实数据 (spec §9 评审 fixture 政策 —
标注为评审数据, 不计入业务闭环证据)。

产物 (幂等: 已存在 v085-review-% case 时跳过, --fresh 先清本组 fixture):
  case A  v085-review-A 漏洞研判闭环   → published judgment + planned action×2
          + queued run + pending artifact + published knowledge(playbook)
  case B  v085-review-B 知识复用演练   → published judgment (队列第二项)

安全护栏: HOTSPOT_DB_PATH 必须指向 dev_data/ — 拒绝写生产库。
用法: source dev_data/dev.env && .venv/bin/python scripts/t085_seed_review_fixtures.py [--fresh]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FIX_A_TITLE_PREFIX = "v085-review-A"
FIX_B_TITLE_PREFIX = "v085-review-B"
CVE = "CVE-2026-31337"
SUBJECT = "某 SSL VPN 网关 (FastGate 3200)"
MATS = [
    {"id": "MAT-V085-ADV", "title": "厂商公告 — FastGate 3200 任意文件读取", "content_hash": "a" * 64},
    {"id": "MAT-V085-NVD", "title": "NVD CVE-2026-31337 条目", "content_hash": "b" * 64},
]


def _guard() -> None:
    db = os.environ.get("HOTSPOT_DB_PATH", "")
    if "dev_data" not in db:
        raise SystemExit(
            f"拒绝: HOTSPOT_DB_PATH={db or '(未设置)'} 不在 dev_data/ 下 — "
            "本脚本只允许写开发库。用法: source dev_data/dev.env && .venv/bin/python scripts/t085_seed_review_fixtures.py"
        )


def _mock_sk02(_prompt: str) -> str:
    return json.dumps({
        "claim_type": "finding",
        "claim": "## 影响\n**CVE-2026-31337** 影响 FastGate 3200 生产集群 (CVSS 9.8, 认证前利用)。\n\n## 处置建议\n1. 升级 7.2.0\n2. WAF 拦截 `../` 探测",
        "conditions": "FastGate 3200/4200 系列, 固件 < 7.2.0, 暴露公网",
        "confidence": "high",
        "evidence_refs": [
            {"material_id": MATS[0]["id"], "hash": MATS[0]["content_hash"], "quote": "7.2.0 之前版本存在路径遍历漏洞"},
            {"material_id": MATS[1]["id"], "hash": MATS[1]["content_hash"], "quote": "官方确认在野利用; 修复版本 7.2.0"},
        ],
        "counter_evidence_refs": [],
        "unknowns": ["3200 节点公网暴露面未拉通 inventory", "3 月探测是否成功读文件未确认"],
    })


def _mock_sk03(_prompt: str) -> str:
    return json.dumps({
        "plan": "1. 核对 FastGate 3200 inventory 固件版本\n2. 检索 WAF 日志 `../` 探测\n3. 产出排查报告",
        "expected_artifacts": ["排查报告.md"],
        "success_criteria": "inventory 覆盖 100%; 报告含暴露面清单 (字符串, 服务层 .encode 校验)",
        "tool_versions": {"inventory": "1.0", "waf-export": "2.3"},
        "unknowns": ["4200 衍生型号清单未拉全"],
    })


def _mock_sk04(_prompt: str) -> str:
    review_at = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()
    return json.dumps({
        "title": "FastGate 3200 路径遍历应急处置手册 (v085 评审 fixture)",
        "body": "## 原理\n认证前路径遍历读敏感文件。\n\n## 步骤\n1. 拉固件版本\n2. WAF 规则拦截\n3. 复盘外泄面\n\n## 适用边界\n仅 3200/4200 < 7.2.0。",
        "prerequisites": ["设备为 FastGate 3200/4200 系列", "固件版本 < 7.2.0"],
        "counter_examples": ["已升级 ≥ 7.2.0 的设备不适用"],
        "evidence_refs": [
            {"material_id": MATS[0]["id"], "hash": MATS[0]["content_hash"], "quote": "7.2.0 之前版本存在路径遍历漏洞"},
        ],
        "review_at": review_at,
        "expiry_at": None,
    })


def _seed_materials() -> None:
    from backend.repository.db import get_connection
    conn = get_connection()
    for m in MATS:
        conn.execute(
            "INSERT OR IGNORE INTO v1_materials "
            "(id, source_kind, url, title, content_hash, content_length, fetched_at, created_at, updated_at) "
            "VALUES (?, 'url', ?, ?, ?, 120, datetime('now'), datetime('now'), datetime('now'))",
            (m["id"], f"https://example.com/{m['id']}", m["title"], m["content_hash"]),
        )
    conn.commit()


def _http_create_case(title: str, question: str, base: str) -> dict:
    import urllib.request
    req = urllib.request.Request(
        f"{base}/api/v1/cases", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"title": title, "question": question, "priority": "p1", "source": "manual"}).encode(),
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["item"]


def _existing_fixture() -> bool:
    from backend.repository.db import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM v1_cases WHERE title LIKE 'v085-review-%'"
    ).fetchone()
    return bool(row and row[0])


def _clear_fixture() -> None:
    # 结构化清理需逐关联表反查 (judgment/action/run/artifact/knowledge + 关联表);
    # demo fixture 体量小且可共存, 这里只提示不删 — 避免误伤业务行。
    print("[seed] --fresh: 未自动删除 (关联清理需逐表反查)。"
          "如需彻底重置, 手工清理 dev_data/db/hotspot.db 中 v085-review-% 关联行。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fresh", action="store_true", help="已存在 fixture 时仅提示 (关联清理需手工)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    args = parser.parse_args()

    _guard()
    # P1 修复 (代码审查 #3): 与姊妹脚本同款生产端口拒绝 — HTTP 写入与直连写必须都护栏
    if args.base_url.rstrip("/").endswith(":8000"):
        raise SystemExit("拒绝: --base-url 指向生产端口 :8000 — 本脚本只允许写 dev 环境 (8766)。")
    if _existing_fixture():
        if args.fresh:
            _clear_fixture()
        print("[seed] 已存在 v085-review-% fixture — 跳过 (幂等)。如需重建请手工清理 dev 库。")
        return 0

    _seed_materials()

    # ── case A: 完整闭环 ──────────────────────────────────────────
    case_a = _http_create_case(
        f"{FIX_A_TITLE_PREFIX} 漏洞研判闭环",
        "CVE-2026-31337 对 FastGate 3200 生产集群的影响研判与排查材料产出 (评审 fixture)",
        args.base_url,
    )
    from backend.services.judgment_service import JudgmentService
    from backend.services.action_service import ActionService
    from backend.services.run_service import RunService
    from backend.services.artifact_service import ArtifactService
    from backend.services.knowledge_service import KnowledgeService

    ev_materials = [{"id": m["id"], "title": m["title"], "content_hash": m["content_hash"]} for m in MATS]

    j = JudgmentService(dsh_caller=_mock_sk02).create_with_dsh(
        case_id=case_a["id"], cve_id=CVE, subject_name=SUBJECT, evidence_materials=ev_materials,
    )["judgment"]
    jp = JudgmentService().publish(j["id"], expected_revision=j["revision"])
    print(f"[seed] judgment published: {jp['id']} rev={jp['revision']}")

    a1 = ActionService(dsh_caller=_mock_sk03).create_with_dsh(
        case_id=case_a["id"], judgment_id=jp["id"], title="FastGate 排查材料产出 (演练)",
        subject_name=SUBJECT, cve_id=CVE, scope="生产集群 FastGate 3200 全量 inventory + WAF 日志",
        evidence_materials=ev_materials,
    )
    a2 = ActionService(dsh_caller=_mock_sk03).create_with_dsh(
        case_id=case_a["id"], judgment_id=jp["id"], title="外泄面复盘 (演练, 待批准)",
        subject_name=SUBJECT, cve_id=CVE, scope="3 月被探测 IP 的访问日志回溯",
        evidence_materials=ev_materials,
    )
    print(f"[seed] actions planned: {a1['action']['id']}, {a2['action']['id']}")

    run = RunService().create_or_replay(
        action_id=a1["action"]["id"], idempotency_key="v085-seed-run-1", attempt=1,
        protocol="direct", trigger_source="user",
    )
    print(f"[seed] run: {run['run']['id']} status={run['run']['status']}")

    seed_dir = Path(os.environ.get("HOTSPOT_DATA_DIR", REPO_ROOT / "dev_data" / "data")) / "v085_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    content = "# FastGate 3200 排查报告 (v085 评审 fixture)\n\n- inventory: 12 台, 9 台 < 7.2.0\n- WAF: `../` 探测 302/min, 已封禁\n- 结论: 需紧急升级\n"
    ref = seed_dir / f"{run['run']['id']}.md"
    ref.write_text(content, encoding="utf-8")
    art = ArtifactService().create(
        run_id=run["run"]["id"], kind="report", title="FastGate 排查报告.md",
        content=content, format="md", content_ref=str(ref),
    )
    print(f"[seed] artifact pending: {art['id']}")

    k = KnowledgeService(dsh_caller=_mock_sk04).create_with_dsh(
        case_id=case_a["id"], judgment_id=jp["id"], action_id=a1["action"]["id"],
        subject_name=SUBJECT, cve_id=CVE, kind="playbook", evidence_materials=ev_materials,
    )["knowledge"]
    kp = KnowledgeService().publish(k["id"], expected_revision=k["revision"])
    print(f"[seed] knowledge published: {kp['id']} (review_at={kp.get('review_at')})")

    # ── case B: 队列第二项 ────────────────────────────────────────
    case_b = _http_create_case(
        f"{FIX_B_TITLE_PREFIX} 知识复用演练",
        "第二个同类事项: 验证 SK-05 经验召回与采用回执 (评审 fixture)",
        args.base_url,
    )
    j2 = JudgmentService(dsh_caller=_mock_sk02).create_with_dsh(
        case_id=case_b["id"], cve_id=CVE, subject_name=SUBJECT, evidence_materials=ev_materials,
    )["judgment"]
    JudgmentService().publish(j2["id"], expected_revision=j2["revision"])

    print("=" * 60)
    print("[seed] 完成 — 评审 fixture (spec §9, 不计业务闭环证据):")
    print(f"  case A = {case_a['id']}  (judgment published + action×2 planned + run + artifact pending + knowledge published)")
    print(f"  case B = {case_b['id']}  (judgment published)")
    print("  下一步: python scripts/t085_golden_walkthrough.py --base-url http://127.0.0.1:8766")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
