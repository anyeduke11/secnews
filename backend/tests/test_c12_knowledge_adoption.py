"""C12 R16 reverse tests: 知识采用与失效反馈.

修复目标 (对应 docs/v1.0/REVIEW_2026-09-07.md R16):
  R16.1: 新知识 total 从 0 起算 — 不应把 source refs 计入 reuse
  R16.2: derived_from 与 adopted_by 物理分离 (新表 v1_knowledge_adoptions)
  R16.3: 召回条件比较 — prerequisites/counter_examples 与当前 case 差异
  R16.4: 撤回/反证/过期 → 挂活跃 case blocker (走 knowledge_review_due 机制)
  R16.5: 召回 receipt {total, by_decision, by_outcome, recent_30d} 只数 adoptions 表
  R16.6: outcome 反馈只改 by_outcome, 不改 total

纪律: 反例测试在旧实现上必失败 (AttributeError 或断言错), 修复后必 pass。
本批 (C12) 跨批保护: 所有 ULID 26 字符 ^[A-Z2-7]{26}$ 锁死。
"""

from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection
from backend.services.knowledge_service import KnowledgeService

# -------- helpers --------

# ULID 字符集 [A-Z2-7], 全部 26 字符 (与 contracts §0.1 一致)
_K0 = "A" * 26
_K1 = "B" * 26
_K2 = "C" * 26
_K3 = "D" * 26
_K4 = "E" * 26
_K5 = "F" * 26
_K6 = "G" * 26


def _ulid26(prefix: str) -> str:
    """生成 26 字符 ULID (prefix 头 + 26-prefix 长 0-9 补位)."""
    if len(prefix) > 26:
        return prefix[:26]
    return prefix + "0" * (26 - len(prefix))


def _insert_case(case_id: str, title: str = "C12 test case") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_cases (id, title, question, status, revision, "
        "tags_json, related_subject_ids_json, related_signal_ids_json, "
        "related_case_ids_json, created_at, updated_at) "
        "VALUES (?, ?, ?, 'open', 1, '[]', '[]', '[]', '[]', "
        "datetime('now'), datetime('now'))",
        (case_id, title, f"{title} question"),
    )
    conn.commit()


def _dsh_response() -> str:
    """C12 mock: 返回 dsh 解析后的 knowledge 草稿 JSON.

    实际格式 (依 contracts §5.2 EvidenceRef): {material_id, hash}
    """
    return json.dumps({
        "title": "C12 R16 fixture knowledge",
        "body": "Test body for R16",
        "prerequisites": ["prereq1"],
        "counter_examples": ["counter1"],
        "evidence_refs": [{"material_id": "MAT-C12-1", "hash": "c12" + "h" * 61}],
        "review_at": "2026-12-01T00:00:00+00:00",
    })


def _seed_material(
    material_id: str = "MAT-C12-1", content_hash: str = "c12" + "h" * 61,
) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials "
        "(id, source_kind, url, title, content_hash, content_length, "
        "fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', ?, 'T', ?, 100, datetime('now'), "
        "datetime('now'), datetime('now'))",
        (material_id, f"https://example.com/{material_id}", content_hash),
    )
    conn.commit()


def _seed_minimal_closure(
    case_id: str, judgment_id: str, action_id: str,
) -> None:
    """case + judgment(published) + action(planned) 最小闭环 (走真实 schema)."""
    _seed_material()
    _insert_case(case_id, "C12 R16 fixture case")
    conn = get_connection()
    now = "2026-09-07T00:00:00+00:00"
    conn.execute(
        "INSERT INTO v1_judgments (id, case_id, claim_type, claim, conditions, "
        "confidence, evidence_refs_json, counter_evidence_refs_json, "
        "unknowns_json, status, content_hash, revision, created_at, updated_at) "
        "VALUES (?, ?, 'finding', 'X', '', 'medium', '[]', '[]', '[]', "
        "'published', ?, 1, ?, ?)",
        (judgment_id, case_id, "h" * 64, now, now),
    )
    conn.execute(
        "INSERT INTO v1_actions (id, case_id, judgment_id, title, plan, "
        "plan_hash, expected_artifacts_json, status, revision, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, 't', '# p', ?, '[]', 'completed', 1, ?, ?)",
        (action_id, case_id, judgment_id, "h" * 64, now, now),
    )
    conn.commit()


