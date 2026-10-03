"""P1-1/M1 Run 账本 + 提案审批循环测试。

覆盖 PRD 用例 A 的后端契约:
- v1_runs 扩列 / v1_proposals / command_log 迁移落地;
- 提案 draft→approved 双签 Run (outcome=done, policy_version 冻结);
- 驳回原因必填 ≤200;
- LLM 超时/拒绝 → proposal failed, payload 空 (无默认值污染);
- payload 64KB 双闸 (service 校验 + DDL CHECK);
- outcome 枚举终判 needs_human/failed (供 pi/artifact 后续消费)。
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.repository.db import get_connection
from backend.services.run_ledger_service import (
    LEDGER_OUTCOMES,
    ProposalConflictError,
    ProposalValidationError,
    RunLedgerService,
)
from backend.version import APP_VERSION


@pytest.fixture
def svc(temp_db) -> RunLedgerService:
    return RunLedgerService()


# ── 1. 迁移落地 ─────────────────────────────────────────────────────
def test_migration_131_schema(temp_db):
    conn = get_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(v1_runs)")}
    assert {"plan_json", "policy_version", "outcome"} <= cols
    props = {r[1] for r in conn.execute("PRAGMA table_info(v1_proposals)")}
    assert {
        "id", "case_id", "source", "kind", "payload_json", "evidence_ids_json",
        "prompt_version", "status", "error_msg", "reject_reason",
        "reviewed_by", "reviewed_at", "run_id", "created_at",
    } <= props
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='command_log'"
    ).fetchone()[0] == 1


def test_legacy_runs_have_null_outcome(temp_db):
    """历史 v1_runs 行 outcome 可空 (迁移不回填伪结论)。"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_runs (id, action_id, protocol, trigger_source, idempotency_key) "
        "VALUES ('run_LEGACY', 'act1', 'direct', 'user', 'k1')"
    )
    conn.commit()
    row = conn.execute(
        "SELECT outcome, plan_json FROM v1_runs WHERE id='run_LEGACY'"
    ).fetchone()
    assert row[0] is None and row[1] == "{}"


# ── 2. 创建 / 查询 ──────────────────────────────────────────────────
def test_create_and_get_draft(svc):
    p = svc.create_proposal(
        source="agent", kind="judgment_draft",
        payload={"claim": "X 可能存在 RCE", "confidence": 0.7},
        evidence_ids=["ev_1", "ev_2"], prompt_version="judg@2026-10-02",
        case_id="case_1",
    )
    assert p["status"] == "draft"
    assert p["source"] == "agent"
    assert p["evidence_ids"] == ["ev_1", "ev_2"]
    assert p["prompt_version"] == "judg@2026-10-02"
    assert p["run_id"] is None

    items, total = svc.list_proposals(status="draft")
    assert total == 1 and items[0]["id"] == p["id"]


@pytest.mark.parametrize("field,bad", [("source", "human"), ("kind", "freeform")])
def test_create_rejects_bad_enum(svc, field, bad):
    kwargs = {"source": "agent", "kind": "report", "payload": {}}
    kwargs[field] = bad
    with pytest.raises(ProposalValidationError, match=f"invalid {field}"):
        svc.create_proposal(**kwargs)


def test_payload_over_64kb_rejected_by_service(svc):
    big = {"blob": "x" * 70_000}
    with pytest.raises(ProposalValidationError, match="payload_json too large"):
        svc.create_proposal(source="agent", kind="report", payload=big)


def test_payload_check_constraint_is_second_gate(temp_db):
    """DDL CHECK 独立兜底: 绕过 service 直插超长 payload 必须被库拒绝。"""
    conn = get_connection()
    oversized = json.dumps({"blob": "y" * 70_000})
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO v1_proposals (id, source, kind, payload_json) "
            "VALUES ('prop_BAD', 'agent', 'report', ?)",
            (oversized,),
        )


# ── 3. 审批循环 (用例 A 主路径) ─────────────────────────────────────
def test_approve_creates_done_run_with_frozen_policy(svc):
    # kind=report 走"采纳即 done"即时路径 (judgment_draft 的产物化路径见 §8)
    p = svc.create_proposal(
        source="agent", kind="report",
        payload={"claim": "CVE-X 可利用"}, evidence_ids=["ev_9"],
    )
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")

    assert approved["status"] == "approved"
    assert approved["reviewed_by"] == "owner"
    assert approved["reviewed_at"] is not None
    run_id = approved["run_id"]
    assert run_id and run_id.startswith("run_")

    run = svc.runs.get(run_id)
    assert run["outcome"] == "done"
    assert run["status"] == "succeeded"
    assert run["policy_version"] == APP_VERSION  # 执行时刻冻结
    assert run["plan"]["dual_sign"] == ["human", "agent"]  # 双签
    assert run["action_id"] == f"proposal:{p['id']}"
    assert run["inputs"] == {"claim": "CVE-X 可利用"}


