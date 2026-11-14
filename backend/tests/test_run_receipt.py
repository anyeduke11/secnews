"""v0.8.9 P1 C1-1: Run 人工回执通道（direct 执行体 = 人，D4 裁决）回归门禁。

测试意图 (WHY):
- 勘察断点①: run 创建即孤儿——7 态机无任何推进器, v1_runs=0 恒冻结。
- 本文件钉住 R-1 契约: ① CAS 迁移链 queued→claimed→running→终态;
  ② RA-9「禁止成功但无产物」——outcome=done 须已有 artifact;
  ③ 失败真实性——failed/timeout/needs_human 须 error;
  ④ 状态竞争 → 409; ⑤ v1_run 事件入 outbox (R-6 前置);
  ⑥ HTTP 端点经真实路由可达 (含统一错误 envelope)。

并发口径: 单实例 SQLite 写串行——连续同调用模拟并发双路 (重复终态 → 409 CAS)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.repository.action_repo import ActionRepository
from backend.repository.judgment_repo import JudgmentRepository
from backend.repository.run_repo import RunRepository
from backend.services.run_service import (
    RunConflictError,
    RunService,
    RunValidationError,
)


def _seed_chain(temp_db: Path) -> str:
    """最小链: judgment(published) → action → run(queued, direct)。返回 run_id。"""
    JudgmentRepository().insert({
        "id": "jd-receipt", "case_id": "case-receipt", "claim_type": "finding",
        "claim": "c", "confidence": "medium", "evidence_refs": [],
        "unknowns": [], "status": "published", "wiki_path": "items/jd-receipt.md",
        "published_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    ActionRepository().insert({
        "id": "act-receipt", "case_id": "case-receipt", "judgment_id": "jd-receipt",
        "title": "人工回执演练", "plan": "p", "plan_hash": "h", "status": "planned",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    RunRepository().insert({
        "id": "run-receipt", "action_id": "act-receipt", "attempt": 1,
        "protocol": "direct", "idempotency_key": "idem-receipt-1",
        "trigger_source": "user",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    return "run-receipt"


def _row(temp_db: Path, run_id: str) -> dict:
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM v1_runs WHERE id = ?", (run_id,)).fetchone())
    finally:
        conn.close()


def test_full_receipt_chain_to_done(temp_db: Path) -> None:
    """验收①: queued→claimed→running→finish(done) 全链 CAS 迁移成功。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    claimed = svc.claim(run_id)
    assert claimed["status"] == "claimed"
    started = svc.start(run_id)
    assert started["status"] == "running"
    # outcome=done 前须登记 artifact (RA-9) — 先以 failed 路径验证状态机, done 路径见下
    finished = svc.finish(run_id, outcome="failed", error="演练: 无产物先败")
    assert finished["status"] == "failed"
    assert finished["outcome"] == "failed"


def test_finish_done_requires_artifact(temp_db: Path) -> None:
    """RA-9: outcome=done 而无 artifact → RunValidationError (禁止成功但无产物)。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    with pytest.raises(RunValidationError, match="RA-9"):
        svc.finish(run_id, outcome="done")
    # 登记 artifact 后 (直接落 v1_artifacts 行, 模拟人工登记产物) → 通过
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "INSERT INTO v1_artifacts (id, run_id, kind, title, content_hash, format, "
        "status, created_at, updated_at) VALUES ('art-r1', ?, 'report', 't', 'h', 'md', "
        "'pending', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (run_id,),
    )
    conn.commit()
    conn.close()
    finished = svc.finish(run_id, outcome="done", result_excerpt="演练完成")
    assert finished["status"] == "succeeded"
    assert finished["outcome"] == "done"
    assert finished["artifact_ids"] == ["art-r1"]  # 实表回填


def test_finish_failed_requires_error(temp_db: Path) -> None:
    """失败真实性: failed/timeout/needs_human 无 error → RunValidationError。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    for outcome in ("failed", "timeout", "needs_human"):
        with pytest.raises(RunValidationError, match="requires error"):
            svc.finish(run_id, outcome=outcome, error=None)


