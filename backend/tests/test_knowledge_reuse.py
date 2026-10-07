"""T13 SK-05 ReuseReceipt 派生 + SK-06 复查测试 (4 个)."""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.services.knowledge_service import (
    KnowledgeNotFoundError,
    KnowledgeService,
)


def _dsh_response() -> str:
    return json.dumps({
        "title": "K1", "body": "# K",
        "prerequisites": ["p1"],
        "counter_examples": [],
        "evidence_refs": [{"material_id": "MAT-R1", "hash": "r" * 64}],
        "review_at": "2026-12-01T00:00:00+00:00",
    })


def _seed(material_id: str = "MAT-R1", content_hash: str = "r" * 64) -> str:
    """seed material + judgment + action, return knowledge id."""
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, "
        "content_length, fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), datetime('now'), datetime('now'))",
        (material_id, f"https://example.com/{material_id}", content_hash),
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
    # P2-4 收编后 create_with_dsh 落提案不直写 — 本夹具直种 draft (SK-05 契约
    # 只关心既有 knowledge 行的 reuse 统计, 与触发路径解耦)
    svc = KnowledgeService()
    return svc._insert_draft(
        case_id="C" * 26, kind="playbook", parsed=json.loads(_dsh_response()),
        submitted_by="test", source_judgment_id="J" * 26, source_action_id="A" * 26,
    )["knowledge"]["id"]


def test_reuse_receipt_derives_2_refs(temp_db) -> None:
    """C12 R16.5: derived_from 不计 reuse, total=0; 无 by_judgment/by_action."""
    kid = _seed()
    svc = KnowledgeService()
    r = svc.get_reuse_receipt(kid)
    assert r["total"] == 0
    assert "by_judgment" not in r
    assert "by_action" not in r
    assert r["by_decision"] == {}
    assert r["by_outcome"] == {}
    assert r["recent_30d"] == 0


def test_reuse_receipt_not_found_raises() -> None:
    svc = KnowledgeService()
    with pytest.raises(KnowledgeNotFoundError):
        svc.get_reuse_receipt("NOSUCHKNOWLEDGE0000000000")


def test_scan_review_due_returns_knowledge_with_review_past(temp_db) -> None:
    """SK-06: 扫 review_at <= now + status=published."""
    kid = _seed()
    svc = KnowledgeService()
    svc.publish(kid, expected_revision=1)
    # 把 review_at 倒拨
    conn = get_connection()
    conn.execute("UPDATE v1_knowledge SET review_at = ? WHERE id = ?", ("2020-01-01T00:00:00+00:00", kid))
    conn.commit()
    items = svc.scan_review_due("2026-12-01T00:00:00+00:00")
    assert any(i["id"] == kid for i in items)


def test_mark_case_blocker_adds_marker(temp_db) -> None:
    """SK-06: 挂 case blocker (v1_cases.tags_json 加 marker)."""
    kid = _seed()
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, tags_json) "
        "VALUES (?, 'T', 'Q', 1, datetime('now'), datetime('now'), '[]')",
        ("C" * 26,),
    )
    conn.commit()
    svc = KnowledgeService()
    ok = svc.mark_case_blocker("C" * 26, kid)
    assert ok is True
    row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", ("C" * 26,)).fetchone()
    tags = json.loads(row[0])
    assert any(f"knowledge_review_due:{kid}" == t for t in tags)
