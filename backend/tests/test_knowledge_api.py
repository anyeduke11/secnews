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


def test_generate_creates_draft(client) -> None:
    _seed_material_and_judgment_action()
    r = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "网关", "cve_id": "CVE-X", "kind": "playbook",
        "evidence_materials": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item"]["status"] == "draft"
    assert body["item"]["kind"] == "playbook"
    assert body["idempotent_replay"] is False


def test_list_returns_knowledge_for_case(client) -> None:
    _seed_material_and_judgment_action()
    client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "X", "cve_id": "CVE-X", "kind": "playbook", "evidence_materials": [],
    })
    r = client.get("/api/v1/knowledge?case_id=" + "C" * 26)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_get_knowledge_by_id(client) -> None:
    _seed_material_and_judgment_action()
    j = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "X", "cve_id": "CVE-X", "kind": "playbook", "evidence_materials": [],
    }).json()["item"]
    r = client.get(f"/api/v1/knowledge/{j['id']}")
    assert r.status_code == 200
    assert r.json()["item"]["id"] == j["id"]


def test_get_knowledge_404(client) -> None:
    r = client.get("/api/v1/knowledge/" + "X" * 26)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "E_NOT_FOUND"


def test_reuse_receipt_endpoint(client) -> None:
    """GET /api/v1/knowledge/{id}/reuse 返 §9.4 派生 {total, by_judgment, by_action, recent_30d}."""
    _seed_material_and_judgment_action()
    j = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "X", "cve_id": "CVE-X", "kind": "playbook", "evidence_materials": [],
    }).json()["item"]
    r = client.get(f"/api/v1/knowledge/{j['id']}/reuse")
    assert r.status_code == 200
    receipt = r.json()["receipt"]
    assert receipt["by_judgment"] == 1
    assert receipt["by_action"] == 1
    assert receipt["total"] == 2


def test_publish_draft_to_published(client) -> None:
    _seed_material_and_judgment_action()
    j = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "X", "cve_id": "CVE-X", "kind": "playbook", "evidence_materials": [],
    }).json()["item"]
    r = client.post(f"/api/v1/knowledge/{j['id']}/publish", json={"expected_revision": 1})
    assert r.status_code == 200
    assert r.json()["item"]["status"] == "published"
    assert r.json()["item"]["wiki_path"] == f"knowledge/{j['id']}.md"


def test_publish_cas_revision_mismatch_409(client) -> None:
    _seed_material_and_judgment_action()
    j = client.post("/api/v1/knowledge/generate", json={
        "case_id": "C" * 26, "judgment_id": "J" * 26, "action_id": "A" * 26,
        "subject_name": "X", "cve_id": "CVE-X", "kind": "playbook", "evidence_materials": [],
    }).json()["item"]
    r = client.post(f"/api/v1/knowledge/{j['id']}/publish", json={"expected_revision": 999})
    assert r.status_code == 409


def test_list_query_validation(client) -> None:
    """T15.5: case_id 改可选, 缺 case_id → 200 (走 listAll 全局)."""
    r = client.get("/api/v1/knowledge")
    assert r.status_code == 200
