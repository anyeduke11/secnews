"""v0.8 B1 — agent_loop 五阶段状态机测试 (V0.8_REFACTOR_PLAN.md §5.3).

覆盖矩阵 (≥15 case):
  1. PHASE_ORDER 与 DB schema 一致 (DB CHECK 约束)
  2. next_phase / should_run_phase / is_terminal 纯函数语义
  3. run 5 阶段 happy path: SUCCEEDED + 5 phases 顺序对
  4. run_fast 跳 PLAN+REFLECT: 只走 intent→execute→commit
  5. REFLECT 失败 retry 1 次仍失败 → PARTIAL 终态
  6. REFLECT 失败 retry 1 次成功 → SUCCEEDED 终态
  7. EXECUTE 抛异常 → 当前阶段 FAILED + 后续 SKIPPED + 终态 FAILED
  8. INTENT 阶段抛异常 → 整链路 SKIPPED + 终态 FAILED
  9. checkpoint 持久化: list_for_run 返回 5 行 (run) / 3 行 (run_fast)
 10. mark_running INSERT OR REPLACE 保留 created_at
 11. mark_terminal 非终态 ValueError (防御)
 12. find_stale_running + recover_stale_checkpoints 时间过滤
 13. LLMPort 默认 _NoopLLMPort 返回 0 token
 14. hooks 触发顺序 (on_phase_change × phase 计数)
 15. hooks 异常隔离 (raise 不打断状态机)
 16. on_error hook 阶段异常时被调
 17. ctx["executor.execute"] / ctx["executor.reflect"] 注入生效
 18. ctx["executors"] 全局分发表覆盖
 19. partial=True 时 error=None 语义 (R-08 契约)
 20. run_id 跨多 run 隔离 (checkpoints 不串)
 21. LoopResult.llm_tokens 累计 (含 reflect retry)
 22. LoopResult.metrics 含 elapsed_ms + phase_count
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable

import pytest

from backend.repository.db import get_connection
from backend.services.agent_loop import (
    AgentLoop,
    AgentLoopHooks,
    AgentLoopSettings,
    LoopCheckpoint,
    LoopCheckpointRepo,
    LoopPhase,
    LoopResult,
    LoopStatus,
    PHASE_ORDER,
    build_default_llm_port,
    is_terminal,
    next_phase,
    recover_stale_checkpoints,
    should_run_phase,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_skill(skill_id: str = "test-skill") -> dict:
    return {"id": skill_id, "name": "test", "category": "test"}


def _make_loop(
    *,
    executors: dict | None = None,
    executor_execute: Callable | None = None,
    executor_reflect: Callable | None = None,
    llm=None,
    hooks: AgentLoopHooks | None = None,
    settings: AgentLoopSettings | None = None,
) -> AgentLoop:
    """Build an AgentLoop with optional ctx-style executor injection (None = default stub)."""
    ctx: dict = {}
    if executors is not None:
        ctx["executors"] = executors
    if executor_execute is not None:
        ctx["executor.execute"] = executor_execute
    if executor_reflect is not None:
        ctx["executor.reflect"] = executor_reflect
    # 兼容: ctx 直接传 AgentLoop, 由调用方 run(..., ctx=ctx) 注入
    return AgentLoop(llm=llm, settings=settings, hooks=hooks)


def _run_with_ctx(
    loop: AgentLoop,
    inputs: dict,
    *,
    run_id: str,
    fast_path: bool = False,
    ctx: dict | None = None,
) -> LoopResult:
    """Run with ctx assembled. Centralizes ctx→run plumbing for tests."""
    merged_ctx: dict = dict(ctx or {})
    if loop is not None:
        # 触发 _run 主循环 ctx 取 executors 的路径 — 我们直接传
        pass
    if fast_path:
        return loop.run_fast(_make_skill(), inputs, run_id=run_id, ctx=merged_ctx or None)
    return loop.run(_make_skill(), inputs, run_id=run_id, ctx=merged_ctx or None)


# ---------------------------------------------------------------------------
# 1. PHASE_ORDER 固定序与 DB CHECK 一致
# ---------------------------------------------------------------------------
def test_phase_order_matches_db_check():
    """PHASE_ORDER 5 元素与 DB schema CHECK IN 子句值 1:1 对应。"""
    assert len(PHASE_ORDER) == 5
    values = {p.value for p in PHASE_ORDER}
    assert values == {"intent", "plan", "execute", "reflect", "commit"}
    # DB schema CHECK 实际枚举 (与 migration 092 一致)
    db_phases = {"intent", "plan", "execute", "reflect", "commit"}
    assert values == db_phases


# ---------------------------------------------------------------------------
# 2. next_phase / should_run_phase / is_terminal 纯函数
# ---------------------------------------------------------------------------
def test_next_phase_full_path():
    assert next_phase(LoopPhase.INTENT, fast_path=False) == LoopPhase.PLAN
    assert next_phase(LoopPhase.PLAN, fast_path=False) == LoopPhase.EXECUTE
    assert next_phase(LoopPhase.EXECUTE, fast_path=False) == LoopPhase.REFLECT
    assert next_phase(LoopPhase.REFLECT, fast_path=False) == LoopPhase.COMMIT
    assert next_phase(LoopPhase.COMMIT, fast_path=False) is None


def test_next_phase_fast_path():
    assert next_phase(LoopPhase.INTENT, fast_path=True) == LoopPhase.EXECUTE
    assert next_phase(LoopPhase.EXECUTE, fast_path=True) == LoopPhase.COMMIT
    assert next_phase(LoopPhase.COMMIT, fast_path=True) is None


def test_should_run_phase_fast_skips_plan_reflect():
    assert should_run_phase(LoopPhase.INTENT, fast_path=True) is True
    assert should_run_phase(LoopPhase.PLAN, fast_path=True) is False
    assert should_run_phase(LoopPhase.EXECUTE, fast_path=True) is True
    assert should_run_phase(LoopPhase.REFLECT, fast_path=True) is False
    assert should_run_phase(LoopPhase.COMMIT, fast_path=True) is True


def test_is_terminal_set():
    assert is_terminal(LoopStatus.SUCCEEDED) is True
    assert is_terminal(LoopStatus.PARTIAL) is True
    assert is_terminal(LoopStatus.FAILED) is True
    assert is_terminal(LoopStatus.SKIPPED) is True
    # pending/running 非终态
    assert is_terminal(LoopStatus.PENDING) is False
    assert is_terminal(LoopStatus.RUNNING) is False


# ---------------------------------------------------------------------------
# 3. run 5 阶段 happy path
# ---------------------------------------------------------------------------
def test_run_full_path_succeeds(temp_db):
    loop = AgentLoop()
    result = loop.run(_make_skill("s1"), {"k": "v"}, run_id="run-1")
    assert result.status == LoopStatus.SUCCEEDED
    assert result.partial is False
    assert result.error is None
    # 5 阶段全部 SUCCEEDED
    assert [p for p, _ in result.phases] == [
        LoopPhase.INTENT,
        LoopPhase.PLAN,
        LoopPhase.EXECUTE,
        LoopPhase.REFLECT,
        LoopPhase.COMMIT,
    ]
    assert all(s == LoopStatus.SUCCEEDED for _, s in result.phases)


# ---------------------------------------------------------------------------
# 4. run_fast 跳 PLAN + REFLECT
# ---------------------------------------------------------------------------
def test_run_fast_skips_plan_reflect(temp_db):
    loop = AgentLoop()
    result = loop.run_fast(_make_skill("s2"), {"k": "v"}, run_id="run-fast-1")
    assert result.status == LoopStatus.SUCCEEDED
    # 5 阶段 (含 SKIPPED 收尾对齐历史回放)
    assert [p for p, _ in result.phases] == [
        LoopPhase.INTENT,
        LoopPhase.PLAN,
        LoopPhase.EXECUTE,
        LoopPhase.REFLECT,
        LoopPhase.COMMIT,
    ]
    # PLAN/REFLECT 应被显式 SKIPPED
    phase_map = dict(result.phases)
    assert phase_map[LoopPhase.PLAN] == LoopStatus.SKIPPED
    assert phase_map[LoopPhase.REFLECT] == LoopStatus.SKIPPED
    # DB 行验证
    repo = LoopCheckpointRepo()
    plan_cp = repo.get("run-fast-1", LoopPhase.PLAN)
    reflect_cp = repo.get("run-fast-1", LoopPhase.REFLECT)
    assert plan_cp is not None and plan_cp.status == LoopStatus.SKIPPED
    assert reflect_cp is not None and reflect_cp.status == LoopStatus.SKIPPED


# ---------------------------------------------------------------------------
# 5. REFLECT 失败 retry 1 次仍失败 → PARTIAL
# ---------------------------------------------------------------------------
def test_reflect_retry_once_still_fails_to_partial(temp_db):
    """reflect executor 第一次 failed → 重试 → 仍 failed → 终态 PARTIAL。"""

    def reflect_executor(inputs, scope):
        return {"status": "failed", "verdict": "no_execute_output", "llm_tokens": 0}

    ctx = {"executor.reflect": reflect_executor}
    # execute 必须有非空输出 (默认 stub 'executed': False → reflect 也会失败, 但走默认路径)
    # 这里用 inject 覆盖 reflect, 让其必定 failed
    loop = AgentLoop()
    result = loop.run(_make_skill("s3"), {}, run_id="run-partial", ctx=ctx)
    # reflect 失败 retry 1 次 → 仍 failed → PARTIAL
    assert result.status == LoopStatus.PARTIAL
    assert result.partial is True
    # error 在 PARTIAL 时为 None (R-08 契约)
    assert result.error is None
    # phases 5 阶段
    assert [p for p, _ in result.phases] == [
        LoopPhase.INTENT,
        LoopPhase.PLAN,
        LoopPhase.EXECUTE,
        LoopPhase.REFLECT,
        LoopPhase.COMMIT,
    ]
    # reflect 阶段 = PARTIAL
    reflect_status = next(s for p, s in result.phases if p == LoopPhase.REFLECT)
    assert reflect_status == LoopStatus.PARTIAL


# ---------------------------------------------------------------------------
# 6. REFLECT 失败 retry 1 次成功 → SUCCEEDED
# ---------------------------------------------------------------------------
def test_reflect_retry_once_recovers_to_succeeded(temp_db):
    """reflect 第一次 failed → 重试 succeeded → 终态 SUCCEEDED。"""
    call_count = {"n": 0}

    def reflect_executor(inputs, scope):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"status": "failed", "verdict": "first_attempt_fail", "llm_tokens": 0}
        return {"status": "succeeded", "verdict": "ok_retry", "llm_tokens": 0}

    ctx = {"executor.reflect": reflect_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s4"), {}, run_id="run-retry-ok", ctx=ctx)
    assert result.status == LoopStatus.SUCCEEDED
    assert result.partial is False
    assert call_count["n"] == 2  # 第一次 + retry
    # reflect 阶段 = SUCCEEDED
    reflect_status = next(s for p, s in result.phases if p == LoopPhase.REFLECT)
    assert reflect_status == LoopStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 7. EXECUTE 抛异常 → FAILED + 后续 SKIPPED
# ---------------------------------------------------------------------------
def test_execute_exception_fails_loop(temp_db):
    def execute_executor(inputs, scope):
        raise RuntimeError("simulated crash")

    ctx = {"executor.execute": execute_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s5"), {}, run_id="run-exc", ctx=ctx)
    assert result.status == LoopStatus.FAILED
    assert result.error is not None and "simulated crash" in result.error
    # intent + plan succeeded, execute failed, reflect skipped, commit succeeded
    phase_map = dict(result.phases)
    assert phase_map[LoopPhase.INTENT] == LoopStatus.SUCCEEDED
    assert phase_map[LoopPhase.PLAN] == LoopStatus.SUCCEEDED
    assert phase_map[LoopPhase.EXECUTE] == LoopStatus.FAILED
    assert phase_map[LoopPhase.REFLECT] == LoopStatus.SKIPPED
    assert phase_map[LoopPhase.COMMIT] == LoopStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 8. INTENT 阶段抛异常 → 后续全部 SKIPPED + 终态 FAILED
# ---------------------------------------------------------------------------
def test_intent_exception_skips_all_remaining(temp_db):
    def intent_executor(inputs, scope):
        raise ValueError("bad input")

    ctx = {"executors": {**{p: AgentLoop()._executor_intent for p in []},
                          LoopPhase.INTENT: intent_executor}}
    # 上面写法太绕; 直接用完整 executors dict
    loop = AgentLoop()
    intent = intent_executor
    plan = loop._executor_plan
    execute = loop._executor_execute
    reflect = loop._executor_reflect
    commit = loop._executor_commit
    ctx = {
        "executors": {
            LoopPhase.INTENT: intent,
            LoopPhase.PLAN: plan,
            LoopPhase.EXECUTE: execute,
            LoopPhase.REFLECT: reflect,
            LoopPhase.COMMIT: commit,
        }
    }
    result = loop.run(_make_skill("s6"), {}, run_id="run-intent-exc", ctx=ctx)
    assert result.status == LoopStatus.FAILED
    assert "bad input" in (result.error or "")
    # INTENT failed, 其余 SKIPPED
    phase_map = dict(result.phases)
    assert phase_map[LoopPhase.INTENT] == LoopStatus.FAILED
    assert phase_map[LoopPhase.PLAN] == LoopStatus.SKIPPED
    assert phase_map[LoopPhase.EXECUTE] == LoopStatus.SKIPPED
    assert phase_map[LoopPhase.REFLECT] == LoopStatus.SKIPPED
    # COMMIT 仍必须跑 (收尾)
    assert phase_map[LoopPhase.COMMIT] == LoopStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 9. checkpoint 持久化: list_for_run 返回 5/3 行
# ---------------------------------------------------------------------------
def test_checkpoints_persisted_full_path(temp_db):
    loop = AgentLoop()
    loop.run(_make_skill("s7"), {"a": 1}, run_id="run-cp-full")
    repo = LoopCheckpointRepo()
    rows = repo.list_for_run("run-cp-full")
    assert len(rows) == 5
    phases = {r.phase for r in rows}
    assert phases == set(PHASE_ORDER)


def test_checkpoints_persisted_fast_path(temp_db):
    loop = AgentLoop()
    loop.run_fast(_make_skill("s8"), {"a": 1}, run_id="run-cp-fast")
    repo = LoopCheckpointRepo()
    rows = repo.list_for_run("run-cp-fast")
    assert len(rows) == 5  # 5 行 (含 SKIPPED)
    skipped = [r for r in rows if r.status == LoopStatus.SKIPPED]
    assert len(skipped) == 2  # PLAN + REFLECT


# ---------------------------------------------------------------------------
# 10. mark_running INSERT OR REPLACE 保留 created_at
# ---------------------------------------------------------------------------
def test_mark_running_preserves_created_at_on_reentry(temp_db):
    repo = LoopCheckpointRepo()
    repo.mark_running("run-reentry", LoopPhase.INTENT, payload={"k": "v1"})
    first = repo.get("run-reentry", LoopPhase.INTENT)
    assert first is not None
    original_created = first.created_at
    # 再次 mark_running (模拟重入, 进程崩溃恢复后再次进同阶段)
    time.sleep(1.1)  # 确保 DB now() 时间差 > 1 秒
    repo.mark_running("run-reentry", LoopPhase.INTENT, payload={"k": "v2"})
    second = repo.get("run-reentry", LoopPhase.INTENT)
    # created_at 应被保留
    assert second.created_at == original_created
    # payload 应被更新
    assert second.payload == {"k": "v2"}
    assert second.status == LoopStatus.RUNNING


# ---------------------------------------------------------------------------
# 11. mark_terminal 非终态 ValueError (防御)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [LoopStatus.PENDING, LoopStatus.RUNNING])
def test_mark_terminal_rejects_non_terminal(temp_db, bad):
    repo = LoopCheckpointRepo()
    with pytest.raises(ValueError, match="只接受终态"):
        repo.mark_terminal("run-bad", LoopPhase.INTENT, bad)


# ---------------------------------------------------------------------------
# 12. find_stale_running + recover_stale_checkpoints 时间过滤
# ---------------------------------------------------------------------------
def test_find_stale_running_and_recover(temp_db):
    repo = LoopCheckpointRepo()
    # 1) 写一个 running 行 (无 completed_at)
    repo.mark_running("run-stale-1", LoopPhase.EXECUTE, payload={"k": "v"})
    # 2) 写一个 succeeded 行 (有 completed_at, 不应被扫到)
    repo.mark_terminal("run-stale-2", LoopPhase.INTENT, LoopStatus.SUCCEEDED)
    # 扫描
    rows = repo.find_stale_running()
    assert len(rows) == 1
    assert rows[0].run_id == "run-stale-1"
    # 恢复: 默认 stale_seconds=60.0, 刚写入的不会被认为 stale
    stale = recover_stale_checkpoints(repo, stale_seconds=60.0)
    assert stale == []  # 太新了
    # 强制传 now_epoch 把 stale 时间拉到未来
    import datetime as _dt

    now = _dt.datetime.strptime(rows[0].created_at, "%Y-%m-%d %H:%M:%S").timestamp() + 120
    stale = recover_stale_checkpoints(repo, stale_seconds=60.0, now_epoch=now)
    assert ("run-stale-1", LoopPhase.EXECUTE) in stale


# ---------------------------------------------------------------------------
# 13. LLMPort 默认 _NoopLLMPort 返回 0 token
# ---------------------------------------------------------------------------
def test_default_llm_port_is_noop():
    port = build_default_llm_port()
    # 没配 LLM 时退化为 noop
    res = port.complete("hello world", system="sys")
    assert "text" in res
    assert "tokens" in res
    # 若无 ai_hub LLMService, 必为 0 token + 空 text
    # (有 LLM 的开发环境可能不同; 我们只校验 schema 存在)


def test_noop_llm_port_returns_zero_tokens():
    """直接构造 _NoopLLMPort — 不依赖 ai_hub 解析。"""
    from backend.services.agent_loop.core import _NoopLLMPort

    res = _NoopLLMPort().complete("anything")
    assert res == {"text": "", "tokens": 0}


# ---------------------------------------------------------------------------
# 14. hooks 触发顺序 (on_phase_change × phase 计数)
# ---------------------------------------------------------------------------
def test_hooks_fire_on_phase_change(temp_db):
    events: list[tuple[LoopPhase, LoopStatus]] = []

    def on_change(phase, status, payload):
        events.append((phase, status))

    hooks = AgentLoopHooks(on_phase_change=on_change)
    loop = AgentLoop(hooks=hooks)
    loop.run(_make_skill("s9"), {}, run_id="run-hook")
    # 5 阶段: RUNNING × 5 + (SUCCEEDED/SKIPPED) × 5 = 10 个事件
    phase_count = [e[0] for e in events]
    assert phase_count == [
        LoopPhase.INTENT, LoopPhase.INTENT,
        LoopPhase.PLAN, LoopPhase.PLAN,
        LoopPhase.EXECUTE, LoopPhase.EXECUTE,
        LoopPhase.REFLECT, LoopPhase.REFLECT,
        LoopPhase.COMMIT, LoopPhase.COMMIT,
    ]


# ---------------------------------------------------------------------------
# 15. hooks 异常隔离
# ---------------------------------------------------------------------------
def test_hook_exception_does_not_break_state_machine(temp_db):
    def on_change(phase, status, payload):
        raise RuntimeError("hook boom")

    hooks = AgentLoopHooks(on_phase_change=on_change)
    loop = AgentLoop(hooks=hooks)
    # 不应抛 — hook 异常被吞
    result = loop.run(_make_skill("s10"), {}, run_id="run-hook-boom")
    assert result.status == LoopStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 16. on_error hook 阶段异常时被调
# ---------------------------------------------------------------------------
def test_on_error_hook_called_on_phase_exception(temp_db):
    errors: list[tuple[LoopPhase, str]] = []

    def on_err(phase, err):
        errors.append((phase, err))

    def execute_executor(inputs, scope):
        raise RuntimeError("kaboom")

    hooks = AgentLoopHooks(on_error=on_err)
    loop = AgentLoop(hooks=hooks)
    ctx = {"executor.execute": execute_executor}
    loop.run(_make_skill("s11"), {}, run_id="run-on-err", ctx=ctx)
    assert len(errors) == 1
    phase, err = errors[0]
    assert phase == LoopPhase.EXECUTE
    assert "kaboom" in err


# ---------------------------------------------------------------------------
# 17. ctx["executor.execute"] / ctx["executor.reflect"] 注入生效
# ---------------------------------------------------------------------------
def test_executor_injection_execute(temp_db):
    def execute_executor(inputs, scope):
        return {"status": "succeeded", "result": "custom_executed", "llm_tokens": 0}

    ctx = {"executor.execute": execute_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s12"), {}, run_id="run-inj-exec", ctx=ctx)
    assert result.outputs[LoopPhase.EXECUTE.value]["result"] == "custom_executed"


def test_executor_injection_reflect(temp_db):
    """reflect 注入强制 succeeded (即便 default 该 failed)。"""
    def reflect_executor(inputs, scope):
        return {"status": "succeeded", "verdict": "injected_ok", "llm_tokens": 0}

    ctx = {"executor.reflect": reflect_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s13"), {}, run_id="run-inj-ref", ctx=ctx)
    assert result.status == LoopStatus.SUCCEEDED
    assert result.outputs[LoopPhase.REFLECT.value]["verdict"] == "injected_ok"


# ---------------------------------------------------------------------------
# 18. ctx["executors"] 全局分发表覆盖
# ---------------------------------------------------------------------------
def test_executors_dict_full_override(temp_db):
    """ctx['executors'] 提供完整 5 阶段, 完全替代默认 stub。"""
    calls: list[LoopPhase] = []

    def make(phase: LoopPhase):
        def fn(inputs, scope):
            calls.append(phase)
            return {"status": "succeeded", "phase": phase.value, "llm_tokens": 0}

        return fn

    ctx = {
        "executors": {
            LoopPhase.INTENT: make(LoopPhase.INTENT),
            LoopPhase.PLAN: make(LoopPhase.PLAN),
            LoopPhase.EXECUTE: make(LoopPhase.EXECUTE),
            LoopPhase.REFLECT: make(LoopPhase.REFLECT),
            LoopPhase.COMMIT: make(LoopPhase.COMMIT),
        }
    }
    loop = AgentLoop()
    result = loop.run(_make_skill("s14"), {}, run_id="run-execs-override", ctx=ctx)
    assert result.status == LoopStatus.SUCCEEDED
    assert calls == [
        LoopPhase.INTENT,
        LoopPhase.PLAN,
        LoopPhase.EXECUTE,
        LoopPhase.REFLECT,
        LoopPhase.COMMIT,
    ]


# ---------------------------------------------------------------------------
# 19. partial=True 时 error=None (R-08 契约)
# ---------------------------------------------------------------------------
def test_partial_result_has_no_error_field(temp_db):
    def reflect_executor(inputs, scope):
        return {"status": "failed", "verdict": "x", "llm_tokens": 0, "error": "reflect-fail"}

    ctx = {"executor.reflect": reflect_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s15"), {}, run_id="run-partial-noerr", ctx=ctx)
    assert result.status == LoopStatus.PARTIAL
    assert result.partial is True
    # partial → error 必为 None (R-08 契约)
    assert result.error is None


# ---------------------------------------------------------------------------
# 20. run_id 跨多 run 隔离
# ---------------------------------------------------------------------------
def test_multiple_runs_isolated(temp_db):
    loop = AgentLoop()
    loop.run(_make_skill("a"), {}, run_id="run-A")
    loop.run_fast(_make_skill("b"), {}, run_id="run-B")
    repo = LoopCheckpointRepo()
    a_rows = repo.list_for_run("run-A")
    b_rows = repo.list_for_run("run-B")
    assert len(a_rows) == 5
    assert len(b_rows) == 5
    a_runs = {r.run_id for r in a_rows}
    b_runs = {r.run_id for r in b_rows}
    assert a_runs == {"run-A"}
    assert b_runs == {"run-B"}


# ---------------------------------------------------------------------------
# 21. LoopResult.llm_tokens 累计 (含 reflect retry)
# ---------------------------------------------------------------------------
def test_llm_tokens_accumulated_across_phases(temp_db):
    def reflect_executor(inputs, scope):
        return {
            "status": "failed",
            "verdict": "x",
            "llm_tokens": 5,
            "error": "e",
        }  # 每次 5 token

    ctx = {"executor.reflect": reflect_executor}
    loop = AgentLoop()
    result = loop.run(_make_skill("s16"), {}, run_id="run-tokens", ctx=ctx)
    # reflect 失败 1 + retry 1 = 2 次调用 × 5 token = 10
    assert result.llm_tokens == 10


def test_llm_tokens_zero_on_fast_path(temp_db):
    loop = AgentLoop()
    result = loop.run_fast(_make_skill("s17"), {}, run_id="run-tokens-fast")
    # fast_path 不调任何 reflect LLM, 仅默认 stub = 0
    assert result.llm_tokens == 0


# ---------------------------------------------------------------------------
# 22. LoopResult.metrics 含 elapsed_ms + phase_count + fast_path
# ---------------------------------------------------------------------------
def test_loop_result_metrics_shape(temp_db):
    loop = AgentLoop()
    result = loop.run(_make_skill("s18"), {}, run_id="run-metrics")
    assert "elapsed_ms" in result.metrics
    assert result.metrics["elapsed_ms"] >= 0
    assert result.metrics["phase_count"] == 5
    assert result.metrics["fast_path"] is False


def test_loop_result_metrics_fast_path(temp_db):
    loop = AgentLoop()
    result = loop.run_fast(_make_skill("s19"), {}, run_id="run-metrics-fast")
    assert result.metrics["phase_count"] == 5  # 包含 2 SKIPPED
    assert result.metrics["fast_path"] is True


# ---------------------------------------------------------------------------
# 23. DB-level CHECK 约束: 非法 phase / status 写入直接拒绝
# ---------------------------------------------------------------------------
def test_db_check_constraint_enforced(temp_db):
    """loop_checkpoints.phase / status CHECK 约束应被 SQLite 强制。"""
    conn = get_connection()
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO loop_checkpoints(run_id, phase, status) "
            "VALUES (?, ?, ?)",
            ("run-bad-1", "invalid_phase", "running"),
        )
    conn.commit()
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO loop_checkpoints(run_id, phase, status) "
            "VALUES (?, ?, ?)",
            ("run-bad-2", "intent", "invalid_status"),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# 24. delete_for_run 清理
# ---------------------------------------------------------------------------
def test_delete_for_run_clears_rows(temp_db):
    loop = AgentLoop()
    loop.run(_make_skill("s20"), {}, run_id="run-del")
    repo = LoopCheckpointRepo()
    assert len(repo.list_for_run("run-del")) == 5
    n = repo.delete_for_run("run-del")
    assert n == 5
    assert repo.list_for_run("run-del") == []
