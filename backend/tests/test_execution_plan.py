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

import pytest

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


# ── C3-2: ExecutionPlan 状态机 (submit/approve/reject) ────────────────


def _plan_payload() -> dict:
    return {
        "commands": [["python", "scripts/cve_brief.py", "--cve", "CVE-2026-1234"]],
        "writable_paths": ["output/"],
        "readable_paths": ["materials/"],
        "network": [],
        "command_timeout_sec": 120,
        "total_timeout_sec": 900,
        "output_artifact": {
            "kind": "report", "title": "CVE-2026-1234 brief", "acceptance_notes": "含评分与影响面",
        },
    }


def test_submit_creates_draft_and_hash(temp_db: Path) -> None:
    """submit → draft 信封 + boundary_hash 稳定 (同 plan 同 hash)。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanService,
        boundary_hash,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    env = svc.submit(run_id, _plan_payload(), submitted_by="drill", source="manual")
    assert env["status"] == "draft"
    assert env["source"] == "manual"
    assert env["boundary_hash"] == boundary_hash(_plan_payload())
    assert env["plan"]["commands"] == [_plan_payload()["commands"][0]]
    # 再算一次 hash → 稳定
    assert boundary_hash(_plan_payload()) == env["boundary_hash"]


def test_approve_freezes_and_immutable(temp_db: Path) -> None:
    """L1: draft → approved (冻结); 再 submit → 409 (immutable)。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanConflictError,
        ExecutionPlanService,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    svc.submit(run_id, _plan_payload(), submitted_by="drill")
    env = svc.approve(run_id, reviewed_by="owner")
    assert env["status"] == "approved"
    assert env["approved_by"] == "owner"
    assert env["approved_at"] is not None
    with pytest.raises(ExecutionPlanConflictError, match="immutable"):
        svc.submit(run_id, _plan_payload(), submitted_by="drill")


def test_reject_then_resubmit(temp_db: Path) -> None:
    """rejected 后可重新 submit 覆盖 (P10 §4: 历史留 audit_log 不拆表)。"""
    from backend.services.execution_plan.service import ExecutionPlanService

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    svc.submit(run_id, _plan_payload(), submitted_by="drill")
    env = svc.reject(run_id, reviewed_by="owner", reason="网络未收窄")
    assert env["status"] == "rejected"
    assert env["reject_reason"] == "网络未收窄"
    env2 = svc.submit(run_id, _plan_payload(), submitted_by="drill", source="manual")
    assert env2["status"] == "draft"


def test_reject_requires_reason(temp_db: Path) -> None:
    """默认拒绝语义的显式表达: reject 无 reason → 400。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanService,
        ExecutionPlanValidationError,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    svc.submit(run_id, _plan_payload(), submitted_by="drill")
    with pytest.raises(ExecutionPlanValidationError, match="requires reason"):
        svc.reject(run_id, reviewed_by="owner", reason="  ")


def test_submit_invalid_schema_rejected(temp_db: Path) -> None:
    """schema 校验 fail-loud: 空 commands / 非法 artifact kind → 400。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanService,
        ExecutionPlanValidationError,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    bad = _plan_payload() | {"commands": []}
    with pytest.raises(ExecutionPlanValidationError, match="schema"):
        svc.submit(run_id, bad, submitted_by="drill")
    bad2 = _plan_payload() | {"output_artifact": {"kind": "nuclear", "title": "t"}}
    with pytest.raises(ExecutionPlanValidationError):
        svc.submit(run_id, bad2, submitted_by="drill")


def test_plan_only_in_queued_or_claimed(temp_db: Path) -> None:
    """running/terminal 不可改边界 (L1: 执行期不可改计划)。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanConflictError,
        ExecutionPlanService,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    RunService().claim(run_id)
    RunService().start(run_id)
    with pytest.raises(ExecutionPlanConflictError, match="queued/claimed"):
        svc.submit(run_id, _plan_payload(), submitted_by="drill")


def test_tampered_plan_detected_on_approve(temp_db: Path) -> None:
    """L4 完整性: 落库后 plan 被篡改 → approve 时 hash 不符 → 409。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanConflictError,
        ExecutionPlanService,
    )

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    svc.submit(run_id, _plan_payload(), submitted_by="drill")
    # 模拟落库后被篡改 (直改 DB)
    conn = sqlite3.connect(str(temp_db))
    env = conn.execute(
        "SELECT execution_plan_json FROM v1_runs WHERE id = ?", (run_id,)).fetchone()[0]
    import json
    env_obj = json.loads(env)
    env_obj["plan"]["commands"].append(["rm", "-rf", "/"])
    conn.execute(
        "UPDATE v1_runs SET execution_plan_json = ? WHERE id = ?",
        (json.dumps(env_obj, ensure_ascii=False), run_id))
    conn.commit()
    conn.close()
    with pytest.raises(ExecutionPlanConflictError, match="boundary_hash 不符"):
        svc.approve(run_id, reviewed_by="owner")


