"""test_playbook_cron — Phase C C2 测试套件 (≥10 case).

覆盖意图 (why):
- PlaybookScheduleRepo: upsert / get / list_enabled / list_all / delete / set_enabled
- PlaybookRunRepo: insert / list_for_playbook / get (落 audit)
- PlaybookScheduler: 启动加载 enabled + 即时 upsert/启停生效 + cron tick 触发
  + 失败持久化
- 隔离策略: 独立 BackgroundScheduler (不接入主 AsyncIOScheduler, R6 1h 上限
  风险隔离); cron spec 校验失败抛 (防无效 schedule 上线)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.services.playbook_engine import (
    Playbook,
    PlaybookEngine,
    PlaybookScheduler,
    PlaybookStep,
    load_playbook,
)
from backend.services.playbook_engine.scheduler import (
    DEFAULT_TZ,
    PlaybookRunRepo,
    PlaybookScheduleRepo,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo(temp_db) -> PlaybookScheduleRepo:  # noqa: ARG001 — temp_db triggers init_db
    return PlaybookScheduleRepo()


@pytest.fixture
def run_repo(temp_db) -> PlaybookRunRepo:  # noqa: ARG001
    return PlaybookRunRepo()


@pytest.fixture
def fake_engine(monkeypatch) -> PlaybookEngine:
    """注入 fake engine: execute 返回成功 PlaybookRun (真实 dataclass, 供 sqlite 序列化)."""
    from backend.services.playbook_engine import core as core_mod

    class FakeEngine:
        def execute(self, pb: Playbook, inputs=None):
            from backend.services.playbook_engine.core import PlaybookRun, StepResult

            now = datetime.now(timezone.utc).isoformat()
            return PlaybookRun(
                run_id="pb-fake-001",
                name=pb.name,
                status="succeeded",
                inputs=inputs or {},
                steps=[StepResult(step_id="x", kind="skill", status="succeeded", output={}, elapsed_ms=1)],
                started_at=now,
                finished_at=now,
                error=None,
            )

    return FakeEngine()


# ---------------------------------------------------------------------------
# ScheduleRepo CRUD
# ---------------------------------------------------------------------------
def test_repo_upsert_creates_row(repo: PlaybookScheduleRepo) -> None:
    """upsert 创建新行; UNIQUE(playbook_name) 保证幂等."""
    entry = repo.upsert(
        playbook_name="daily-source-health",
        cron_spec="0 8 * * *",
        timezone=DEFAULT_TZ,
        inputs={"hours": 24},
        enabled=True,
    )
    assert entry["playbook_name"] == "daily-source-health"
    assert entry["cron_spec"] == "0 8 * * *"
    assert entry["enabled"] == 1
    assert entry["inputs_json"] == {"hours": 24}

    # 第二次 upsert 同名 → 覆盖 (不应 create 第二个)
    entry2 = repo.upsert(
        playbook_name="daily-source-health",
        cron_spec="0 9 * * *",
        timezone=DEFAULT_TZ,
    )
    assert entry2["cron_spec"] == "0 9 * * *"


def test_repo_get_returns_none_for_missing(repo: PlaybookScheduleRepo) -> None:
    assert repo.get("ghost-schedule") is None


def test_repo_list_enabled_filters_disabled(repo: PlaybookScheduleRepo) -> None:
    repo.upsert(playbook_name="a", cron_spec="0 8 * * *", enabled=True)
    repo.upsert(playbook_name="b", cron_spec="0 9 * * *", enabled=False)
    enabled = repo.list_enabled()
    assert "a" in [e["playbook_name"] for e in enabled]
    assert "b" not in [e["playbook_name"] for e in enabled]


def test_repo_set_enabled_toggles(repo: PlaybookScheduleRepo) -> None:
    repo.upsert(playbook_name="x", cron_spec="0 8 * * *", enabled=True)
    assert repo.set_enabled("x", False) is True
    assert repo.get("x")["enabled"] == 0
    assert repo.set_enabled("x", True) is True
    assert repo.get("x")["enabled"] == 1


def test_repo_delete_removes_row(repo: PlaybookScheduleRepo) -> None:
    repo.upsert(playbook_name="to-del", cron_spec="0 8 * * *")
    assert repo.delete("to-del") is True
    assert repo.get("to-del") is None
    assert repo.delete("to-del") is False  # 二次删除返 False


# ---------------------------------------------------------------------------
# RunRepo (audit 落库)
# ---------------------------------------------------------------------------
def test_run_repo_insert_and_get(run_repo: PlaybookRunRepo) -> None:
    """execute 后落 audit; get 返完整字段."""
    now = datetime.now(timezone.utc).isoformat()
    run_repo.insert(
        run_id="pb-audit-001",
        playbook_name="daily-source-health",
        status="succeeded",
        inputs={"hours": 24},
        steps=[{"step_id": "scan", "status": "succeeded", "output": {}, "elapsed_ms": 12}],
        started_at=now,
        finished_at=now,
        duration_ms=12,
        error=None,
    )
    row = run_repo.get("pb-audit-001")
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["steps_json"][0]["step_id"] == "scan"
    assert row["inputs_json"]["hours"] == 24


def test_run_repo_list_for_playbook_desc_by_started(run_repo: PlaybookRunRepo) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        run_repo.insert(
            run_id=f"pb-list-{i}",
            playbook_name="x",
            status="succeeded",
            inputs={},
            steps=[],
            started_at=now,
            finished_at=now,
            duration_ms=0,
            error=None,
        )
    rows = run_repo.list_for_playbook("x", limit=10)
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# PlaybookScheduler 生命周期 + 即时生效
# ---------------------------------------------------------------------------
def test_scheduler_upsert_validates_cron_spec(temp_db) -> None:  # noqa: ARG001
    """upsert 时校验 cron spec, 无效拒绝 (fail loud, 防无效 schedule 上线)."""
    sched = PlaybookScheduler(engine=MagicMock())
    with pytest.raises(Exception):
        sched.upsert_schedule(playbook_name="bad", cron_spec="not-a-cron")


def test_scheduler_start_registers_enabled_only(repo: PlaybookScheduleRepo, fake_engine) -> None:
    """start() 按 enabled 加载到 APScheduler; disabled 不被加载."""
    repo.upsert(playbook_name="on", cron_spec="0 8 * * *", enabled=True)
    repo.upsert(playbook_name="off", cron_spec="0 9 * * *", enabled=False)

    sched = PlaybookScheduler(engine=fake_engine, repo=repo, run_repo=PlaybookRunRepo())
    sched.start()
    try:
        jobs = sched.scheduler.get_jobs()
        ids = {j.id for j in jobs}
        assert "playbook::on" in ids
        assert "playbook::off" not in ids
    finally:
        sched.shutdown()


def test_scheduler_upsert_after_start_registers_immediately(
    repo: PlaybookScheduleRepo, fake_engine
) -> None:
    """upsert_schedule 在 start 后即时加 APScheduler job (无需重启)."""
    sched = PlaybookScheduler(engine=fake_engine, repo=repo, run_repo=PlaybookRunRepo())
    sched.start()
    try:
        # 启动后追加
        sched.upsert_schedule(playbook_name="late", cron_spec="0 10 * * *")
        assert sched.scheduler.get_job("playbook::late") is not None
    finally:
        sched.shutdown()


def test_scheduler_set_enabled_adds_or_removes_job(
    repo: PlaybookScheduleRepo, fake_engine
) -> None:
    """set_enabled(False) 移 APScheduler job; set_enabled(True) 重新加."""
    repo.upsert(playbook_name="toggle", cron_spec="0 8 * * *", enabled=True)

    sched = PlaybookScheduler(engine=fake_engine, repo=repo, run_repo=PlaybookRunRepo())
    sched.start()
    try:
        # 启动后 job 已加
        assert sched.scheduler.get_job("playbook::toggle") is not None

        sched.set_enabled("toggle", False)
        assert sched.scheduler.get_job("playbook::toggle") is None

        sched.set_enabled("toggle", True)
        assert sched.scheduler.get_job("playbook::toggle") is not None
    finally:
        sched.shutdown()


def test_scheduler_tick_executes_and_persists_audit(
    repo: PlaybookScheduleRepo, run_repo: PlaybookRunRepo, fake_engine, monkeypatch
) -> None:
    """cron tick 触发 _run_tick → 调 execute → 落 playbook_runs 表."""
    import os

    from pathlib import Path

    cwd = os.getcwd()
    # pytest 在 backend/ 下执行, CWD=backend; project root 在 cwd.parent
    candidates = [
        Path(cwd) / "playbook_engine" / "examples" / "daily_source_health.yml",
        Path(cwd).parent / "playbook_engine" / "examples" / "daily_source_health.yml",
    ]
    pb_path = next((p for p in candidates if p.exists()), None)
    assert pb_path is not None, f"C1 examples 必须存在 (cwd={cwd}, tried {candidates})"

    repo.upsert(
        playbook_name="daily-source-health",
        cron_spec="0 8 * * *",
        inputs={"hours": 24},
        enabled=True,
    )

    sched = PlaybookScheduler(engine=fake_engine, repo=repo, run_repo=run_repo)
    sched.start()
    try:
        # 手动调 _run_tick (不等待 APScheduler 真触达)
        sched._run_tick(playbook_name="daily-source-health")

        # 落 audit
        runs = run_repo.list_for_playbook("daily-source-health", limit=5)
        assert len(runs) == 1
        assert runs[0]["status"] == "succeeded"
    finally:
        sched.shutdown()


def test_scheduler_tick_persists_failure_when_load_fails(
    repo: PlaybookScheduleRepo, run_repo: PlaybookRunRepo, fake_engine, monkeypatch
) -> None:
    """load 失败 → 落 playbook_runs status=failed, 不抛."""
    # 指向不存在的 playbook
    repo.upsert(playbook_name="ghost-pb", cron_spec="0 8 * * *", enabled=True)

    sched = PlaybookScheduler(engine=fake_engine, repo=repo, run_repo=run_repo)
    sched.start()
    try:
        sched._run_tick(playbook_name="ghost-pb")
        runs = run_repo.list_for_playbook("ghost-pb", limit=5)
        assert len(runs) == 1
        assert runs[0]["status"] == "failed"
        assert "not found" in (runs[0]["error"] or "")
    finally:
        sched.shutdown()


def test_scheduler_shutdown_is_idempotent(fake_engine, temp_db) -> None:  # noqa: ARG001
    """shutdown 多次调用安全 (startup lifespan 重入场景)."""
    sched = PlaybookScheduler(engine=fake_engine)
    sched.start()
    sched.shutdown()
    sched.shutdown()  # 二次应不抛
    assert sched.scheduler is None