def test_approve_with_edited_payload(svc):
    """人修订后批准 → run 落修订内容, 不是 AI 原稿。"""
    p = svc.create_proposal(
        source="agent", kind="knowledge_draft", payload={"v": "ai-original"},
    )
    approved = svc.approve_proposal(
        p["id"], reviewed_by="owner", payload={"v": "human-edited"},
    )
    run = svc.runs.get(approved["run_id"])
    assert run["inputs"] == {"v": "human-edited"}


def test_approve_twice_conflicts(svc):
    p = svc.create_proposal(source="command", kind="case_suggestion", payload={})
    svc.approve_proposal(p["id"], reviewed_by="owner")
    with pytest.raises(ProposalConflictError, match="only draft"):
        svc.approve_proposal(p["id"], reviewed_by="owner")


def test_approve_requires_reviewer(svc):
    p = svc.create_proposal(source="agent", kind="report", payload={})
    with pytest.raises(ProposalValidationError, match="reviewed_by"):
        svc.approve_proposal(p["id"], reviewed_by="  ")


# ── 4. 驳回 ─────────────────────────────────────────────────────────
def test_reject_requires_reason(svc):
    p = svc.create_proposal(source="agent", kind="report", payload={})
    with pytest.raises(ProposalValidationError, match="reject reason is required"):
        svc.reject_proposal(p["id"], reviewed_by="owner", reason="")


def test_reject_reason_max_200(svc):
    p = svc.create_proposal(source="agent", kind="report", payload={})
    with pytest.raises(ProposalValidationError, match="too long"):
        svc.reject_proposal(p["id"], reviewed_by="owner", reason="x" * 201)


def test_reject_happy_path(svc):
    p = svc.create_proposal(source="copilot", kind="case_suggestion", payload={})
    out = svc.reject_proposal(p["id"], reviewed_by="owner", reason="证据不足")
    assert out["status"] == "rejected"
    assert out["reject_reason"] == "证据不足"
    assert out["run_id"] is None  # 驳回不产生 Run


# ── 5. LLM 失败显式化 (用例 A②) ─────────────────────────────────────
def test_failed_proposal_is_explicit_and_unpolluted(svc):
    p = svc.record_failed_proposal(
        source="agent", kind="judgment_draft",
        error="ReadTimeout: The read operation timed out",
        prompt_version="judg@2026-10-02",
    )
    assert p["status"] == "failed"
    assert "ReadTimeout" in p["error_msg"]
    assert p["payload"] == {}           # 无默认值/无伪内容
    assert p["evidence_ids"] == []
    # 失败项可在收件箱按状态查到 (可重试的前提)
    failed, total = svc.list_proposals(status="failed")
    assert total == 1 and failed[0]["id"] == p["id"]


def test_failed_proposal_requires_error(svc):
    with pytest.raises(ProposalValidationError, match="error is required"):
        svc.record_failed_proposal(source="agent", kind="report", error=" ")


# ── 6. Run outcome 终判 ─────────────────────────────────────────────
def test_finish_run_enum_and_persistence(svc):
    p = svc.create_proposal(source="agent", kind="case_suggestion", payload={})
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")
    run = svc.finish_run(
        approved["run_id"], "needs_human", reason="pi executor unavailable",
    )
    assert run["outcome"] == "needs_human"
    assert run["reason"] == "pi executor unavailable"

    with pytest.raises(ProposalValidationError, match="invalid outcome"):
        svc.finish_run(approved["run_id"], "bogus")


def test_ledger_outcome_enum_matches_prd():
    assert {
        "done", "failed", "cancelled", "timeout", "needs_human",
    } == LEDGER_OUTCOMES


