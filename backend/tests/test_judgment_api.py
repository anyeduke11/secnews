"""T11 Judgment API 端到端测试 (8 个)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.api.judgment_api import router as judgment_router
from backend.repository.db import get_connection


@pytest.fixture()
def client(temp_db, monkeypatch):
    """FastAPI TestClient + 注入 dsh_caller fake (无网络, 无 LLM)."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(judgment_router)

    def fake_dsh(prompt: str) -> str:
        # 找 evidence_materials 的 hash 用于 dsh response
        return json.dumps({
            "claim_type": "finding", "claim": "## X",
            "conditions": "Y", "confidence": "high",
            "evidence_refs": [
                {"material_id": "MAT-API", "hash": "a" * 64, "quote": "ok"},
            ],
            "counter_evidence_refs": [], "unknowns": ["api test"],
        })
    monkeypatch.setattr(
        "backend.services.judgment_service.JudgmentService._call_dsh",
        lambda self, prompt: fake_dsh(prompt),
    )
    return TestClient(app)


def _seed_material(material_id: str = "MAT-API", content_hash: str = "a" * 64) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials "
        "(id, source_kind, url, title, content_hash, content_length, fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        (material_id, f"https://example.com/{material_id}", content_hash),
    )
    conn.commit()


def test_generate_creates_draft(client, temp_db) -> None:
    _seed_material()
    r = client.post("/api/v1/judgments/generate", json={
        "case_id": "C" * 26, "cve_id": "CVE-2026-0001", "subject_name": "某网关",
        "evidence_materials": [{"id": "MAT-API", "title": "T", "content_hash": "a" * 64}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item"]["status"] == "draft"
    assert body["item"]["claim_type"] == "finding"
    assert body["idempotent_replay"] is False


def test_list_judgments_by_case(client, temp_db) -> None:
    _seed_material()
    client.post("/api/v1/judgments/generate", json={
        "case_id": "C" * 26, "cve_id": "CVE-2026-0002", "subject_name": "X",
        "evidence_materials": [{"id": "MAT-API", "content_hash": "a" * 64}],
    })
    r = client.get(f"/api/v1/judgments?case_id={'C' * 26}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_get_judgment_by_id(client, temp_db) -> None:
    _seed_material()
    j = client.post("/api/v1/judgments/generate", json={
        "case_id": "C" * 26, "cve_id": "CVE-2026-0003", "subject_name": "X",
        "evidence_materials": [{"id": "MAT-API", "content_hash": "a" * 64}],
    }).json()["item"]
    r = client.get(f"/api/v1/judgments/{j['id']}")
    assert r.status_code == 200
    assert r.json()["item"]["id"] == j["id"]


def test_get_judgment_404(client) -> None:
    r = client.get("/api/v1/judgments/" + "X" * 26)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "E_NOT_FOUND"


def test_publish_draft_to_published(client, temp_db) -> None:
    _seed_material()
    j = client.post("/api/v1/judgments/generate", json={
        "case_id": "C" * 26, "cve_id": "CVE-2026-0004", "subject_name": "X",
        "evidence_materials": [{"id": "MAT-API", "content_hash": "a" * 64}],
    }).json()["item"]
    r = client.post(f"/api/v1/judgments/{j['id']}/publish", json={"expected_revision": 1})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["status"] == "published"
    assert "create_supersede" in r.json()["item"]["allowed_actions"]


def test_publish_revision_mismatch_409(client, temp_db) -> None:
    _seed_material()
    j = client.post("/api/v1/judgments/generate", json={
        "case_id": "C" * 26, "cve_id": "CVE-2026-0005", "subject_name": "X",
        "evidence_materials": [{"id": "MAT-API", "content_hash": "a" * 64}],
    }).json()["item"]
    r = client.post(f"/api/v1/judgments/{j['id']}/publish", json={"expected_revision": 999})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "E_CONFLICT"


def test_publish_404(client) -> None:
    r = client.post(f"/api/v1/judgments/{'X' * 26}/publish", json={"expected_revision": 1})
    assert r.status_code == 404


def test_list_query_validation(client) -> None:
    """query 缺 case_id → 422."""
    r = client.get("/api/v1/judgments")
    assert r.status_code == 422
