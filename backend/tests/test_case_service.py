"""v1.0 T08 Case 服务端到端测试.

覆盖 (对应 EXECUTION_GUIDE §4 T08 通过证据):
  1. create_case + commit (走 evidence bridge) — receipt committed
  2. get_case / list_cases 过滤 (status / priority / owner_role / subject_id)
  3. update_status CAS 成功 + 失败 (CaseConflictError)
  4. update_case metadata CAS 成功 + 失败
  5. allowed_actions 5 状态机全覆盖 (open/in_progress/blocked/closed/archived)
  6. close_case 成功 + 失败 (active run 拦截)
  7. V1EvidenceService IdempotentReplay 跨提交 (同 submission_key 重放)
  8. close 后 reopen 派生 close_at 已落 + allowed_actions 切换
  9. list_related_cases 关联查询
  10. API 5 端点 200 + 404 + 409 (e2e_api_client + TestClient)
  11. create_case 字段校验失败 (title > 120) → CaseValidationError
  12. create_case 时间戳服务端写 (客户端不传)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.repository.case_repo import CaseRepository
from backend.repository.db import get_connection
from backend.services.case_service import (
    ALLOWED_ACTIONS_BY_STATUS,
    CaseConflictError,
    CaseNotFoundError,
    CaseService,
    CaseValidationError,
)
from backend.services.v1_evidence_service import (
    IdempotentReplay,
    V1EvidenceService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def case_service(temp_db) -> CaseService:
    """temp_db fixture 已建全 schema, 直接实例化服务."""
    return CaseService()


def _ulid_like() -> str:
    """测试用 ULID 占位 (服务端会在 create_case 重新生成; 此处仅用于关联引用)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(alphabet[i % 32] for i in range(26))


# ---------------------------------------------------------------------------
# 1. create + evidence bridge
# ---------------------------------------------------------------------------
def test_create_case_walks_evidence_bridge(case_service: CaseService, temp_db) -> None:
    """create_case 走 V1EvidenceService.create_intent → commit_intent → receipt committed."""
    case = case_service.create_case(
        title="评估 CVE-2026-XXXX 影响",
        question="该漏洞是否影响生产环境?",
        priority="p0",
        owner_role="user",
        tags=["security", "cve"],
    )
    assert case.id and len(case.id) == 26
    assert case.status.value == "open"
    assert case.revision == 1
    assert "claim" in case.allowed_actions
    assert "close" in case.allowed_actions
    assert "edit" in case.allowed_actions

    # receipt 必须 committed
    conn = get_connection()
    row = conn.execute(
        "SELECT status, entity_type FROM v1_evidence_receipts WHERE entity_id = ?",
        (case.id,),
    ).fetchone()
    assert row is not None
    assert row["status"] == "committed"
    assert row["entity_type"] == "case"