# ── 7. HTTP 冒烟 ────────────────────────────────────────────────────
def test_api_proposal_approve_flow(e2e_api_client):
    client = e2e_api_client
    r = client.post("/api/proposals", json={
        "source": "agent", "kind": "report",
        "payload": {"claim": "api smoke"}, "evidence_ids": ["e1"],
    })
    assert r.status_code == 200
    pid = r.json()["id"]

    assert client.get(f"/api/proposals/{pid}").status_code == 200
    listed = client.get("/api/proposals?status=draft").json()
    assert listed["total"] == 1

    r = client.post(f"/api/proposals/{pid}/approve", json={"reviewed_by": "owner"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["run_id"]


def test_api_reject_missing_reason_400(e2e_api_client):
    client = e2e_api_client
    r = client.post("/api/proposals", json={
        "source": "agent", "kind": "report", "payload": {},
    })
    pid = r.json()["id"]
    r = client.post(f"/api/proposals/{pid}/reject", json={"reviewed_by": "owner"})
    assert r.status_code == 400


def test_api_approve_unknown_404(e2e_api_client):
    r = e2e_api_client.post(
        "/api/proposals/prop_DOESNOTEXIST/approve", json={"reviewed_by": "owner"},
    )
    assert r.status_code == 404


# ── 8. 切片 2: AI 起草 + 研判产物物化 (用例 A① + 异常流) ────────────
def _bind_case_evidence(case_id: str, *materials: dict) -> None:
    """最小证据夹具: v1_materials + v1_case_materials 绑定 (含 Source url)。"""
    from backend.repository.v1_evidence_repo import V1EvidenceRepository
    repo = V1EvidenceRepository()
    conn = get_connection()
    for m in materials:
        repo.insert_material(
            {"id": m["id"], "url": m["url"], "title": m.get("title", m["id"]),
             "summary": m.get("summary", ""), "content_hash": m.get(
                 "content_hash", "0" * 64)},
            entity_id=m["id"], body_hash=m.get("content_hash", "0" * 64),
        )
        conn.execute(
            "INSERT INTO v1_case_materials (case_id, material_id) VALUES (?, ?)",
            (case_id, m["id"]),
        )
    conn.commit()


def _good_drafter(ctx):
    return {"claim": "存在公开 PoC 且补丁缺失", "conditions": "服务暴露于边界",
            "confidence": "high", "unknowns": ["内网横向条件未知"]}


def test_draft_judgment_success_binds_evidence_and_prompt(svc):
    _bind_case_evidence("case_A", {
        "id": "mat_1", "url": "https://src.example.com/advisory/1",
        "title": "厂商公告", "summary": "补丁未发布",
    })
    p = svc.draft_judgment("case_A", drafter=_good_drafter)
    assert p["status"] == "draft"
    assert p["kind"] == "judgment_draft"
    assert p["case_id"] == "case_A"
    assert p["evidence_ids"] == ["mat_1"]  # 证据引用随草案落账
    assert p["payload"]["claim"] == "存在公开 PoC 且补丁缺失"
    assert p["prompt_version"]  # prompt 版本必须冻结, 可审计


def test_draft_judgment_drafter_failure_becomes_failed_proposal(svc):
    """用例 A②: 模型超时/拒绝 → failed 提案, 不抛 500, 不伪造内容。"""
    _bind_case_evidence("case_B", {"id": "mat_2", "url": "https://x/2"})

    def boom(ctx):
        raise TimeoutError("read timed out")

    p = svc.draft_judgment("case_B", drafter=boom)
    assert p["status"] == "failed"
    assert p["payload"] == {}
    assert "TimeoutError" in p["error_msg"]
    assert p["case_id"] == "case_B"  # 失败也锚定 case, 收件箱可按案重试


def test_draft_judgment_without_evidence_is_400(svc):
    with pytest.raises(ProposalValidationError, match="no bound evidence"):
        svc.draft_judgment("case_EMPTY", drafter=_good_drafter)


def test_approve_judgment_materializes_signed_artifact_with_backtrace(
    svc, monkeypatch,
):
    """用例 A 主路径: 批准 → Run done + md Artifact(sha256) → Source 原文可回溯。"""
    import hashlib
    from pathlib import Path

    from backend.config import config

    _bind_case_evidence("case_C", {
        "id": "mat_3", "url": "https://src.example.com/cve/31337",
        "title": "CVE 公告", "content_hash": "f" * 64,
    })
    p = svc.draft_judgment("case_C", drafter=_good_drafter)
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")
    run = svc.runs.get(approved["run_id"])
    assert run["status"] == "succeeded" and run["outcome"] == "done"
    assert len(run["artifact_ids"]) == 1

    # 关系链回溯: artifact → run → proposal → case → material(Source url)
    conn = get_connection()
    row = conn.execute(
        "SELECT a.id, a.content_hash, a.content_ref, a.status, m.url "
        "FROM v1_artifacts a "
        "JOIN v1_runs r ON r.id = a.run_id "
        "JOIN v1_proposals p ON p.run_id = r.id "
        "JOIN v1_case_materials cm ON cm.case_id = p.case_id "
        "JOIN v1_materials m ON m.id = cm.material_id",
    ).fetchone()
    aid, recorded_hash, content_ref, a_status, source_url = row
    assert aid == run["artifact_ids"][0]
    assert a_status == "pending"  # 登记后待人 verify/accept, 不自动验收
    assert source_url == "https://src.example.com/cve/31337"

    # sha256: 落盘正文重算必须与登记一致 (R08), 且正文内嵌 Source url (回溯终端)
    md_path = Path(content_ref)
    assert md_path.is_file()
    assert hashlib.sha256(md_path.read_bytes()).hexdigest() == recorded_hash
    body = md_path.read_text(encoding="utf-8")
    assert source_url in body and "存在公开 PoC" in body
    # 产物落在受管 data 目录 (测试环境隔离)
    assert md_path.parent == Path(config.data_dir) / "run_artifacts"


def test_approve_judgment_human_edit_reaches_artifact(svc):
    """人修订后批准: 产物正文必须是修订版而非 AI 原稿 (主从关系)。"""
    from pathlib import Path
    _bind_case_evidence("case_D", {"id": "mat_4", "url": "https://x/4"})
    p = svc.draft_judgment("case_D", drafter=_good_drafter)
    edited = {"claim": "人工结论: 当前不可利用", "conditions": "已缓解",
              "confidence": "low", "unknowns": []}
    approved = svc.approve_proposal(p["id"], reviewed_by="owner", payload=edited)
    run = svc.runs.get(approved["run_id"])
    from backend.repository.artifact_repo import ArtifactRepository
    art = ArtifactRepository().get(run["artifact_ids"][0])
    assert "人工结论: 当前不可利用" in Path(art["content_ref"]).read_text()
    assert "存在公开 PoC" not in Path(art["content_ref"]).read_text()


class _ExplodingArtifacts:
    def create(self, **kwargs):
        raise RuntimeError("simulated disk failure")


def test_approve_judgment_artifact_failure_marks_run_failed(svc):
    """用例 A 异常流: 产物登记失败 → Run=failed/outcome=failed, 原异常上抛。"""
    svc._artifact_service = _ExplodingArtifacts()
    _bind_case_evidence("case_E", {"id": "mat_5", "url": "https://x/5"})
    p = svc.draft_judgment("case_E", drafter=_good_drafter)
    with pytest.raises(RuntimeError, match="disk failure"):
        svc.approve_proposal(p["id"], reviewed_by="owner")

    anchor = f"proposal:{p['id']}"
    run = svc.runs.find_by_idem(anchor, anchor)
    assert run["status"] == "failed" and run["outcome"] == "failed"
    assert "disk failure" in (run["error"] or "")
    # 人的批准决定成立 (approved), 失败的是执行, 可凭 run_id 重试
    assert svc.get_proposal(p["id"])["status"] == "approved"


def test_api_draft_judgment_no_evidence_400(e2e_api_client):
    r = e2e_api_client.post(
        "/api/proposals/draft-judgment", json={"case_id": "case_NOPE"},
    )
    assert r.status_code == 400


def test_api_draft_judgment_success_and_artifact_chain(
    e2e_api_client, monkeypatch,
):
    """端到端: 起草(桩 drafter, 不打真 LLM) → 批准 → Run done + artifact。"""
    import backend.services.run_ledger_service as mod
    monkeypatch.setattr(mod, "ai_draft_judgment", _good_drafter)
    _bind_case_evidence("case_F", {
        "id": "mat_6", "url": "https://src.example.com/f/6", "title": "报告",
    })
    client = e2e_api_client

    r = client.post("/api/proposals/draft-judgment", json={"case_id": "case_F"})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert r.json()["status"] == "draft"

    r = client.post(f"/api/proposals/{pid}/approve", json={"reviewed_by": "owner"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    run = client.get("/api/proposals").json()  # sanity: 列表不炸
    assert run["total"] == 1

    conn = get_connection()
    row = conn.execute(
        "SELECT r.status, r.outcome, COUNT(a.id) FROM v1_runs r "
        "JOIN v1_artifacts a ON a.run_id = r.id WHERE r.id = ? "
        "GROUP BY r.id", (run_id,),
    ).fetchone()
    assert tuple(row) == ("succeeded", "done", 1)


# ── 9. failed Run 原地重试 (DEV-0266, P1-1 收尾) ─────────────────────
def test_retry_run_recovers_after_transient_artifact_failure(svc):
    """产物化失败 Run 凭 run_id 重试: 复位→重产物化→succeeded/done, 失败痕迹清零。"""
    svc._artifact_service = _ExplodingArtifacts()
    _bind_case_evidence("case_G", {"id": "mat_7", "url": "https://src.example.com/g/7"})
    p = svc.draft_judgment("case_G", drafter=_good_drafter)
    with pytest.raises(RuntimeError, match="disk failure"):
        svc.approve_proposal(p["id"], reviewed_by="owner")

    anchor = f"proposal:{p['id']}"
    run = svc.runs.find_by_idem(anchor, anchor)
    assert run["status"] == "failed" and run["outcome"] == "failed"
    assert "disk failure" in (run["error"] or "")

    class _OkArtifacts:
        def create(self, **kwargs):
            return {"id": "art_retry_ok", "status": "pending"}

    svc._artifact_service = _OkArtifacts()
    retried = svc.retry_run(run["id"])
    assert retried["status"] == "succeeded" and retried["outcome"] == "done"
    assert retried["error"] is None  # 复位后账本行不留旧失败原因
    assert retried["artifact_ids"] == ["art_retry_ok"]
    # 同一 Run 行 + proposal.run_id 回指不变 → 回溯链与"一提案一 Run"保持
    p2 = svc.get_proposal(p["id"])
    assert p2["run_id"] == run["id"] and p2["status"] == "approved"


def test_retry_run_guards_failed_state_and_ledger_domain(svc):
    from backend.exceptions import NotFoundException

    _bind_case_evidence("case_H", {"id": "mat_8", "url": "https://x/8"})
    p = svc.draft_judgment("case_H", drafter=_good_drafter)
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")
    # 非 failed 态拒绝重试 (409 语义)
    with pytest.raises(ProposalConflictError, match="only failed run"):
        svc.retry_run(approved["run_id"])
    # 非账本 Run (action_id 非 proposal: 锚点) 拒绝 (400 语义)
    svc.runs.insert({
        "id": "run_RAW", "action_id": "action_RAW", "protocol": "direct",
        "trigger_source": "user", "idempotency_key": "k_raw", "status": "failed",
        "created_at": "2026-10-03T00:00:00+00:00",
        "updated_at": "2026-10-03T00:00:00+00:00",
    })
    with pytest.raises(ProposalValidationError, match="not a ledger proposal run"):
        svc.retry_run("run_RAW")
    # 未知 run (404 语义)
    with pytest.raises(NotFoundException, match="run not found"):
        svc.retry_run("run_NOPE")


def test_retry_run_conflicts_when_proposal_not_approved(svc):
    """failed Run 锚到非 approved 提案 (手工构造边界) → 409 语义。"""
    p = svc.create_proposal(
        source="agent", kind="judgment_draft",
        payload={"claim": "x"}, case_id="case_Z",
    )
    svc.runs.insert({
        "id": "run_ORPHAN", "action_id": f"proposal:{p['id']}",
        "protocol": "direct", "trigger_source": "user",
        "idempotency_key": f"proposal:{p['id']}", "status": "failed",
        "created_at": "2026-10-03T00:00:00+00:00",
        "updated_at": "2026-10-03T00:00:00+00:00",
    })
    with pytest.raises(ProposalConflictError, match="not approved"):
        svc.retry_run("run_ORPHAN")


def test_api_retry_run_maps_409_and_404(e2e_api_client, monkeypatch):
    """HTTP 契约: succeeded Run 重试 → 409; 未知 run → 404 (成功路径由 service 层覆盖)。"""
    import backend.services.run_ledger_service as mod
    monkeypatch.setattr(mod, "ai_draft_judgment", _good_drafter)
    _bind_case_evidence("case_I", {"id": "mat_9", "url": "https://x/9"})
    client = e2e_api_client
    pid = client.post(
        "/api/proposals/draft-judgment", json={"case_id": "case_I"},
    ).json()["id"]
    r = client.post(f"/api/proposals/{pid}/approve", json={"reviewed_by": "owner"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert client.post(f"/api/proposals/runs/{run_id}/retry").status_code == 409
    assert client.post("/api/proposals/runs/run_NOPE/retry").status_code == 404
