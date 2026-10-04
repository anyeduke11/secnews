"""P1-3/M3 副驾三卡起草 + 四 kind 批准产物化测试。

验收 (PRD §10 P1-3): 副驾四卡各产出 ≥1 artifact —
- judgment_draft 产物化由 §8 既有测试覆盖 (切片2);
- 本文件锁: case_suggestion / knowledge_draft / report 三卡起草链 (服务层
  copilot_draft + HTTP copilot-draft) + **全 kind 批准产物化** (Run
  succeeded/done + Artifact sha256 登记 + md 落盘)。

契约 (Rule 9 WHY):
- 起草失败 → failed 提案 (source=copilot), 不抛 500, 不伪造内容 (用例 A② 同纪律);
- case 锚定 kind 必须有绑定证据 (不允许凭空起草);
- 批准产物 md 正文必须含 payload 关键内容 (人批准的就是人看到的)。
"""
from __future__ import annotations

import pytest

from backend.repository.db import get_connection
from backend.services.run_ledger_service import (
    ProposalValidationError,
    RunLedgerService,
)


@pytest.fixture
def svc(temp_db) -> RunLedgerService:
    return RunLedgerService()


def _bind_case_evidence(case_id: str, *materials: dict) -> None:
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


def _insert_kl_item(item_id: str, title: str, topic: str = "摘要素材") -> None:
    from backend.domain.knowledge_models import KnowledgeItem
    from backend.repository.knowledge_repo import knowledge_repo
    knowledge_repo.upsert_item(KnowledgeItem(
        id=item_id, title=title, source="secnews",
        source_url=f"https://example.com/{item_id}", topic=topic,
        lifecycle="kl:raw",
        ingested_at="2026-10-03T00:00:00+00:00",
        updated_at="2026-10-03T00:00:00+00:00",
    ))


# ── 起草: case_suggestion (证据召回卡) ──────────────────────────────

def _cs_drafter(ctx):
    return {"title": "建议立桉跟进 CVE-X", "rationale": "证据显示在野利用",
            "evidence_refs": ["mat_cs"]}


def test_copilot_draft_case_suggestion_binds_evidence(svc):
    _bind_case_evidence("case_CS", {"id": "mat_cs", "url": "https://x/cs"})
    p = svc.copilot_draft("case_suggestion", case_id="case_CS",
                          drafter=_cs_drafter)
    assert p["status"] == "draft"
    assert p["source"] == "copilot"          # 副驾通道
    assert p["kind"] == "case_suggestion"
    assert p["evidence_ids"] == ["mat_cs"]   # 证据引用随草案落账
    assert p["prompt_version"]               # 可审计


def test_copilot_draft_case_kind_without_evidence_is_400(svc):
    with pytest.raises(ProposalValidationError, match="no bound evidence"):
        svc.copilot_draft("case_suggestion", case_id="case_EMPTY",
                          drafter=_cs_drafter)


def test_copilot_draft_case_kind_requires_case_id(svc):
    with pytest.raises(ProposalValidationError, match="case_id is required"):
        svc.copilot_draft("report", drafter=lambda ctx: {})


def test_copilot_draft_drafter_failure_becomes_failed_proposal(svc):
    _bind_case_evidence("case_F", {"id": "mat_f", "url": "https://x/f"})

    def boom(ctx):
        raise TimeoutError("read timed out")

    p = svc.copilot_draft("report", case_id="case_F", drafter=boom)
    assert p["status"] == "failed"
    assert p["source"] == "copilot"
    assert p["payload"] == {}
    assert "TimeoutError" in p["error_msg"]
    assert p["case_id"] == "case_F"          # 失败锚定 case, 收件箱可重试


# ── 起草: knowledge_draft (知识摘要卡) ──────────────────────────────

def _kd_drafter(ctx):
    return {"title": "供应链投毒摘要", "summary": "三家供应商遭投毒",
            "key_points": ["投毒路径", "缓解措施"]}


def test_copilot_draft_knowledge_summary(svc):
    _insert_kl_item("kl-sum-1", "供应链投毒事件", "三家供应商遭投毒")
    p = svc.copilot_draft("knowledge_draft", knowledge_id="kl-sum-1",
                          drafter=_kd_drafter)
    assert p["status"] == "draft"
    assert p["source"] == "copilot"
    assert p["case_id"] is None              # knowledge 锚, 非 case
    assert p["payload"]["key_points"] == ["投毒路径", "缓解措施"]


def test_copilot_draft_knowledge_missing_item_is_400(svc):
    with pytest.raises(ProposalValidationError, match="not found"):
        svc.copilot_draft("knowledge_draft", knowledge_id="kl_NOPE",
                          drafter=_kd_drafter)


