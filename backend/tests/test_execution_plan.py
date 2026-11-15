"""v0.8.9 P3: ExecutionPlan 边界协议回归门禁（D2 裁决：另加三列，plan_json 语义不动）。

覆盖（随各 commit 递增）:
- C3-1: migration 136 三列存在 + claim 落 executor='manual';
- C3-2: schema 校验 / freeze 冻结 immutable / boundary_hash 稳定 / approve-reject 状态机;
- C3-3: ai_hub 草稿生成（mock LLM）+ 人工手写兜底 + 非法 LLM 输出降级;
- C3-4: plan API 端点（submit/approve/reject/get 经真实路由）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.repository.action_repo import ActionRepository
from backend.repository.judgment_repo import JudgmentRepository
from backend.repository.run_repo import RunRepository
from backend.services.run_service import RunService


def _seed_run(temp_db: Path, run_id: str = "run-plan-test") -> str:
    """最小链: judgment(published) → action → run(queued, direct)。返回 run_id。"""
    JudgmentRepository().insert({
        "id": "jd-plan", "case_id": "case-plan", "claim_type": "finding",
        "claim": "c", "confidence": "medium", "evidence_refs": [],
        "unknowns": [], "status": "published", "wiki_path": "items/jd-plan.md",
        "published_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    ActionRepository().insert({
        "id": "act-plan", "case_id": "case-plan", "judgment_id": "jd-plan",
        "title": "plan 演练", "plan": "p", "plan_hash": "h", "status": "planned",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    RunRepository().insert({
        "id": run_id, "action_id": "act-plan", "attempt": 1,
        "protocol": "direct", "idempotency_key": f"idem-{run_id}",
        "trigger_source": "user",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    return run_id


# ── C3-1: migration 136 三列 + claim executor ────────────────────────


def test_migration136_columns_exist(temp_db: Path) -> None:
    """D2 裁决: v1_runs 必有 executor / boundary_hash / execution_plan_json 三列
    （且 plan_json 账本列不受影响）。"""
    _seed_run(temp_db)
    conn = sqlite3.connect(str(temp_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(v1_runs)").fetchall()}
        assert {"executor", "boundary_hash", "execution_plan_json", "plan_json"} <= cols
        # 三新列默认 NULL（plan_json 账本列不受影响）
        row = conn.execute(
            "SELECT executor, boundary_hash, execution_plan_json FROM v1_runs"
        ).fetchone()
        assert row == (None, None, None)
    finally:
        conn.close()


def test_claim_sets_executor_manual(temp_db: Path) -> None:
    """D4/D2: 人工 claim 落 executor='manual'（pi 派发 R-3 传 'pi'）。"""
    run_id = _seed_run(temp_db)
    svc = RunService()
    claimed = svc.claim(run_id)
    assert claimed["status"] == "claimed"
    assert claimed["executor"] == "manual"
    conn = sqlite3.connect(str(temp_db))
    try:
        v = conn.execute(
            "SELECT executor FROM v1_runs WHERE id = ?", (run_id,)).fetchone()[0]
        assert v == "manual"
    finally:
        conn.close()


def test_claim_custom_executor_for_pi(temp_db: Path) -> None:
    """R-3 前置: pi 派发可传 executor='pi'。"""
    run_id = _seed_run(temp_db, "run-plan-pi")
    claimed = RunService().claim(run_id, executor="pi")
    assert claimed["executor"] == "pi"
