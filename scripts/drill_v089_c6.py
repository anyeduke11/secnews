#!/usr/bin/env python3
"""v0.8.9 试点演练⑤ — 运营型 case 关闭全链 (P6 C6-1 验收)。

与演练① 的差别: 那条是「研究型 published judgment 旁路」(无 action); 本演练走
**运营型全链** — case → judgment(published) → action(approved) → run(pi 边界执行)
→ artifact(verify+accept) → action finish → case close, 四守卫 (a)(b)(c)(d) 全过。

同时做四处**反向取证** (证明四守卫各自是活的, 而非被绕过):
- N1: action running 时 close → 守卫 (a) 必须拦;
- N2: action 终态但 artifact 仍 pending 时 close → 守卫 (c) 必须拦;
- N3: 无 published judgment 的 case(无 action) → 守卫 (d) 必须拦;
- N4: action cancelled 但名下 run 仍 queued → 守卫 (b) 必须拦。

用法::

    HOTSPOT_DB_PATH=/tmp/v089_drill5/hotspot.db \\
    HOTSPOT_DATA_DIR=/tmp/v089_drill5_data \\
    HOTSPOT_PI_EXECUTOR_ENABLED=true \\
    python scripts/drill_v089_c6.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WS = "workspace/p6-drill"
RUN_TAG = "c6drill"


def _setup_workspace() -> None:
    ws = ROOT / WS
    (ws / "out").mkdir(parents=True, exist_ok=True)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "input.txt").write_text(
        "CVE-2024-0000 暴露面基线材料\n", encoding="utf-8")


def _plan(commands: list[list[str]]) -> dict:
    return {
        "status": "approved",
        "submitted_by": "drill",
        "plan": {
            "commands": commands,
            "writable_paths": ["out"],
            "readable_paths": ["src"],
            "network": [],
            "command_timeout_sec": 30,
            "total_timeout_sec": 120,
            "output_artifact": {
                "kind": "report", "title": "P6 运营型关闭演练产物",
                "acceptance_notes": "",
            },
        },
    }


def _artifact_of(run_id: str) -> dict:
    from backend.repository.db import get_connection

    row = get_connection().execute(
        "SELECT id, status, content_hash, content_ref, revision "
        "FROM v1_artifacts WHERE run_id = ? ORDER BY id DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    return dict(row) if row else {}


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _case_revision(case_id: str) -> int:
    from backend.services.case_service import CaseService

    return CaseService().get_case(case_id).revision


def _main() -> int:
    from backend.config import config
    from backend.repository.db import get_connection, init_db

    if not config.pi_executor_enabled:
        print("FATAL: HOTSPOT_PI_EXECUTOR_ENABLED 未开启", file=sys.stderr)
        return 2

    init_db()
    _setup_workspace()

    from backend.services.action_service import ActionService
    from backend.services.artifact_service import ArtifactService
    from backend.services.case_service import CaseService
    from backend.services.execution_runner import runner as runner_mod
    from backend.services.judgment_service import JudgmentService
    from backend.services.run_service import RunService

    report: dict = {"steps": []}

    def step(name: str, fn) -> None:
        out = fn()
        report["steps"].append({"name": name, **out})
        print(f"[{name}] {json.dumps(out, ensure_ascii=False)}")

    # ── 1. 建 case ────────────────────────────────────────────────────
    case = CaseService().create_case(
        title="P6 演练⑤ 运营型关闭",
        question="CVE-2024-0000 暴露面是否可收敛?",
        goal="走完整 run/artifact 链后合法关闭",
        scope="drill",
        client_request_id=f"{RUN_TAG}-{os.getpid()}",
    )
    case_id = case.id

    # ── 2. judgment draft → published (守卫 d 的前置) ──────────────────
    def step_judgment():
        svc = JudgmentService()
        inserted = svc._insert_draft(
            case_id=case_id,
            parsed={
                "claim_type": "assessment",
                "claim": "该暴露面可在边界内收敛 (演练用结论)",
                "conditions": "仅在 plan 审批范围内成立",
                "confidence": 0.6,
                "evidence_refs": [str(ROOT / WS / "src" / "input.txt")],
                "unknowns": ["真实环境未验证"],
            },
            submitted_by="drill",
        )
        published = svc.publish(inserted["judgment"]["id"], expected_revision=1)
        return {"judgment_id": published["id"], "status": published["status"]}

    step_judgment()
    jrow = get_connection().execute(
        "SELECT id, status FROM v1_judgments WHERE case_id = ? ORDER BY created_at DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    judgment_id, judgment_status = jrow[0], jrow[1]
    print(f"[judgment] {judgment_id} status={judgment_status}")

    # ── 3. action planned → approved ──────────────────────────────────
    a_svc = ActionService()
    action = a_svc._insert_planned(
        case_id=case_id, judgment_id=judgment_id,
        title="P6 演练⑤ 边界内只读汇总",
        scope="drill",
        plan="在审批 plan 内读取 src/input.txt 并输出汇总",
        tool_versions={"python": sys.version.split()[0]},
        expected_artifacts=["report/md"],
        success_criteria="stdout 非空且落盘 hash 一致",
        unknowns=[],
        submitted_by="drill",
    )["action"]
    action = a_svc.approve(action["id"], expected_revision=1, approved_by="drill")

    # ── 4. action start → run (queued) ────────────────────────────────
    started = a_svc.start(
        action["id"], expected_revision=action["revision"],
        idempotency_key=f"{RUN_TAG}-start-{os.getpid()}", protocol="pi",
    )
    run_id = started["run"]["id"]

    # ── N1: action running 时 close → 守卫 (a) 必须拦 ──────────────────
    def step_guard_a():
        try:
            CaseService().close_case(case_id, expected_revision=_case_revision(case_id))
        except Exception as e:  # noqa: BLE001 — 演练取证, 只关心拦截事实
            return {"blocked": True, "type": type(e).__name__,
                    "message": str(e)[:220],
                    "guard_a_active": "active action" in str(e)}
        return {"blocked": False}

    step("N1-守卫a拦截", step_guard_a)

    # ── 5. run claim → start → pi 边界执行 → artifact 自动登记 ─────────
    r_svc = RunService()
    r_svc.claim(run_id, executor="pi")
    r_svc.start(run_id)

    py = sys.executable
    result = runner_mod.execute_and_settle(
        run_id,
        _plan([[py, "-c", "print(open('src/input.txt').read().strip())"]]),
        workspace=WS,
    )
    artifact = _artifact_of(run_id)
    rrow = get_connection().execute(
        "SELECT status, outcome, error FROM v1_runs WHERE id = ?", (run_id,)).fetchone()
    run_row = dict(rrow) if rrow else {}
    print(f"[run] {run_id} ok={result.ok} reason={result.reason_code} "
          f"run={run_row} artifact={artifact.get('id')}@{artifact.get('status')}")

    # ── 6. action finish(succeeded) (守卫 a 的前置) ────────────────────
    a_row = get_connection().execute(
        "SELECT revision FROM v1_actions WHERE id = ?", (action["id"],)).fetchone()
    a_svc.finish(action["id"], expected_revision=a_row[0], succeeded=True)

    # ── N2: artifact 仍 pending 时 close → 守卫 (c) 必须拦 ─────────────
    def step_guard_c():
        try:
            CaseService().close_case(case_id, expected_revision=_case_revision(case_id))
        except Exception as e:  # noqa: BLE001
            return {"blocked": True, "type": type(e).__name__,
                    "message": str(e)[:220],
                    "guard_c_active": "no verified/accepted artifact" in str(e)}
        return {"blocked": False}

    step("N2-守卫c拦截", step_guard_c)

    # ── 7. artifact verify → accept (守卫 c 的前置) ────────────────────
    eff_hash = _sha256_of(artifact["content_ref"])
    ar_svc = ArtifactService()
    ar_svc.verify(artifact["id"], verified_by="drill")
    accepted = ar_svc.accept(artifact["id"], accepted_by="drill",
                             accepted_note="演练⑤ 落盘 hash 一致")

    # ── 7.5 绑定证据材料 (C6-2 前置: 复盘起草要求 case 有证据) ──────────
    def step_bind_evidence():
        from backend.repository.v1_evidence_repo import V1EvidenceRepository

        src = (ROOT / WS / "src" / "input.txt").read_bytes()
        mid = f"mat-{RUN_TAG}-{os.getpid()}"
        h = hashlib.sha256(src).hexdigest()
        V1EvidenceRepository().insert_material(
            {"id": mid, "source_kind": "file",
             "url": f"file://{ROOT / WS / 'src' / 'input.txt'}",
             "title": "CVE-2024-0000 暴露面基线材料",
             "content_hash": h, "content_length": len(src),
             "content_ref": str(ROOT / WS / "src" / "input.txt"),
             "summary": "演练⑤ 证据材料"},
            entity_id=mid, body_hash=h,
        )
        conn = get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO v1_case_materials (case_id, material_id) VALUES (?, ?)",
            (case_id, mid),
        )
        conn.commit()
        return {"material_id": mid, "content_hash": h}

    step("7.5-绑定证据材料", step_bind_evidence)

    # ── 8. case close → 四守卫全过 ─────────────────────────────────────
    closed = CaseService().close_case(case_id, expected_revision=_case_revision(case_id))
    t_close = time.monotonic()  # 演练⑥ 计时起点: 关闭 → 复盘提案出现

    # ── 9. 对账 ───────────────────────────────────────────────────────
    outbox = get_connection().execute(
        "SELECT event_type, COUNT(*) FROM v1_outbox WHERE trace_id IS NOT NULL "
        "AND aggregate_id IN (?, ?, ?) GROUP BY event_type",
        (run_id, artifact["id"], action["id"]),
    ).fetchall()

    # ── 10. 演练⑥ C6-2: v1_case_closed → 复盘提案 (事件直连) ────────────
    def step_case_closed_event():
        n = get_connection().execute(
            "SELECT COUNT(*) FROM v1_outbox "
            "WHERE event_type = 'v1_case_closed' AND aggregate_id = ?",
            (case_id,),
        ).fetchone()[0]
        if n != 1:
            raise AssertionError(f"expected 1 v1_case_closed event, got {n}")
        return {"events": n}

    def _stub_drafter(context: dict) -> dict:
        """演练桩: 不依赖 dsh/ai_hub, 只验证 glue 链 (人主律不变)。"""
        return {
            "title": "复盘: CVE-2024-0000 暴露面收敛",
            "summary": "边界内只读汇总成功, 暴露面已按 plan 收敛。",
            "lessons": ["先收敛暴露面, 再复核依赖面"],
            "next_actions": ["下季度复测该边界"],
            "evidence_refs": [str(m.get("id")) for m in context.get("evidence") or []],
        }

    def step_retro_dispatch():
        import asyncio

        from backend.services.outbox_dispatcher import OutboxDispatcher
        from backend.services.retrospective_service import register as register_retro

        disp = OutboxDispatcher()
        register_retro(disp, drafter=_stub_drafter)

        async def _pump() -> int:
            n = await disp.flush_once()
            await asyncio.gather(*list(disp._handler_tasks), return_exceptions=True)
            return n

        broadcast = asyncio.run(_pump())
        row = get_connection().execute(
            "SELECT id, status, kind, source, created_at FROM v1_proposals "
            "WHERE case_id = ? ORDER BY created_at DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        if row is None:
            raise AssertionError("no retrospective proposal created")
        latency = time.monotonic() - t_close
        return {"broadcast": broadcast, "proposal_id": row["id"], "status": row["status"],
                "kind": row["kind"], "source": row["source"],
                "latency_sec": round(latency, 3)}

    def step_approve_draft():
        pid = _step_of("C6-2-复盘提案")["proposal_id"]
        from backend.services.run_ledger_service import RunLedgerService

        RunLedgerService().approve_proposal(pid, reviewed_by="drill-human")
        frow = get_connection().execute(
            "SELECT status, outcome FROM v1_runs WHERE idempotency_key = ?",
            (f"proposal:{pid}",),
        ).fetchone()
        krow = get_connection().execute(
            "SELECT id, status, kind, title FROM v1_knowledge "
            "ORDER BY created_at DESC LIMIT 1",
        ).fetchone()
        if krow is None:
            raise AssertionError("no v1_knowledge draft materialized")
        return {"fork_run": dict(frow) if frow else {}, "knowledge_id": krow["id"],
                "status": krow["status"], "kind": krow["kind"], "title": krow["title"]}

    def step_publish_recall():
        kid = _step_of("C6-2-批准→知识草案")["knowledge_id"]
        from backend.services.knowledge_reuse import auto_recall_for_case
        from backend.services.knowledge_service import KnowledgeService

        pub = KnowledgeService().publish(kid, expected_revision=1)
        hits = auto_recall_for_case(
            {"title": "CVE-2024-0000 暴露面复测", "question": "同类暴露面是否复发?"},
            limit=5,
        )
        recalled = [h["id"] for h in hits]
        if kid not in recalled:
            raise AssertionError(f"knowledge {kid} not recalled; hits={recalled}")
        return {"publish_status": pub.get("status"), "recall_hits": recalled}

    def _step_of(name: str) -> dict:
        for s in report["steps"]:
            if s.get("name") == name:
                return s
        raise AssertionError(f"step {name} not found")

    step("C6-2-关闭事件落账", step_case_closed_event)
    step("C6-2-复盘提案", step_retro_dispatch)
    step("C6-2-批准→知识草案", step_approve_draft)
    step("C6-2-发布→同类召回", step_publish_recall)

    # ── N3: 无 published judgment 的 case → 守卫 (d) 必须拦 ─────────────
    # 无 action → 守卫 (c) 跳过, 前置 (a)(b) 天然通过, 直抵 (d)。
    def step_guard_d():
        c = CaseService().create_case(
            title="P6 演练⑤ N3 无 published judgment",
            question="守卫 (d) 是否拦?",
            scope="drill",
            client_request_id=f"{RUN_TAG}-n3-{os.getpid()}",
        )
        try:
            CaseService().close_case(c.id, expected_revision=c.revision)
        except Exception as e:  # noqa: BLE001
            return {"case_id": c.id, "blocked": True, "type": type(e).__name__,
                    "message": str(e)[:220],
                    "guard_d_active": "no published judgment" in str(e)}
        return {"case_id": c.id, "blocked": False}

    # ── N4: action cancelled 但名下 run 仍 queued → 守卫 (b) 必须拦 ──────
    # cancel 不级联 run (源码 L343-359), 故 action 已终态而 run 仍 active —
    # 这是唯一能在合法通道下让 (a) 过、(b) 拦的组合。
    def step_guard_b():
        c = CaseService().create_case(
            title="P6 演练⑤ N4 active run",
            question="守卫 (b) 是否拦?",
            scope="drill",
            client_request_id=f"{RUN_TAG}-n4-{os.getpid()}",
        )
        j = JudgmentService()._insert_draft(
            case_id=c.id,
            parsed={"claim_type": "assessment", "claim": "演练用结论",
                    "conditions": "drill", "confidence": 0.5,
                    "evidence_refs": [], "unknowns": ["N4 不执行"]},
            submitted_by="drill",
        )
        JudgmentService().publish(j["judgment"]["id"], expected_revision=1)
        a = a_svc._insert_planned(
            case_id=c.id, judgment_id=j["judgment"]["id"],
            title="P6 演练⑤ N4 计划内动作", scope="drill",
            plan="只用于制造 active run", tool_versions={},
            expected_artifacts=["report/md"], success_criteria="n/a",
            unknowns=[], submitted_by="drill",
        )["action"]
        a = a_svc.approve(a["id"], expected_revision=1, approved_by="drill")
        started = a_svc.start(
            a["id"], expected_revision=a["revision"],
            idempotency_key=f"{RUN_TAG}-n4-start-{os.getpid()}", protocol="pi",
        )
        a_svc.cancel(started["action"]["id"],
                     expected_revision=started["action"]["revision"],
                     reason="drill N4: 制造 action 终态 + run active")
        try:
            CaseService().close_case(c.id, expected_revision=c.revision)
        except Exception as e:  # noqa: BLE001
            return {"case_id": c.id, "blocked": True, "type": type(e).__name__,
                    "message": str(e)[:220],
                    "guard_b_active": "active run" in str(e)}
        return {"case_id": c.id, "blocked": False}

    step("N3-守卫d拦截", step_guard_d)
    step("N4-守卫b拦截", step_guard_b)

    c62 = {s["name"]: s for s in report["steps"] if s["name"].startswith("C6-2-")}
    draft = c62["C6-2-复盘提案"]
    kb = c62["C6-2-批准→知识草案"]
    pub = c62["C6-2-发布→同类召回"]

    report["entities"] = {
        "case_id": case_id, "case_status": closed.status,
        "judgment_id": judgment_id, "judgment_status": judgment_status,
        "action_id": action["id"], "run_id": run_id,
        "artifact_id": artifact["id"], "artifact_status": accepted["status"],
        "content_hash": artifact["content_hash"], "disk_sha256": eff_hash,
        "hash_match": artifact["content_hash"] == eff_hash,
        "outbox": {r[0]: r[1] for r in outbox},
        "c6_2": {
            "closed_event": c62["C6-2-关闭事件落账"]["events"],
            "proposal_id": draft["proposal_id"], "proposal_status": draft["status"],
            "latency_sec": draft["latency_sec"],
            "knowledge_id": kb["knowledge_id"], "knowledge_status": kb["status"],
            "knowledge_kind": kb["kind"],
            "publish_status": pub["publish_status"],
            "recalled": kb["knowledge_id"] in pub["recall_hits"],
        },
    }
    print("\n=== 演练⑤⑥ 汇总 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    guards = {s["name"]: bool(s.get("blocked"))
              for s in report["steps"] if s["name"].startswith("N")}
    ok = (
        closed.status == "closed"
        and run_row.get("outcome") == "done"
        and accepted["status"] == "accepted"
        and artifact["content_hash"] == eff_hash
        and all(guards.values()) and len(guards) == 4
        # 演练⑥ 三断言: 30s 内起草 · 人批准产 draft · publish 后同类可召回
        and draft["status"] == "draft" and draft["latency_sec"] < 30
        and kb["status"] == "draft" and pub["publish_status"] == "published"
    )
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())