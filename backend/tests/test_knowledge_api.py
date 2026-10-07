"""T13 Knowledge API 端到端测试 (8 个)."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.knowledge_api import router as knowledge_router
from backend.repository.db import get_connection


@pytest.fixture()
def client(temp_db, monkeypatch):
    app = FastAPI()
    app.include_router(knowledge_router)

    def fake_dsh(prompt: str) -> str:
        return json.dumps({
            "title": "K1", "body": "x",
            "prerequisites": ["p"],
            "counter_examples": [],
            "evidence_refs": [{"material_id": "MAT-API", "hash": "a" * 64, "quote": "ok"}],
            "review_at": "2026-12-01T00:00:00+00:00",
        })
    monkeypatch.setattr(
        "backend.services.knowledge_service.KnowledgeService._call_dsh",
        lambda self, prompt: fake_dsh(prompt),
    )
    return TestClient(app)


def _seed_material_and_judgment_action():
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, "
        "content_length, fetched_at, created_at, updated_at) "
        "VALUES ('MAT-API', 'url', 'x', 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        ("a" * 64,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments (id, case_id, claim_type, claim, conditions, confidence, "
        "evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, content_hash, "
        "revision, created_at, updated_at) "
        "VALUES (?, ?, 'finding', 'X', '', 'high', '[]', '[]', '[]', 'published', ?, 1, ?, ?)",
        ("J" * 26, "C" * 26, "h" * 64, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_actions (id, case_id, judgment_id, title, plan, plan_hash, "
        "expected_artifacts_json, status, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, 't', '# p', ?, '[\"r\"]', 'planned', 1, ?, ?)",
        ("A" * 26, "C" * 26, "J" * 26, "h" * 64, now, now),
    )
    conn.commit()


def _seed_case_evidence_binding() -> None:
    """P2-4: generate 落 copilot 提案 — report 卡纪律要求 case 绑定证据。"""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, tags_json) "
        "VALUES (?, 'T', 'Q', 1, datetime('now'), datetime('now'), '[]')",
        ("C" * 26,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_case_materials (case_id, material_id, signal_id, created_at) "
        "VALUES (?, 'MAT-API', NULL, datetime('now'))",
        ("C" * 26,),
    )
    conn.commit()


def _seed_knowledge_row() -> str:
    """P2-4 后 generate 不再产 knowledge 行 — 生命周期/复用测试直种 draft。"""
    from backend.services.knowledge_service import KnowledgeService

    _seed_material_and_judgment_action()
    svc = KnowledgeService()
    parsed = {
        "title": "K1", "body": "x",
        "prerequisites": ["p"], "counter_examples": [],
        "evidence_refs": [{"material_id": "MAT-API", "hash": "a" * 64, "quote": "ok"}],
        "review_at": "2026-12-01T00:00:00+00:00",
    }
    return svc._insert_draft(
        case_id="C" * 26, kind="playbook", parsed=parsed,
        submitted_by="test", source_judgment_id="J" * 26, source_action_id="A" * 26,
    )["knowledge"]["id"]


def test_generate_creates_proposal_not_knowledge(client) -> None:
    """P2-4 (SK-04 收编): /generate → copilot 提案 (report/draft), 零 knowledge 直写。"""
    _seed_material_and_judgment_action()
    _seed_case_evidence_binding()
    r = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "网关", "cve_id": "CVE-X", "kind": "playbook",
        "evidence_materials": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item"]["kind"] == "report"
    assert body["item"]["status"] == "draft"
    assert body["item"]["source"] == "copilot"
    assert "CVE-X" in json.dumps(body["item"]["payload"], ensure_ascii=False)
    assert body["idempotent_replay"] is False
    n = get_connection().execute("SELECT COUNT(*) FROM v1_knowledge").fetchone()[0]
    assert n == 0


def test_list_returns_knowledge_for_case(client) -> None:
    _seed_knowledge_row()
    r = client.get("/api/v1/knowledge?case_id=" + "C" * 26)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_get_knowledge_by_id(client) -> None:
    kid = _seed_knowledge_row()
    r = client.get(f"/api/v1/knowledge/{kid}")
    assert r.status_code == 200
    assert r.json()["item"]["id"] == kid


def test_get_knowledge_404(client) -> None:
    r = client.get("/api/v1/knowledge/" + "X" * 26)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "E_NOT_FOUND"


def test_reuse_receipt_endpoint(client) -> None:
    """GET /api/v1/knowledge/{id}/reuse 返 C12 R16 收口: total=0 (无 adoptions)."""
    kid = _seed_knowledge_row()
    r = client.get(f"/api/v1/knowledge/{kid}/reuse")
    assert r.status_code == 200
    receipt = r.json()["receipt"]
    # C12 R16.5 收口: 新知识 derived_from 不计 reuse, total=0
    assert receipt["total"] == 0
    assert "by_judgment" not in receipt
    assert "by_action" not in receipt
    assert "by_decision" in receipt
    assert "by_outcome" in receipt
    assert "recent_30d" in receipt


def test_publish_draft_to_published(client) -> None:
    kid = _seed_knowledge_row()
    r = client.post(f"/api/v1/knowledge/{kid}/publish", json={"expected_revision": 1})
    assert r.status_code == 200
    assert r.json()["item"]["status"] == "published"
    # R10 fix: wiki_path 用 env 根 + items/knowledge_{id}.md (非字面 knowledge/)
    assert r.json()["item"]["wiki_path"] == f"items/knowledge_{kid}.md"


def test_publish_cas_revision_mismatch_409(client) -> None:
    kid = _seed_knowledge_row()
    r = client.post(f"/api/v1/knowledge/{kid}/publish", json={"expected_revision": 999})
    assert r.status_code == 409


def test_list_query_validation(client) -> None:
    """T15.5: case_id 改可选, 缺 case_id → 200 (走 listAll 全局)."""
    r = client.get("/api/v1/knowledge")
    assert r.status_code == 200