def test_copilot_draft_knowledge_requires_knowledge_id(svc):
    with pytest.raises(ProposalValidationError, match="knowledge_id"):
        svc.copilot_draft("knowledge_draft", drafter=_kd_drafter)


def test_copilot_draft_invalid_kind_is_400(svc):
    with pytest.raises(ProposalValidationError, match="invalid copilot kind"):
        svc.copilot_draft("judgment_draft", case_id="x")  # judgment 走专用端点


# ── 验收主断言: 四 kind 批准各产出 ≥1 artifact ─────────────────────

@pytest.mark.parametrize("kind,payload,expect_in_body", [
    ("case_suggestion",
     {"title": "建案建议 X", "rationale": "证据充分", "evidence_refs": ["m1"]},
     "证据充分"),
    ("knowledge_draft",
     {"title": "摘要 Y", "summary": "三家供应商遭投毒", "key_points": ["kp"]},
     "三家供应商遭投毒"),
    ("report",
     {"title": "复盘 Z", "summary": "过程概述", "lessons": ["先验证再采信"],
      "next_actions": ["补齐检测"]},
     "先验证再采信"),
])
def test_approve_non_judgment_kind_materializes_artifact(
    svc, kind, payload, expect_in_body,
):
    """P1-3 验收: 非研判 kind 批准 → Run succeeded/done + Artifact(md, sha256)。

    (切片1 "其余 kind 采纳即 done" 占位语义退役; judgment_draft 产物化
    由 §8 test_approve_judgment_materializes_signed_artifact_with_backtrace
    覆盖 — 四卡 artifact 验收在此拼齐。)
    """
    from pathlib import Path

    _bind_case_evidence(f"case_{kind}", {"id": f"mat_{kind}",
                                         "url": f"https://x/{kind}"})
    p = svc.create_proposal(
        source="copilot", kind=kind, payload=payload,
        evidence_ids=[f"mat_{kind}"], case_id=f"case_{kind}",
    )
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")
    run = svc.runs.get(approved["run_id"])
    assert run["status"] == "succeeded" and run["outcome"] == "done"
    assert len(run["artifact_ids"]) == 1

    from backend.repository.artifact_repo import ArtifactRepository
    art = ArtifactRepository().get(run["artifact_ids"][0])
    assert art["format"] == "md"
    body = Path(art["content_ref"]).read_text(encoding="utf-8")
    assert expect_in_body in body            # 产物 = 人批准的内容
    assert f"https://x/{kind}" in body       # 证据 Source url 回溯终端


def test_approve_knowledge_draft_without_case_still_materializes(svc):
    """knowledge 锚定提案 (case_id=None) 批准 → 产物落盘不因无证据分支崩溃。"""
    from pathlib import Path
    p = svc.create_proposal(
        source="copilot", kind="knowledge_draft",
        payload={"title": "T", "summary": "S", "key_points": []},
    )
    approved = svc.approve_proposal(p["id"], reviewed_by="owner")
    run = svc.runs.get(approved["run_id"])
    assert run["status"] == "succeeded" and run["outcome"] == "done"
    assert len(run["artifact_ids"]) == 1
    assert "S" in Path(
        # content_ref 经 artifact repo 查回
        __import__("backend.repository.artifact_repo", fromlist=["x"])
        .ArtifactRepository().get(run["artifact_ids"][0])["content_ref"],
    ).read_text(encoding="utf-8")


# ── HTTP 契约 ───────────────────────────────────────────────────────

def test_api_copilot_draft_success_and_failure_flow(e2e_api_client, monkeypatch):
    import backend.services.run_ledger_service as mod

    _bind_case_evidence("case_API_CS", {"id": "mat_api", "url": "https://x/api"})
    monkeypatch.setattr(mod, "ai_copilot_draft", _cs_drafter)
    client = e2e_api_client

    r = client.post("/api/proposals/copilot-draft", json={
        "kind": "case_suggestion", "case_id": "case_API_CS",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    assert r.json()["source"] == "copilot"

    # 模型失败 → HTTP 200 + status=failed (收件箱可重试语义)
    def boom(ctx):
        raise RuntimeError("down")

    monkeypatch.setattr(mod, "ai_copilot_draft", boom)
    r = client.post("/api/proposals/copilot-draft", json={
        "kind": "report", "case_id": "case_API_CS",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_api_copilot_draft_param_errors_400(e2e_api_client):
    client = e2e_api_client
    # case kind 缺 case_id
    r = client.post("/api/proposals/copilot-draft", json={"kind": "report"})
    assert r.status_code == 400
    # knowledge kind 缺 knowledge_id
    r = client.post("/api/proposals/copilot-draft", json={
        "kind": "knowledge_draft",
    })
    assert r.status_code == 400
    # judgment 不走此端点
    r = client.post("/api/proposals/copilot-draft", json={
        "kind": "judgment_draft", "case_id": "c",
    })
    assert r.status_code == 400