@pytest.fixture
def fixture_case_with_judgment(temp_db):
    case_id = _ulid26("C12FIXA000000000000000")
    judgment_id = _ulid26("C12FIXJ000000000000000")
    action_id = _ulid26("C12FIXX000000000000000")
    _seed_minimal_closure(case_id, judgment_id, action_id)
    return {
        "case_id": case_id,
        "judgment_id": judgment_id,
        "action_id": action_id,
    }


def _create_knowledge(
    svc: KnowledgeService, case_id: str, jid: str, aid: str,
) -> str:
    """通过 mock dsh 走 create_with_dsh, 返 knowledge id."""
    res = svc.create_with_dsh(
        case_id=case_id, judgment_id=jid, action_id=aid,
        subject_name="C12 R16", cve_id="CVE-2026-31337", kind="playbook",
        evidence_materials=[], submitted_by="test_user",
    )
    return res["knowledge"]["id"]


def _new_case(ulid_seed: str) -> str:
    """生成 26-char ULID case id, 直接 INSERT 走 v1_cases."""
    cid = _ulid26(ulid_seed)
    _insert_case(cid, f"C12 R16 {ulid_seed[:6]}")
    return cid


# -------- R16.1 reverse: 新知识 total = 0 (旧实现 = 2 含 source) --------

def test_r16_1_new_knowledge_total_starts_at_zero(
    fixture_case_with_judgment, temp_db,
):
    """新知识刚建立: derived_from 不应计入 adoption total = 0."""
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    receipt = svc.get_reuse_receipt(kid)
    assert receipt["total"] == 0, (
        f"R16.1 FAIL: 新知识 total 应为 0, 实际 {receipt['total']} "
        f"(含 derived_from source refs 误统计)"
    )
    assert receipt.get("by_decision", {}).get("adopted", 0) == 0
    assert receipt.get("by_decision", {}).get("rejected", 0) == 0


# -------- R16.2: adopted_by 物理分离 --------

def test_r16_2_adoption_creates_new_table_row(
    fixture_case_with_judgment, temp_db,
):
    """record_adoption → v1_knowledge_adoptions 有 1 行, v1_knowledge_refs 不变."""
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    published = svc.publish(kid, expected_revision=1)
    published_revision = published["revision"]

    target_case_id = _new_case("C12TGT0000000000000000002")
    adoption = svc.record_adoption(
        knowledge_id=kid,
        case_id=target_case_id,
        condition_diff=[{"field": "prereq1", "expected": "X", "actual": "Y"}],
        decision="adopted",
        decided_by="test_user",
    )
    assert adoption["case_id"] == target_case_id
    assert adoption["knowledge_id"] == kid
    assert adoption["decision"] == "adopted"
    assert adoption["knowledge_revision"] == published_revision, (
        f"knowledge_revision 应 = {published_revision} (publish 后), "
        f"实际 {adoption['knowledge_revision']}"
    )

    conn = get_connection()
    rows = conn.execute(
        "SELECT role, source_type FROM v1_knowledge_refs WHERE knowledge_id = ?",
        (kid,),
    ).fetchall()
    roles = {row[0] for row in rows}
    assert "adopted" not in roles, (
        f"R16.2 FAIL: v1_knowledge_refs 不应含 adopted, 实际 {roles}"
    )

    adopt_rows = conn.execute(
        "SELECT decision FROM v1_knowledge_adoptions "
        "WHERE knowledge_id = ? AND case_id = ?",
        (kid, target_case_id),
    ).fetchall()
    assert len(adopt_rows) == 1, (
        f"R16.2 FAIL: v1_knowledge_adoptions 缺 1 行, 实际 {len(adopt_rows)}"
    )


# -------- R16.3: 召回条件比较 --------