def test_approve_without_draft_404(temp_db: Path) -> None:
    """无 plan 草稿直接 approve → 404 (前端空态依据)。"""
    from backend.services.execution_plan.service import (
        ExecutionPlanNotFoundError,
        ExecutionPlanService,
    )

    run_id = _seed_run(temp_db)
    with pytest.raises(ExecutionPlanNotFoundError):
        ExecutionPlanService().approve(run_id, reviewed_by="owner")


def test_audit_trail_written(temp_db: Path) -> None:
    """L4 审计: submit/approve/reject 全落 audit_log (plan.*)。"""
    from backend.services.execution_plan.service import ExecutionPlanService

    run_id = _seed_run(temp_db)
    svc = ExecutionPlanService()
    svc.submit(run_id, _plan_payload(), submitted_by="drill")
    svc.approve(run_id, reviewed_by="owner")
    conn = sqlite3.connect(str(temp_db))
    try:
        actions = [r[0] for r in conn.execute(
            "SELECT action FROM audit_log WHERE target = ? ORDER BY id",
            (f"run:{run_id}",)).fetchall()]
        assert actions == ["plan.submit", "plan.approve"]
    finally:
        conn.close()


# ── C3-3: ai_hub 草稿生成 + 人工兜底 ─────────────────────────────────


def _fake_llm(payload: dict | str | None):
    """llm_service.generate 的 async fake。"""
    import json as _json

    async def _fake(prompt: str, task: str = "chat", **kw):
        if isinstance(payload, str):
            return payload
        return _json.dumps(payload, ensure_ascii=False)
    return _fake


def test_generate_plan_draft_happy_path(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """合法 LLM 输出 → source=ai_draft 的 draft 提交。"""
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.generator import generate_plan_draft

    run_id = _seed_run(temp_db)
    good = _plan_payload()
    monkeypatch.setattr(llm_service, "generate", _fake_llm(good))
    env = generate_plan_draft(
        run_id=run_id,
        action={"title": "CVE brief", "plan": "汇总本地产物", "success_criteria": "含评分", "expected_artifacts": ["brief"]},
        submitted_by="drill",
    )
    assert env["status"] == "draft"
    assert env["source"] == "ai_draft"
    assert env["submitted_by"] == "drill"
    assert env["plan"]["commands"] == good["commands"]


def test_generate_plan_prompt_contains_action_fields(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """prompt 必须携带 action 既有字段 (title/plan/success_criteria) — 起草依据。"""
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.generator import build_plan_prompt, generate_plan_draft

    captured: dict[str, str] = {}

    async def _capture(prompt: str, task: str = "chat", **kw):
        captured["prompt"] = prompt
        captured["task"] = task
        import json as _json
        return _json.dumps(_plan_payload(), ensure_ascii=False)

    run_id = _seed_run(temp_db)
    monkeypatch.setattr(llm_service, "generate", _capture)
    action = {"title": "CVE brief X", "plan": "读材料写简报", "success_criteria": "含 CVSS"}
    generate_plan_draft(run_id=run_id, action=action)
    assert "CVE brief X" in captured["prompt"]
    assert "读材料写简报" in captured["prompt"]
    assert "含 CVSS" in captured["prompt"]
    assert captured["task"] == "execution_plan_draft"
    assert "最小权限" in build_plan_prompt(action)  # 红线约束写进 prompt


def test_generate_plan_invalid_json_falls_back(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 输出不可解析 → ExecutionPlanGenerationError (前端落人工手写兜底)。"""
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.generator import (
        ExecutionPlanGenerationError,
        generate_plan_draft,
    )

    run_id = _seed_run(temp_db)
    monkeypatch.setattr(llm_service, "generate", _fake_llm("这不是 JSON"))
    with pytest.raises(ExecutionPlanGenerationError, match="无 JSON 对象"):
        generate_plan_draft(run_id=run_id, action={"title": "t", "plan": "p"})


def test_generate_plan_schema_invalid_falls_back(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 幻觉字段 (schema 不过) → GenerationError + 人工兜底提示。"""
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.generator import (
        ExecutionPlanGenerationError,
        generate_plan_draft,
    )

    run_id = _seed_run(temp_db)
    monkeypatch.setattr(llm_service, "generate", _fake_llm({"commands": []}))
    with pytest.raises(ExecutionPlanGenerationError, match="人工手写兜底"):
        generate_plan_draft(run_id=run_id, action={"title": "t", "plan": "p"})


def test_generate_plan_llm_down_falls_back(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 不可用 → GenerationError (fail-loud, 不静默造空 plan)。"""
    from backend.services.ai_hub.gateway import llm_service
    from backend.services.execution_plan.generator import (
        ExecutionPlanGenerationError,
        generate_plan_draft,
    )

    run_id = _seed_run(temp_db)

    async def _boom(prompt: str, task: str = "chat", **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm_service, "generate", _boom)
    with pytest.raises(ExecutionPlanGenerationError, match="LLM 调用失败"):
        generate_plan_draft(run_id=run_id, action={"title": "t", "plan": "p"})
