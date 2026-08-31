"""v0.7 Batch 1 — 可观测性单测。

覆盖:
1. record_llm_call 真值/估算 tokens 分流 + trace_id 兜底 + 失败路径落表
2. success_stats_24h latency p50 (SQLite ROW_NUMBER trick)
3. observability_records 4 表写入 helper (job_runs / agent_runs /
   process_events / audit_log) 异常吞错不阻塞
4. observability contextvar trace_id set/reset 闭环
5. log_event bind 模式 — extras 进入 record.extra (loguru 序列化路径)
6. instrument_job → job_runs 双阶段 (running → ok/failed)
"""
from __future__ import annotations

from backend.observability import (
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)
from backend.observability_records import (
    finish_agent_run,
    finish_job_run,
    record_audit,
    record_process_event,
    start_agent_run,
    start_job_run,
)
from backend.repository.db import get_connection
from backend.services.ai_hub.usage import (
    recent_calls,
    record_llm_call,
    success_stats_24h,
)

# ── record_llm_call ─────────────────────────────────────────────


def test_record_llm_call_real_tokens_ok(temp_db):
    record_llm_call(
        provider="sensenova", model="SenseChat-32B", task="t1_score",
        prompt_tokens=10, completion_tokens=20, total_tokens=30,
        cost_usd=0.001, latency_ms=120, ok=True, scene="t1_score",
        trace_id="t-001",
    )
    row = get_connection().execute(
        "SELECT * FROM llm_usage_log WHERE trace_id = ?", ("t-001",)
    ).fetchone()
    assert row is not None
    assert int(row["ok"]) == 1
    assert int(row["tokens"]) == 30
    assert int(row["tokens_estimated"]) == 0
    assert row["trace_id"] == "t-001"


def test_record_llm_call_estimated_tokens(temp_db):
    record_llm_call(
        provider="ollama", model="qwen2.5", task="t3_summary",
        prompt="a" * 80, response="b" * 40, ok=True, scene="t3_summary",
        trace_id="t-002",
    )
    row = get_connection().execute(
        "SELECT tokens, tokens_estimated FROM llm_usage_log WHERE trace_id = ?",
        ("t-002",),
    ).fetchone()
    # (80+40)//4 = 30
    assert int(row["tokens"]) == 30
    assert int(row["tokens_estimated"]) == 1


def test_record_llm_call_failure_path(temp_db):
    record_llm_call(
        provider="sensenova", model="SenseChat-32B", task="t1_score",
        latency_ms=300, ok=False, error="HTTP 502 from upstream",
        scene="t1_score", trace_id="t-003",
    )
    row = get_connection().execute(
        "SELECT ok, error FROM llm_usage_log WHERE trace_id = ?", ("t-003",)
    ).fetchone()
    assert int(row["ok"]) == 0
    assert "HTTP 502" in row["error"]