def test_r16_3_recall_returns_condition_diff(
    fixture_case_with_judgment, temp_db,
):
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    svc.publish(kid, expected_revision=1)

    target_case_id = _new_case("C12TGT0000000000000000003")
    svc.record_adoption(
        knowledge_id=kid,
        case_id=target_case_id,
        condition_diff=[
            {"field": "prereq_A", "expected": "yes", "actual": "no",
             "severity": "mismatch"},
            {"field": "counter_X", "expected": "no", "actual": "yes",
             "severity": "warn"},
        ],
        decision="adopted",
        decided_by="test_user",
    )

    other_case_id = _new_case("C12TGT0000000000000000004")
    recall = svc.recall_for_case(other_case_id, knowledge_id=kid)
    assert "applicable" in recall, "R16.3 FAIL: 缺 applicable 字段"
    assert "prerequisite_match" in recall, "R16.3 FAIL: 缺 prerequisite_match"
    assert "counter_example_conflict" in recall, (
        "R16.3 FAIL: 缺 counter_example_conflict"
    )
    assert "adoption_history" in recall, "R16.3 FAIL: 缺 adoption_history"
    assert len(recall["adoption_history"]) >= 1
    assert recall["adoption_history"][0]["case_id"] == target_case_id
    assert recall["adoption_history"][0]["condition_diff"]


# -------- R16.4: 撤回 → 挂活跃 case blocker --------

def test_r16_4_retract_affects_active_cases(
    fixture_case_with_judgment, temp_db,
):
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    svc.publish(kid, expected_revision=1)

    target_case_id = _new_case("C12TGT0000000000000000005")
    svc.record_adoption(
        knowledge_id=kid,
        case_id=target_case_id,
        condition_diff=[],
        decision="adopted",
        decided_by="test_user",
    )

    svc.retract(
        kid,
        expected_revision=2,
        reason="C12 R16 reverse test: counter-evidence found",
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT tags_json FROM v1_cases WHERE id = ?", (target_case_id,),
    ).fetchone()
    tags = json.loads(row[0] or "[]")
    assert any(t.startswith("knowledge_retracted:") for t in tags), (
        f"R16.4 FAIL: 撤回后 case 缺 blocker tag, 实际 {tags}"
    )
    adoptions = conn.execute(
        "SELECT decision FROM v1_knowledge_adoptions "
        "WHERE case_id = ? AND knowledge_id = ?",
        (target_case_id, kid),
    ).fetchall()
    assert len(adoptions) == 1, (
        "R16.4 FAIL: 撤回不可破坏 adoption 历史 (append-only-ish)"
    )


# -------- R16.5: receipt 只数 adoptions --------

def test_r16_5_receipt_only_counts_adoptions(
    fixture_case_with_judgment, temp_db,
):
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    svc.publish(kid, expected_revision=1)

    for i in range(3):
        tc = _new_case(f"C12RCT00{i}0000000000000000006")
        svc.record_adoption(
            knowledge_id=kid, case_id=tc, condition_diff=[],
            decision="adopted", decided_by="test_user",
        )

    receipt = svc.get_reuse_receipt(kid)
    assert receipt["total"] == 3, (
        f"R16.5 FAIL: total 应=3, 实际 {receipt['total']}"
    )
    assert receipt["by_decision"]["adopted"] == 3
    assert receipt["by_decision"].get("rejected", 0) == 0
    assert "by_judgment" not in receipt, (
        "R16.5 FAIL: receipt 应弃用 by_judgment 字段 (旧 derived_from 误统计)"
    )


# -------- R16.6: outcome 反馈不影响 total --------

def test_r16_6_outcome_recording_does_not_change_total(
    fixture_case_with_judgment, temp_db,
):
    svc = KnowledgeService(dsh_caller=lambda _p: _dsh_response())
    kid = _create_knowledge(
        svc,
        fixture_case_with_judgment["case_id"],
        fixture_case_with_judgment["judgment_id"],
        fixture_case_with_judgment["action_id"],
    )
    svc.publish(kid, expected_revision=1)
    tc = _new_case("C12OUT0000000000000000000007")
    svc.record_adoption(
        knowledge_id=kid, case_id=tc, condition_diff=[],
        decision="adopted", decided_by="test_user",
    )

    before = svc.get_reuse_receipt(kid)["total"]
    svc.record_outcome(
        knowledge_id=kid, case_id=tc,
        outcome="success", outcome_note="work done",
    )
    after = svc.get_reuse_receipt(kid)["total"]
    assert before == after == 1, (
        f"R16.6 FAIL: outcome 不应改 total ({before}→{after})"
    )
    assert svc.get_reuse_receipt(kid)["by_outcome"]["success"] == 1
