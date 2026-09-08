"""T12 RunService 单元测试 (6 个)."""
from __future__ import annotations

import pytest

from backend.repository.db import get_connection
from backend.services.action_service import ActionService
from backend.services.run_service import (
    RunConflictError,
    RunNotFoundError,
    RunService,
    RunValidationError,
)


def _seed_published_judgment(judgment_id: str) -> None:
    conn = get_connection()
    now = "2026-09-06T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_judgments "
        "(id, case_id, claim_type, claim, conditions, confidence, "
        " evidence_refs_json, counter_evidence_refs_json, unknowns_json, status, "
        " content_hash, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (judgment_id, "C" * 26, "finding", "X", "", "high",
         "[]", "[]", "[]", "published", "h" * 64, 1, now, now),
    )
    conn.commit()


def _make_action(judgment_id: str = "J" * 26) -> str:
    """建 published judgment + planned action; 返 action_id."""
    _seed_published_judgment(judgment_id)
    svc = ActionService(dsh_caller=lambda _p: '{"plan": "# p", "expected_artifacts": ["r"], "success_criteria": "y", "tool_versions": {}, "unknowns": []}')
    return svc.create_with_dsh(
        case_id="C" * 26, judgment_id=judgment_id, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]["id"]


# ---------------------------------------------------------------------------
# create_or_replay 正常路径
# ---------------------------------------------------------------------------
def test_create_or_replay_creates_run(temp_db) -> None:
    aid = _make_action()
    svc = RunService()
    out = svc.create_or_replay(
        action_id=aid, idempotency_key="idem-1", attempt=1, protocol="direct",
    )
    assert out["replayed"] is False
    assert out["run"]["status"] == "queued"  # v1.0 C07 R05 修复: 统一 queued (mock 协议从生产移除)
    assert out["run"]["idempotency_key"] == "idem-1"
    assert out["run"]["attempt"] == 1


def test_idempotent_replay_same_key_same_body(temp_db) -> None:
    aid = _make_action()
    svc = RunService()
    out1 = svc.create_or_replay(action_id=aid, idempotency_key="idem-2", attempt=1, protocol="direct")
    out2 = svc.create_or_replay(action_id=aid, idempotency_key="idem-2", attempt=1, protocol="direct")
    assert out1["replayed"] is False
    assert out2["replayed"] is True
    assert out1["run"]["id"] == out2["run"]["id"]  # 同一 run


# ---------------------------------------------------------------------------
# 三层幂等 (contracts §7.4)
# ---------------------------------------------------------------------------
def test_same_attempt_different_idem_key_raises_422(temp_db) -> None:
    """同一 (action_id, attempt=1) 已被 (idem-A) 占, 再用 idem-B 创 attempt=1 → 422."""
    aid = _make_action()
    svc = RunService()
    svc.create_or_replay(action_id=aid, idempotency_key="idem-A", attempt=1, protocol="direct")
    with pytest.raises(RunValidationError, match="already exists"):
        svc.create_or_replay(action_id=aid, idempotency_key="idem-B", attempt=1, protocol="direct")


def test_same_key_different_body_raises_409(temp_db) -> None:
    """同 (action_id, idempotency_key) + body 不同 → 409 E_CONFLICT."""
    aid = _make_action()
    svc = RunService()
    svc.create_or_replay(
        action_id=aid, idempotency_key="idem-3", attempt=1, protocol="direct",
        inputs={"x": 1},
    )
    with pytest.raises(RunConflictError, match="different body"):
        svc.create_or_replay(
            action_id=aid, idempotency_key="idem-3", attempt=1, protocol="direct",
            inputs={"x": 999},
        )


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------
def test_list_by_action_and_get(temp_db) -> None:
    aid = _make_action()
    svc = RunService()
    r = svc.create_or_replay(action_id=aid, idempotency_key="idem-4", attempt=1, protocol="direct")["run"]
    out = svc.list_by_action(aid, status="queued", limit=10)
    assert out["total"] == 1
    assert out["items"][0]["id"] == r["id"]
    single = svc.get(r["id"])
    assert single["status"] == "queued"


def test_get_not_found_raises() -> None:
    svc = RunService()
    with pytest.raises(RunNotFoundError):
        svc.get("run_NOSUCHRUN000000000000000")