def test_record_llm_call_trace_id_fallback_from_contextvar(temp_db):
    """调用方不传 trace_id 时从 observability contextvar 兜底取。"""
    token = set_trace_id("ctx-456")
    try:
        record_llm_call(
            provider="sensenova", model="SenseChat-32B", task="t1_score",
            total_tokens=10, ok=True, scene="t1_score",
        )
    finally:
        reset_trace_id(token)
    row = get_connection().execute(
        "SELECT trace_id FROM llm_usage_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["trace_id"] == "ctx-456"


# ── success_stats_24h ──────────────────────────────────────────


def test_success_stats_24h_p50(temp_db):
    """3 行 ok=1 不同 latency → 中位数 = 第 2 行。"""
    for lat, tid in [(100, "p50-a"), (200, "p50-b"), (300, "p50-c")]:
        record_llm_call(
            provider="sensenova", model="SenseChat-32B", task="t1_score",
            total_tokens=10, latency_ms=lat, ok=True, scene="t1_score",
            trace_id=tid,
        )
    # 1 失败, 不计入 p50
    record_llm_call(
        provider="sensenova", model="SenseChat-32B", task="t1_score",
        latency_ms=999, ok=False, error="x", scene="t1_score", trace_id="p50-fail",
    )
    stats = success_stats_24h()
    assert stats["ok_calls_24h"] == 3
    assert stats["fail_calls_24h"] == 1
    assert stats["success_rate"] == 0.75
    # 中位行: (cnt+1)/2 = (3+1)/2 = 2 → rn=2 → 200ms
    assert stats["latency_p50_ms"] == 200.0


def test_recent_calls_returns_newest_first(temp_db):
    record_llm_call(
        provider="sensenova", model="X", task="t1_score",
        total_tokens=1, ok=True, scene="t1_score", trace_id="rc-a",
    )
    record_llm_call(
        provider="sensenova", model="X", task="t1_score",
        total_tokens=1, ok=True, scene="t1_score", trace_id="rc-b",
    )
    calls = recent_calls(10)
    assert len(calls) >= 2
    assert calls[0]["trace_id"] == "rc-b"
    assert calls[1]["trace_id"] == "rc-a"


# ── observability_records ──────────────────────────────────────


def test_job_runs_dual_phase(temp_db):
    rid = start_job_run("t", "t-123", trace_id="t-123")
    assert rid is not None
    finish_job_run(rid, ok=True, duration_ms=50)
    row = get_connection().execute(
        "SELECT status, duration_ms FROM job_runs WHERE id = ?", (rid,)
    ).fetchone()
    assert row["status"] == "ok"
    assert int(row["duration_ms"]) == 50


def test_job_runs_finish_failed(temp_db):
    rid = start_job_run("t", "t-456")
    finish_job_run(rid, ok=False, duration_ms=12, error="boom")
    row = get_connection().execute(
        "SELECT status, error FROM job_runs WHERE id = ?", (rid,)
    ).fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "boom"


def test_job_runs_finish_with_none_rowid_noop(temp_db):
    # start_job_run 失败时返 None; finish_* 收到 None 直接返回, 不抛错
    finish_job_run(None, ok=True, duration_ms=0)


def test_agent_runs_dual_phase(temp_db):
    rid = start_agent_run(
        agent="pi", protocol="jsonl", task_kind="digest",
        trigger_source="api", trace_id="ag-1",
    )
    finish_agent_run(rid, ok=True, duration_ms=200,
                     result_excerpt="hello world")
    row = get_connection().execute(
        "SELECT status, duration_ms, result_excerpt FROM agent_runs WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row["status"] == "ok"
    assert int(row["duration_ms"]) == 200
    assert row["result_excerpt"] == "hello world"


def test_process_events_appends(temp_db):
    record_process_event(name="dsh", event="spawn", pid=999, detail="cmd x")
    row = get_connection().execute(
        "SELECT name, event, pid FROM process_events WHERE name='dsh' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["event"] == "spawn"
    assert int(row["pid"]) == 999


def test_record_audit_appends(temp_db):
    record_audit(actor="web", action="llm_config.update",
                 target="default_provider", detail={"to": "ollama"},
                 trace_id="au-1")
    row = get_connection().execute(
        "SELECT actor, action, target FROM audit_log WHERE trace_id='au-1'"
    ).fetchone()
    assert row["actor"] == "web"
    assert row["action"] == "llm_config.update"


def test_observability_records_swallows_exceptions(temp_db, monkeypatch):
    """DB 故障时观测写入必须吞错, 永不阻塞业务。"""
    from backend import observability_records

    def _boom(*a, **kw):
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(observability_records, "get_connection", _boom)
    # 四个 helper 全部不应抛错
    start_job_run("t", "t-x")
    finish_job_run(1, ok=True, duration_ms=1)
    start_agent_run("a", "acp")
    finish_agent_run(1, ok=True, duration_ms=1)
    record_process_event(name="x", event="spawn")
    record_audit(actor="x", action="x")


# ── observability contextvar ───────────────────────────────────


def test_trace_id_contextvar_isolated():
    """contextvar 在不同 set/reset 调用间互不影响。"""
    assert get_trace_id() is None
    tok = set_trace_id("a")
    assert get_trace_id() == "a"
    tok2 = set_trace_id("b")
    assert get_trace_id() == "b"
    reset_trace_id(tok2)
    assert get_trace_id() == "a"
    reset_trace_id(tok)
    assert get_trace_id() is None


# ── log_event bind pattern ─────────────────────────────────────


def test_log_event_flattens_extras_into_extra(temp_db):
    """log_event 用 bind 模式, extras 进入 record.extra 顶层 (loguru JSON)。"""
    import json as _json

    from backend.logging_config import logger
    from backend.observability import log_event

    token = set_trace_id("lg-1")
    try:
        # loguru sink 收到的是序列化字符串 (logger.add(serialize=True))。
        # 解析后 record.extra 顶层应含 method/path/status/event/trace_id,
        # 不应嵌套到 record.extra.extra。
        captured: list[dict] = []

        class _CaptureSink:
            def write(self, msg):
                try:
                    d = _json.loads(msg)
                except Exception:
                    return
                captured.append(d)

        sink_id = logger.add(_CaptureSink(), serialize=True, level="DEBUG",
                             format="{message}")
        try:
            log_event("test_event", method="GET", path="/x", status=200)
        finally:
            logger.remove(sink_id)
        assert len(captured) >= 1
        rec = captured[-1]["record"]
        extra = rec["extra"]
        # 顶层扁平: 关键字段都在 record.extra (不在 record.extra.extra)
        assert "method" not in extra.get("extra", {}), (
            f"extras nested under record.extra.extra: {extra}"
        )
        assert extra.get("event") == "test_event"
        assert extra.get("trace_id") == "lg-1"
        assert extra.get("method") == "GET"
        assert extra.get("path") == "/x"
        assert extra.get("status") == 200
    finally:
        reset_trace_id(token)


# ── instrument_job (链路级, 走真实装饰器) ───────────────────────


def test_instrument_job_writes_job_runs(temp_db):
    from backend.scheduler.jobs._runtime import instrument_job

    @instrument_job("dummy_test")
    async def _j():
        return "ok"

    import asyncio
    asyncio.run(_j())

    rows = get_connection().execute(
        "SELECT status, duration_ms FROM job_runs WHERE job_type = 'dummy_test'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert int(rows[0]["duration_ms"]) >= 0


def test_instrument_job_writes_failed(temp_db):
    from backend.scheduler.jobs._runtime import instrument_job

    @instrument_job("dummy_fail")
    async def _j():
        raise RuntimeError("simulated")

    import asyncio
    try:
        asyncio.run(_j())
    except RuntimeError:
        pass  # 装饰器 finally 必走, 业务异常应冒泡 — 测试只验证 job_runs 已落

    rows = get_connection().execute(
        "SELECT status, error FROM job_runs WHERE job_type = 'dummy_fail'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert "simulated" in rows[0]["error"]