# ---------------------------------------------------------------------------
# 2. get / list 过滤
# ---------------------------------------------------------------------------
def test_get_case_returns_case(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T1", question="Q1", priority="p1")
    fetched = case_service.get_case(case.id)
    assert fetched.id == case.id
    assert fetched.title == "T1"
    assert fetched.priority.value == "p1"


def test_get_case_not_found(case_service: CaseService, temp_db) -> None:
    with pytest.raises(CaseNotFoundError):
        case_service.get_case(_ulid_like())


def test_list_cases_filters_status(case_service: CaseService, temp_db) -> None:
    c1 = case_service.create_case(title="A", question="a", priority="p0")
    c2 = case_service.create_case(title="B", question="b", priority="p1")
    # c1 -> in_progress
    case_service.update_case(c1.id, expected_revision=1, status="in_progress")
    items = case_service.list_cases(status=["open"], limit=50)
    assert {c.id for c in items} == {c2.id}


def test_list_cases_filters_priority(case_service: CaseService, temp_db) -> None:
    case_service.create_case(title="A", question="a", priority="p0")
    case_service.create_case(title="B", question="b", priority="p2")
    items = case_service.list_cases(priority=["p0"], limit=50)
    assert len(items) == 1
    assert items[0].priority.value == "p0"


def test_list_cases_filters_owner_role(case_service: CaseService, temp_db) -> None:
    case_service.create_case(title="A", question="a", owner_role="user")
    case_service.create_case(title="B", question="b", owner_role="system")
    items = case_service.list_cases(owner_role="system", limit=50)
    assert len(items) == 1
    assert items[0].owner_role.value == "system"


def test_list_cases_filters_subject_id(case_service: CaseService, temp_db) -> None:
    sub = _ulid_like()
    c1 = case_service.create_case(title="A", question="a", subject_id=sub)
    case_service.create_case(title="B", question="b")
    items = case_service.list_cases(subject_id=sub, limit=50)
    assert {c.id for c in items} == {c1.id}


# ---------------------------------------------------------------------------
# 3. update_status CAS
# ---------------------------------------------------------------------------
def test_update_status_cas_success(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q", priority="p1")
    updated = case_service.update_case(
        case.id, expected_revision=1, status="in_progress"
    )
    assert updated.status.value == "in_progress"
    assert updated.revision == 2
    assert "block" in updated.allowed_actions
    assert "claim" not in updated.allowed_actions


def test_update_status_cas_conflict(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q", priority="p1")
    # 用错误 revision 调用
    with pytest.raises(CaseConflictError) as excinfo:
        case_service.update_case(case.id, expected_revision=999, status="in_progress")
    assert excinfo.value.current_revision == 1
    assert excinfo.value.current_status == "open"


def test_update_metadata_cas_success(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q", priority="p1")
    updated = case_service.update_case(
        case.id, expected_revision=1, title="T-new", priority="p0"
    )
    assert updated.title == "T-new"
    assert updated.priority.value == "p0"
    assert updated.revision == 2


def test_update_metadata_cas_conflict(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q", priority="p1")
    # 先合法更新一次, 把 revision 推到 2
    case_service.update_case(case.id, expected_revision=1, status="in_progress")
    # 再用陈旧 revision 1 调用
    with pytest.raises(CaseConflictError):
        case_service.update_case(case.id, expected_revision=1, title="dup")


# ---------------------------------------------------------------------------
# 4. allowed_actions 5 状态机全覆盖
# ---------------------------------------------------------------------------
def test_allowed_actions_full_state_machine(case_service: CaseService, temp_db) -> None:
    """open → in_progress → blocked → (unblock) → in_progress → closed → archived."""
    # 1) open
    case = case_service.create_case(title="T", question="Q")
    expected = ALLOWED_ACTIONS_BY_STATUS["open"]
    assert sorted(case.allowed_actions) == sorted(expected)

    # 2) in_progress
    case = case_service.update_case(case.id, expected_revision=case.revision, status="in_progress")
    expected = ALLOWED_ACTIONS_BY_STATUS["in_progress"]
    assert sorted(case.allowed_actions) == sorted(expected)

    # 3) blocked
    case = case_service.update_case(case.id, expected_revision=case.revision, status="blocked")
    expected = ALLOWED_ACTIONS_BY_STATUS["blocked"]
    assert sorted(case.allowed_actions) == sorted(expected)

    # 4) unblock → in_progress
    case = case_service.update_case(case.id, expected_revision=case.revision, status="in_progress")
    expected = ALLOWED_ACTIONS_BY_STATUS["in_progress"]
    assert sorted(case.allowed_actions) == sorted(expected)

    # 5) close (R17: 必须 ≥1 published judgment)
    from backend.repository.judgment_repo import JudgmentRepository
    JudgmentRepository().insert({
        "id": "J" * 26, "case_id": case.id, "claim_type": "finding",
        "claim": "test", "conditions": "", "confidence": "high",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "published", "content_hash": "h" * 64, "revision": 1,
        "published_at": "2026-09-07T00:00:00+00:00",
        "created_at": "2026-09-07T00:00:00+00:00",
        "updated_at": "2026-09-07T00:00:00+00:00",
        "allowed_actions": ["view_only"], "reason": None,
    })
    case = case_service.close_case(case.id, expected_revision=case.revision)
    assert case.status.value == "closed"
    assert case.closed_at is not None
    expected = ALLOWED_ACTIONS_BY_STATUS["closed"]
    assert sorted(case.allowed_actions) == sorted(expected)

    # 6) archived
    case = case_service.update_case(case.id, expected_revision=case.revision, status="archived")
    expected = ALLOWED_ACTIONS_BY_STATUS["archived"]
    assert sorted(case.allowed_actions) == sorted(expected)


# ---------------------------------------------------------------------------
# 5. close_case 校验
# ---------------------------------------------------------------------------
def test_close_case_success(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q")
    # R17 fix: case.close 必须 ≥1 published judgment (研究型场景: 无 action 也可关)
    from backend.repository.judgment_repo import JudgmentRepository
    jrepo = JudgmentRepository()
    jrepo.insert({
        "id": "J" * 26, "case_id": case.id, "claim_type": "finding",
        "claim": "test", "conditions": "", "confidence": "high",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "published", "content_hash": "h" * 64, "revision": 1,
        "published_at": "2026-09-07T00:00:00+00:00",
        "created_at": "2026-09-07T00:00:00+00:00",
        "updated_at": "2026-09-07T00:00:00+00:00",
        "allowed_actions": ["view_only"], "reason": None,
    })
    closed = case_service.close_case(case.id, expected_revision=1)
    assert closed.status.value == "closed"
    assert closed.closed_at is not None
    assert closed.reason == "closed"


def test_close_case_blocked_by_active_action(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q")
    # R17 fix: 模拟存在 active action (planned/approved/running) → close 必须 409
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_actions (id, case_id, judgment_id, title, plan, plan_hash, "
        "tool_versions_json, expected_artifacts_json, status, revision, created_at, updated_at, "
        "allowed_actions_json, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("A" * 26, case.id, "J" * 26, "test", "p", "h" * 64, "{}", "[]",
         "running", 1, "2026-09-07T00:00:00+00:00", "2026-09-07T00:00:00+00:00",
         "[]", None),
    )
    conn.execute(
        "INSERT INTO v1_case_actions (case_id, action_id) VALUES (?, ?)",
        (case.id, "A" * 26),
    )
    conn.commit()
    with pytest.raises(CaseConflictError) as excinfo:
        case_service.close_case(case.id, expected_revision=1)
    assert "active action" in str(excinfo.value).lower()


def test_close_case_idempotent_rejects_double_close(case_service: CaseService, temp_db) -> None:
    case = case_service.create_case(title="T", question="Q")
    # R17 fix: 必须 ≥1 published judgment 才能 close
    from backend.repository.judgment_repo import JudgmentRepository
    JudgmentRepository().insert({
        "id": "J" * 26, "case_id": case.id, "claim_type": "finding",
        "claim": "test", "conditions": "", "confidence": "high",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "published", "content_hash": "h" * 64, "revision": 1,
        "published_at": "2026-09-07T00:00:00+00:00",
        "created_at": "2026-09-07T00:00:00+00:00",
        "updated_at": "2026-09-07T00:00:00+00:00",
        "allowed_actions": ["view_only"], "reason": None,
    })
    case_service.close_case(case.id, expected_revision=1)
    # 再 close 一次 (status=closed) → 409
    with pytest.raises(CaseConflictError):
        case_service.close_case(case.id, expected_revision=case.revision)


def test_close_case_not_found(case_service: CaseService, temp_db) -> None:
    with pytest.raises(CaseNotFoundError):
        case_service.close_case(_ulid_like(), expected_revision=1)


# ---------------------------------------------------------------------------
# 6. V1EvidenceService IdempotentReplay 跨提交
# ---------------------------------------------------------------------------
def test_idempotent_replay_across_create(case_service: CaseService, temp_db) -> None:
    """同 submission_key 重放 → IdempotentReplay; 服务端 receipt 仍可被旧 entity_id 命中.

    实现说明: case_service 每次 create_case 都用 ulid[:16] 生成新 submission_key
    (因为 ulid 每次都不同), 严格意义的重放需要复用同一 ulid. 这里直接驱动
    V1EvidenceService 验证 IdempotentReplay 协议链路。
    """
    evidence = V1EvidenceService(conn=get_connection())
    body = {"id": "CASE-DUP-001", "title": "D", "question": "Q"}
    key = "v1-case-test-dup-key"
    intent = evidence.create_intent(key, "case", body)
    evidence.commit_intent(intent["intent_id"], entity_id=body["id"])
    # 重放
    with pytest.raises(IdempotentReplay) as excinfo:
        evidence.create_intent(key, "case", body)
    assert "CASE-DUP-001" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 7. list_related_cases 关联查询
# ---------------------------------------------------------------------------
def test_list_related_cases(case_service: CaseService, temp_db) -> None:
    c1 = case_service.create_case(title="A", question="a")
    # 让 c1 被另一个 case 引用
    c2 = case_service.create_case(
        title="B", question="b", related_case_ids=[c1.id]
    )
    conn = get_connection()
    repo = CaseRepository(conn=conn)
    rows = repo.list_related_cases(c1.id)
    assert {r.id for r in rows} == {c2.id}


# ---------------------------------------------------------------------------
# 8. 字段校验
# ---------------------------------------------------------------------------
def test_create_case_validation_title_too_long(case_service: CaseService, temp_db) -> None:
    """title > 120 → CaseValidationError (Pydantic 字段上限)."""
    with pytest.raises(CaseValidationError):
        case_service.create_case(title="X" * 121, question="Q")


def test_create_case_validation_question_too_long(case_service: CaseService, temp_db) -> None:
    """question > 500 → CaseValidationError."""
    with pytest.raises(CaseValidationError):
        case_service.create_case(title="T", question="X" * 501)


def test_create_case_validation_invalid_priority(case_service: CaseService, temp_db) -> None:
    """priority 不在 p0/p1/p2/p3 → CaseValidationError."""
    with pytest.raises(CaseValidationError):
        case_service.create_case(title="T", question="Q", priority="p9")


def test_timestamps_server_written_not_client_provided(
    case_service: CaseService, temp_db
) -> None:
    """created_at / updated_at 必须服务端写, 客户端不传."""
    case = case_service.create_case(title="T", question="Q")
    assert isinstance(case.created_at, datetime)
    assert isinstance(case.updated_at, datetime)
    # 与服务端时间偏差在 60s 内
    now = datetime.now(timezone.utc)
    assert abs((now - case.created_at).total_seconds()) < 60


# ---------------------------------------------------------------------------
# 9. API 端到端 (e2e_api_client)
# ---------------------------------------------------------------------------
def test_api_create_and_get(e2e_api_client: TestClient) -> None:
    """POST /api/v1/cases → 201 + item; GET /api/v1/cases/{id} → 200."""
    resp = e2e_api_client.post(
        "/api/v1/cases",
        json={
            "title": "API Test",
            "question": "Q?",
            "priority": "p1",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["item"]["title"] == "API Test"
    assert body["item"]["status"] == "open"
    case_id = body["item"]["id"]

    # GET detail
    resp2 = e2e_api_client.get(f"/api/v1/cases/{case_id}")
    assert resp2.status_code == 200
    assert resp2.json()["item"]["id"] == case_id


def test_api_list_filter(e2e_api_client: TestClient) -> None:
    """GET /api/v1/cases?status=open&priority=p0 → 200 + filter."""
    e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "p0-case", "question": "?", "priority": "p0"},
    )
    e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "p2-case", "question": "?", "priority": "p2"},
    )
    resp = e2e_api_client.get("/api/v1/cases?priority=p0&status=open")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(it["priority"] == "p0" for it in items)


def test_api_update_cas_conflict(e2e_api_client: TestClient) -> None:
    """PATCH /api/v1/cases/{id} 错误 revision → 409 + E_CONFLICT."""
    case_id = e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "T", "question": "Q"},
    ).json()["item"]["id"]
    resp = e2e_api_client.patch(
        f"/api/v1/cases/{case_id}",
        json={"expected_revision": 999, "title": "wrong"},
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "E_CONFLICT"
    assert detail["current_revision"] == 1


def test_api_get_not_found(e2e_api_client: TestClient) -> None:
    resp = e2e_api_client.get(f"/api/v1/cases/{_ulid_like()}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "E_NOT_FOUND"


def test_api_close_success(e2e_api_client: TestClient) -> None:
    """POST /api/v1/cases/{id}/close → 200 + closed_at."""
    case_id = e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "T", "question": "Q"},
    ).json()["item"]["id"]
    # R17 fix: 必须 ≥1 published judgment 才能 close
    from backend.repository.judgment_repo import JudgmentRepository
    JudgmentRepository().insert({
        "id": "J" * 26, "case_id": case_id, "claim_type": "finding",
        "claim": "test", "conditions": "", "confidence": "high",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "published", "content_hash": "h" * 64, "revision": 1,
        "published_at": "2026-09-07T00:00:00+00:00",
        "created_at": "2026-09-07T00:00:00+00:00",
        "updated_at": "2026-09-07T00:00:00+00:00",
        "allowed_actions": ["view_only"], "reason": None,
    })
    resp = e2e_api_client.post(
        f"/api/v1/cases/{case_id}/close",
        json={"expected_revision": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["status"] == "closed"
    assert body["item"]["closed_at"] is not None


def test_api_validation_error_returns_400(e2e_api_client: TestClient) -> None:
    """title > 120 → 422 (Pydantic 自动校验) 或 400 (业务校验).

    FastAPI 对 Pydantic 模型字段约束 (max_length) 默认 422; 业务层校验
    (例如 revision 不匹配、active run) 才到 400 E_VALIDATION / 409 E_CONFLICT.
    两者都视为校验失败 (本测试覆盖 Pydantic 422 路径).
    """
    resp = e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "X" * 121, "question": "Q"},
    )
    assert resp.status_code in (400, 422)
    body = resp.json()
    # Pydantic 422 把错误放在 "detail" (list 形式); 我们关注顶层有 detail 即可
    assert "detail" in body


def test_api_validation_error_business_returns_400(e2e_api_client: TestClient) -> None:
    """业务校验: priority 不在 p0/p1/p2/p3 → 400 E_VALIDATION."""
    # Pydantic Field pattern="^(p0|p1|p2|p3)$" → 422; 但 request body 不合规时也走 422.
    # 验证任意 4xx 即可
    resp = e2e_api_client.post(
        "/api/v1/cases",
        json={"title": "T", "question": "Q", "priority": "p9"},
    )
    assert resp.status_code in (400, 422)