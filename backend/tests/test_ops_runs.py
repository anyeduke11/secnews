"""v0.8.6 P0-5: E4 misfire 全量声明 + run record 统一 + /api/ops/runs。

- E4: create_scheduler job_defaults 全量 misfire_grace_time=900 (58 job
  统一继承, 不再 55 个裸奔默认 1s 静默丢弃)
- run record 统一: ensure_instrumented 注册口幂等包装 + scheduler
  _ensure_run_records 对全部 job 换 func
- 丢弃→记录: EVENT_MISSED listener → record_missed_job_run (status=missed)
- /api/ops/runs: 失败优先列表 + 窗口 summary + stale_running 僵尸检测

验收 (PRD P0-5): 任一 job 失败 24h 内可在 UI 查到原因。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.ops_runs_api import router as ops_router
from backend.observability_records import record_missed_job_run
from backend.repository.db import get_connection
from backend.scheduler import jobs as jobs_mod
from backend.scheduler.scheduler import HotspotScheduler, create_scheduler

# ---------------------------------------------------------------------------
# E4: misfire 全量声明
# ---------------------------------------------------------------------------


def test_job_defaults_declare_misfire_grace() -> None:
    """E4: job_defaults 必须全量声明 misfire_grace_time (默认 1s 的静默丢弃修复)。"""
    defaults = create_scheduler()._job_defaults  # type: ignore[attr-defined]
    assert defaults.get("misfire_grace_time") == 900
    assert defaults.get("max_instances") == 1
    assert defaults.get("coalesce") is True


def test_started_job_inherits_grace_900() -> None:
    """E4 生效证明: start 后 pending job 从 job_defaults 填充 grace=900。

    (APScheduler 语义: undefined 选项在调度时才被 defaults 替换 —
    pending 阶段 hasattr 为 False, 必须启动后断言。)
    """
    import asyncio

    async def scenario() -> None:
        s = create_scheduler()

        async def dummy() -> None:
            return None

        s.add_job(dummy, trigger="interval", seconds=3600, id="x")
        s.start()
        try:
            assert s.get_jobs()[0].misfire_grace_time == 900
        finally:
            s.shutdown(wait=False)

    asyncio.run(scenario())


def test_no_per_job_misfire_override_in_scheduler_src() -> None:
    """全量声明纪律: add_job 调用不得再出现 per-job misfire_grace_time
    (统一走 job_defaults=900; per-job 值 <900 会重新打开 E4 缺口)。"""
    import ast
    from pathlib import Path

    src = Path(
        __import__("backend.scheduler.scheduler", fromlist=["__file__"]).__file__
    ).read_text(encoding="utf-8")
    offenders = [
        kw.arg
        for node in ast.walk(ast.parse(src)) if isinstance(node, ast.Call)
        for kw in node.keywords if kw.arg == "misfire_grace_time"
    ]
    assert offenders == [], f"scheduler.py 存在 per-job misfire 声明: {offenders}"


# ---------------------------------------------------------------------------
# run record 统一: ensure_instrumented / _ensure_run_records
# ---------------------------------------------------------------------------


async def _plain_job() -> None:
    return None


def test_ensure_instrumented_wraps_plain_func() -> None:
    wrapped = jobs_mod.ensure_instrumented(_plain_job, "sm2_daily_push")
    assert wrapped is not _plain_job
    assert getattr(wrapped, "_instrument_job_type", None) == "sm2_daily_push"


def test_ensure_instrumented_sync_job_awaitable(temp_db) -> None:
    """DEV-0287 (D1): 同步 def job 被包装后必须可 await 且返回值正确。

    回归根因: sync def 直接进 async wrapper → `await coro()` 对 dict 抛
    `'dict' object can't be awaited` — legacy 双 job + knowledge_review_due
    生产 failed 200+ 条 (每 30/60min 必炸)。
    """
    import asyncio

    def _sync_job() -> dict:
        return {"ok": 1}

    wrapped = jobs_mod.ensure_instrumented(_sync_job, "legacy_promote_due")
    assert asyncio.iscoroutinefunction(wrapped)
    result = asyncio.run(wrapped())
    assert result == {"ok": 1}


def test_ensure_instrumented_sync_job_exception_recorded(temp_db) -> None:
    """同步 job 抛错 → wrapper 正常落 job_runs failed (而非误报 awaited 错)。"""
    import asyncio

    def _boom() -> dict:
        raise ValueError("sync boom")

    wrapped = jobs_mod.ensure_instrumented(_boom, "legacy_migrate_resume")
    try:
        asyncio.run(wrapped())
        raised = False
    except ValueError as e:
        raised = True
        assert str(e) == "sync boom"
    assert raised
    row = get_connection().execute(
        "SELECT status, error FROM job_runs WHERE job_type='legacy_migrate_resume' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None and row[0] == "failed" and "sync boom" in row[1]


def test_ensure_instrumented_idempotent() -> None:
    """已插桩的 job 不双重包装 (双重包装 = 一次执行写两行 job_runs)。"""
    once = jobs_mod.ensure_instrumented(_plain_job, "collect_all")
    twice = jobs_mod.ensure_instrumented(once, "collect_all")
    assert once is twice


def test_module_decorated_jobs_pass_through() -> None:
    """模块级 @instrument_job 的 job (如 telemetry_window_job) 原样通过。"""
    out = jobs_mod.ensure_instrumented(jobs_mod.telemetry_window_job, "telemetry_window")
    assert out is jobs_mod.telemetry_window_job


def test_ensure_run_records_swaps_all_funcs() -> None:
    """scheduler 注册口统一补插桩: 未装饰 job 的 func 被换成带标记的 wrapper。"""
    s = HotspotScheduler()
    s.scheduler = create_scheduler()
    s.scheduler.add_job(_plain_job, trigger="interval", seconds=60, id="plain_job")
    s._ensure_run_records()
    (job,) = s.scheduler.get_jobs()
    assert getattr(job.func, "_instrument_job_type", None) == "plain_job"


# ---------------------------------------------------------------------------
# 丢弃 → 记录: EVENT_MISSED listener
# ---------------------------------------------------------------------------


class _FakeMissedEvent:
    """APScheduler JobExecutionEvent (EVENT_MISSED) 最小复刻。"""

    def __init__(self, job_id: str, scheduled_run_time: datetime):
        self.job_id = job_id
        self.scheduled_run_time = scheduled_run_time


def test_on_job_missed_records_job_run(temp_db) -> None:
    """E4 验收: 错过 grace 的 run 落 job_runs (status=missed), 不再静默丢弃。"""
    s = HotspotScheduler()
    scheduled = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
    s._on_job_missed(_FakeMissedEvent("sm2_daily_push", scheduled))

    row = get_connection().execute(
        "SELECT job_type, status, started_at, error FROM job_runs "
        "WHERE job_type = 'sm2_daily_push'"
    ).fetchone()
    assert row is not None, "misfire 事件未落 job_runs (E4 静默丢弃未修)"
    assert row["status"] == "missed"
    assert row["started_at"] == scheduled.isoformat()
    assert "misfire" in row["error"]


def test_record_missed_job_run_tolerates_db_error(temp_db, monkeypatch) -> None:
    """观测写入吞错契约: DB 不可用时返回 None, 不抛异常。"""
    from backend.observability_records import get_connection as _gc

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.observability_records.get_connection", _boom)
    assert record_missed_job_run("x", "x-1", "2026-10-02T00:00:00+00:00") is None
    del _gc


# ---------------------------------------------------------------------------
# /api/ops/runs
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client(temp_db):
    app = FastAPI()
    app.include_router(ops_router)
    with TestClient(app) as c:
        yield c


def _seed_runs() -> None:
    """造 4 类 run: failed / missed / ok / stale running (2h 前)。"""
    now = datetime.now(tz=timezone.utc)
    conn = get_connection()
    rows = [
        # (job_type, status, started_at 偏移分, error)
        ("collect_all", "failed", -10, "RuntimeError: proxy timeout"),
        ("sm2_daily_push", "missed", -20, "misfire: ..."),
        ("collect_all", "ok", -5, None),
        ("kl_trigger_t1", "running", -180, None),  # stale (>2h)
    ]
    for jt, st, off_min, err in rows:
        conn.execute(
            "INSERT INTO job_runs (job_id, job_type, trace_id, started_at, "
            "status, duration_ms, error) VALUES (?, ?, NULL, ?, ?, ?, ?)",
            (f"{jt}-{off_min}", jt,
             (now + timedelta(minutes=off_min)).isoformat(), st,
             1000 if st == "ok" else None, err),
        )


def test_runs_failure_first_with_summary(api_client: TestClient) -> None:
    """默认失败优先: failed → missed 排前, summary 含四态计数 + stale_running。"""
    _seed_runs()
    r = api_client.get("/api/ops/runs")
    assert r.status_code == 200
    body = r.json()
    types = [x["job_type"] for x in body["runs"]]
    # failed 最先, missed 次之 (窗口内只有这两类被默认过滤)
    assert types[0] == "collect_all" and body["runs"][0]["status"] == "failed"
    assert types[1] == "sm2_daily_push" and body["runs"][1]["status"] == "missed"
    assert len(body["runs"]) == 2
    assert body["summary"] == {
        "ok": 1, "failed": 1, "missed": 1, "running": 1, "stale_running": 1,
    }


def test_runs_all_filter_and_job_type(api_client: TestClient) -> None:
    """status=all + job_type 精确过滤。"""
    _seed_runs()
    r = api_client.get("/api/ops/runs", params={"status": "all", "job_type": "collect_all"})
    body = r.json()
    assert all(x["job_type"] == "collect_all" for x in body["runs"])
    assert {x["status"] for x in body["runs"]} == {"failed", "ok"}


def test_runs_invalid_status_400(api_client: TestClient) -> None:
    assert api_client.get("/api/ops/runs", params={"status": "bogus"}).status_code == 400


def test_runs_empty_window(api_client: TestClient) -> None:
    """无记录窗口: 空列表 + 零 summary (面板空态)。"""
    r = api_client.get("/api/ops/runs")
    assert r.status_code == 200
    assert r.json()["runs"] == []
    assert r.json()["summary"]["failed"] == 0
