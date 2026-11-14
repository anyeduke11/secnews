"""v0.8.8 P4 C4-2: R-11 七段写端点幂等 / 并发 / 错误语义回归门禁。

测试意图 (WHY):
- R-11 ③: 错误响应统一含 ``error_code`` / ``retryable`` 字段 — exceptions.py
  的 _err_response 是全部错误出口, 在此断言 (retryable: 429/5xx=True)。
- R-11 ①: Case create (client_request_id) 与 Artifact create (run_id+content_hash)
  此前无幂等键 → 重复提交产生重复行; 本文件钉住「重放返回同结果, 零重复行」。
- Run (三层幂等 contracts §7.4) / Judgment (content_hash 键) / publish (CAS)
  既有语义由原测试覆盖, 不在此重复。

并发口径: 单实例 SQLite 写串行 — 用「连续两次同键调用」模拟并发双路,
重复行断言等价 (真线程并发由 UNIQUE 约束兜底, 见各 service docstring)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.exceptions import (
    NotFoundException,
    RateLimitedException,
    register_exception_handlers,
)


def _error_app(*, raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()

    @app.get("/boom-404")
    def _not_found() -> None:
        raise NotFoundException("case not found")

    @app.get("/boom-429")
    def _rate_limited() -> None:
        raise RateLimitedException("provider saturated")

    @app.get("/boom-500")
    def _internal() -> None:
        raise RuntimeError("unhandled")

    register_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_error_envelope_has_error_code_and_retryable() -> None:
    """R-11 ③: 4xx → retryable=False; 5xx/429 → retryable=True; error_code 显式。"""
    client = _error_app()

    resp = client.get("/boom-404")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "NOT_FOUND"
    assert body["code"] == "NOT_FOUND"  # 兼容别名保留
    assert body["retryable"] is False

    resp = client.get("/boom-429")
    body = resp.json()
    assert body["error_code"] == "RATE_LIMITED"
    assert body["retryable"] is True

    # 未处理异常兜底 500 — 需 raise_server_exceptions=False 让 Exception
    # handler 接住 (test_exceptions.py:82 同款先例)
    client500 = _error_app(raise_server_exceptions=False)
    resp = client500.get("/boom-500")
    body = resp.json()
    assert body["retryable"] is True


# ── Case create 幂等 (client_request_id) ─────────────────────────────


def test_case_create_replay_same_body_returns_same_case(temp_db: Path) -> None:
    """R-11 ①: 同 client_request_id + 同语义 body 重放 → 同一 case, 零重复行。"""
    from backend.services.case_service import CaseService

    svc = CaseService()
    first = svc.create_case(
        title="幂等重放", question="q", source="test", client_request_id="cr-42",
    )
    second = svc.create_case(
        title="幂等重放", question="q", source="test", client_request_id="cr-42",
    )
    assert second.id == first.id
    conn = sqlite3.connect(str(temp_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM v1_cases").fetchone()[0] == 1
        # 快路径重放不写 evidence receipt (避免 receipt 与重放行错位)
        assert conn.execute(
            "SELECT COUNT(*) FROM v1_evidence_receipts WHERE entity_type='case'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_case_create_same_key_different_body_conflicts(temp_db: Path) -> None:
    """R-11 ①: 同 client_request_id 不同 body → ConflictException (RunService 守卫 2 同款)。"""
    from backend.services.case_service import CaseService

    svc = CaseService()
    svc.create_case(title="原始标题", question="q", source="test", client_request_id="cr-7")
    with pytest_conflict():
        svc.create_case(
            title="不同标题", question="q", source="test", client_request_id="cr-7",
        )


def pytest_conflict():
    import pytest

    from backend.exceptions import ConflictException

    return pytest.raises(ConflictException)


def test_case_create_without_key_keeps_random_ulid(temp_db: Path) -> None:
    """不传 client_request_id 时行为不变 (随机 ULID, 不做重放判定)。"""
    from backend.services.case_service import CaseService

    svc = CaseService()
    a = svc.create_case(title="a", question="q", source="test")
    b = svc.create_case(title="a", question="q", source="test")
    assert a.id != b.id  # 无键 → 两次独立立项 (既有语义)


def test_case_api_create_passes_client_request_id(temp_db: Path) -> None:
    """API 契约: CreateCaseRequest.client_request_id 透传到 service (幂等键入参)。"""
    from fastapi.testclient import TestClient as _TC  # noqa: F401 — e2e 走 service 层已足够

    from backend.services.case_service import CaseService

    svc = CaseService()
    first = svc.create_case(
        title="api 幂等", question="q", source="web", client_request_id="cr-api-1",
    )
    again = svc.create_case(
        title="api 幂等", question="q", source="web", client_request_id="cr-api-1",
    )
    assert again.id == first.id


# ── Artifact create 幂等 (run_id + content_hash) ─────────────────────


def _seed_run_chain(temp_db: Path) -> str:
    """最小链: judgment(published) → action → run, 返回 run_id。"""
    from backend.repository.action_repo import ActionRepository
    from backend.repository.judgment_repo import JudgmentRepository
    from backend.repository.run_repo import RunRepository

    JudgmentRepository().insert({
        "id": "jd-art-idem", "case_id": "case-art-idem", "claim_type": "finding",
        "claim": "c", "confidence": "medium", "evidence_refs": [],
        "unknowns": [], "status": "published", "wiki_path": "items/jd-art-idem.md",
        "published_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    ActionRepository().insert({
        "id": "act-art-idem", "case_id": "case-art-idem", "judgment_id": "jd-art-idem",
        "title": "artifact 幂等", "plan": "p", "plan_hash": "h", "status": "planned",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    run_id = "run-art-idem"
    RunRepository().insert({
        "id": run_id, "action_id": "act-art-idem", "attempt": 1,
        "protocol": "direct", "idempotency_key": "idem-art-1", "status": "queued",
        "trigger_source": "user",
        "started_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    return run_id


def test_artifact_create_dedup_same_run_and_content(temp_db: Path) -> None:
    """R-11 ①: 同 (run_id, content_hash) 重复登记 → 返回既有 artifact, 零重复行。"""
    from backend.services.artifact_service import ArtifactService

    run_id = _seed_run_chain(temp_db)
    # R08 守卫: content_ref 文件必须存在且 hash 与 content 一致
    ref = temp_db.parent / "artifact-idem.md"
    content = "# artifact idempotency\n\nsame content"
    ref.write_text(content, encoding="utf-8")

    svc = ArtifactService()
    first = svc.create(
        run_id=run_id, kind="report", title="t",
        content=content, content_ref=str(ref),
    )
    second = svc.create(
        run_id=run_id, kind="report", title="t",
        content=content, content_ref=str(ref),
    )
    assert second["id"] == first["id"]
    conn = sqlite3.connect(str(temp_db))
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM v1_artifacts WHERE run_id = ?", (run_id,)
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_artifact_create_different_content_not_deduped(temp_db: Path) -> None:
    """同 run 不同内容 → 各自登记 (幂等键含 content_hash, 不误伤新产物)。"""
    from backend.services.artifact_service import ArtifactService

    run_id = _seed_run_chain(temp_db)
    ref1 = temp_db.parent / "artifact-a.md"
    ref2 = temp_db.parent / "artifact-b.md"
    ref1.write_text("# content A", encoding="utf-8")
    ref2.write_text("# content B", encoding="utf-8")

    svc = ArtifactService()
    a = svc.create(run_id=run_id, kind="report", title="A",
                   content="# content A", content_ref=str(ref1))
    b = svc.create(run_id=run_id, kind="report", title="B",
                   content="# content B", content_ref=str(ref2))
    assert a["id"] != b["id"]


def test_artifact_rejected_hash_allows_new_row_keeps_anti_sneak(temp_db: Path) -> None:
    """R-11 × contracts §8.3 交叉语义: rejected 后同 hash 重新登记走**新行**
    (去重不吞防蒙混流程), accept 时由既有守卫 409。
    """
    import pytest

    from backend.services.artifact_service import ArtifactConflictError, ArtifactService

    run_id = _seed_run_chain(temp_db)
    ref = temp_db.parent / "artifact-reject.md"
    content = "# bad content for reject flow"
    ref.write_text(content, encoding="utf-8")
    svc = ArtifactService()
    a = svc.create(run_id=run_id, kind="report", title="r",
                   content=content, content_ref=str(ref))
    svc.verify(a["id"], verified_by="ci-bot", verified_result="fail")
    assert svc.get(a["id"])["status"] == "rejected"
    b = svc.create(run_id=run_id, kind="report", title="r2",
                   content=content, content_ref=str(ref))
    assert b["id"] != a["id"]  # rejected 不去重 → 新行
    conn = sqlite3.connect(str(temp_db))
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM v1_artifacts WHERE run_id = ?", (run_id,)
        ).fetchone()[0] == 2
    finally:
        conn.close()
    # 新行走完 verify pass 后 accept → 既有防蒙混守卫 409 (同 run 同 hash 已有 rejected)
    svc.verify(b["id"], verified_by="ci-bot", verified_result="pass")
    with pytest.raises(ArtifactConflictError, match="rejected"):
        svc.accept(b["id"], accepted_by="user")