def test_double_finish_conflicts(temp_db: Path) -> None:
    """CAS: 终态后重复 finish → RunConflictError (409), 不产生第二次终态。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    svc.finish(run_id, outcome="failed", error="e")
    with pytest.raises(RunConflictError, match="requires running"):
        svc.finish(run_id, outcome="failed", error="e again")


def test_wrong_state_transition_conflicts(temp_db: Path) -> None:
    """CAS: queued 直接 finish / claimed 直接 claim → RunConflictError。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    with pytest.raises(RunConflictError):
        svc.finish(run_id, outcome="done")  # queued 不可 finish
    svc.claim(run_id)
    with pytest.raises(RunConflictError):
        svc.claim(run_id)  # claimed 不可重复 claim


def test_cancel_from_active_states(temp_db: Path) -> None:
    """cancel: queued/running → cancelled + outcome=cancelled。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    cancelled = svc.cancel(run_id, reason="owner 中止")
    assert cancelled["status"] == "cancelled"
    assert cancelled["outcome"] == "cancelled"
    # 二次 cancel → 冲突 (cancelled 不在 from 集合)
    with pytest.raises(RunConflictError):
        svc.cancel(run_id)


def test_timeout_outcome_maps_to_timed_out(temp_db: Path) -> None:
    """outcome=timeout → status=timed_out (7 态机对齐)。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    finished = svc.finish(run_id, outcome="timeout", error="超预算")
    assert finished["status"] == "timed_out"
    assert finished["outcome"] == "timeout"


def test_invalid_outcome_rejected(temp_db: Path) -> None:
    """非法 outcome → RunValidationError (白名单 {done,failed,cancelled,timeout,needs_human})。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    with pytest.raises(RunValidationError, match="invalid outcome"):
        svc.finish(run_id, outcome="mock_success")


def test_run_events_written_to_outbox(temp_db: Path) -> None:
    """R-6 前置: claim/start/finish 生命周期各写一条 v1_run outbox 事件。"""
    run_id = _seed_chain(temp_db)
    svc = RunService()
    svc.claim(run_id)
    svc.start(run_id)
    svc.finish(run_id, outcome="failed", error="e")
    conn = sqlite3.connect(str(temp_db))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM v1_outbox WHERE event_type='v1_run' "
            "ORDER BY id ASC").fetchall()
        assert len(rows) == 3
        import json
        events = [json.loads(r[0])["event"] for r in rows]
        assert events == ["claimed", "started", "finished"]
    finally:
        conn.close()


def test_receipt_api_endpoints_via_http(temp_db: Path) -> None:
    """验收⑥: 四端点经真实路由可达; 未知 run 404; 冲突走统一 envelope。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.run_api import router
    from backend.exceptions import register_exception_handlers

    _seed_chain(temp_db)
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    client = TestClient(app)

    r = client.post("/api/v1/runs/run-receipt/claim")
    assert r.status_code == 200
    assert r.json()["item"]["status"] == "claimed"
    r = client.post("/api/v1/runs/run-receipt/start")
    assert r.status_code == 200
    # done 无 artifact → 400 + 统一 envelope (error_code + retryable)
    r = client.post("/api/v1/runs/run-receipt/finish", json={"outcome": "done"})
    assert r.status_code == 400
    body = r.json()
    assert body["error_code"] == "INVALID_PARAM"
    assert body["retryable"] is False
    # failed 收口
    r = client.post("/api/v1/runs/run-receipt/finish",
                    json={"outcome": "failed", "error": "api 演练"})
    assert r.status_code == 200
    # 终态后 finish → 409
    r = client.post("/api/v1/runs/run-receipt/finish",
                    json={"outcome": "failed", "error": "again"})
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONFLICT"
    # 未知 run → 404
    r = client.post("/api/v1/runs/run-nope/claim")
    assert r.status_code == 404
