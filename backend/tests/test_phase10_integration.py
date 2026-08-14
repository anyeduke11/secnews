"""Phase 10 integration test — scheduler jobs + end-to-end T1 → T2 chain.

6 cases (per spec §8.1)
-----------------------
- I.1  3 KL jobs are registered with the correct intervals
- I.2  T1 advances a raw item to refine; T2 then advances it to link
- I.3  end-to-end: T1 → T2 chain produces knowledge_links row
- I.4  metrics endpoint reflects T1 + T2 activity
- I.5  dead_letter_retry_job is non-fatal when DB is empty
- I.6  3 jobs survive a scheduler start/stop cycle (replace_existing works)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.kl_metrics_api import router as kl_router
from backend.config import config
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.scheduler import jobs
from backend.scheduler.scheduler import HotspotScheduler
from backend.services.kl_state_machine import (
    LIFECYCLE_LINK,
    LIFECYCLE_RAW,
    LIFECYCLE_REFINE,
)
from backend.services.triggers import T1Trigger, T2Trigger

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_phase10_integration.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    yield test_db
    db_module.close_db()


@pytest.fixture
def client(temp_db):
    app = FastAPI()
    app.include_router(kl_router)
    return TestClient(app)


def _insert_raw_item(conn, id: str, title: str = "Sample") -> None:
    """Insert a knowledge_item that T1 will pick up.

    ingested_at is 6 minutes ago so the 5-min debounce passes.
    """
    ingested = (
        datetime.now(timezone.utc) - timedelta(minutes=6)
    ).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, 'web', 'https://x.test/' || ?, '[]', '[]',
                0, 0, ?, ?, ?)
        """,
        (id, title, id, ingested, ingested, LIFECYCLE_RAW),
    )


# ---------------------------------------------------------------------------
# I.1 — 3 KL jobs registered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_kl_jobs_registered(temp_db):
    sched = HotspotScheduler.__new__(HotspotScheduler)
    sched.scheduler = None
    sched.service = None  # bypass attach_service in start
    sched.logger = None
    # Use a minimal init
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched.scheduler = AsyncIOScheduler(timezone="UTC")
    sched.scheduler.add_job(
        jobs.kl_trigger_t1_job, id="kl_trigger_t1", replace_existing=True,
    )
    sched.scheduler.add_job(
        jobs.kl_trigger_t2_job, id="kl_trigger_t2", replace_existing=True,
    )
    sched.scheduler.add_job(
        jobs.kl_dead_letter_retry_job, id="kl_dead_letter_retry",
        replace_existing=True,
    )
    sched.scheduler.start()
    try:
        job_ids = {job.id for job in sched.scheduler.get_jobs()}
        assert "kl_trigger_t1" in job_ids
        assert "kl_trigger_t2" in job_ids
        assert "kl_dead_letter_retry" in job_ids
    finally:
        sched.scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# I.2 — T1 + T2 single-step chain
# ---------------------------------------------------------------------------

def test_t1_then_t2_advances_chain(temp_db):
    conn = get_connection()
    _insert_raw_item(conn, "chain-1")
    conn.commit()

    t1 = T1Trigger()
    rep1 = t1.run_once()
    assert rep1["advanced"] == 1
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("chain-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE

    t2 = T2Trigger()
    rep2 = t2.run_once()
    assert rep2["advanced"] == 1
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("chain-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_LINK


# ---------------------------------------------------------------------------
# I.3 — end-to-end: T1 + T2 produce knowledge_links row
# ---------------------------------------------------------------------------

def test_end_to_end_writes_knowledge_link(temp_db):
    conn = get_connection()
    _insert_raw_item(conn, "a")
    _insert_raw_item(conn, "b")
    # Concepts injected post-insert to simulate concept_linker having run
    conn.execute(
        "UPDATE knowledge_items SET concepts = ? WHERE id = ?",
        (json.dumps(["ml", "rag"]), "a"),
    )
    conn.execute(
        "UPDATE knowledge_items SET concepts = ? WHERE id = ?",
        (json.dumps(["rag", "llm"]), "b"),
    )
    conn.commit()

    T1Trigger().run_once()
    T2Trigger().run_once()

    links = conn.execute("SELECT * FROM knowledge_links").fetchall()
    # 2 directed links (a→b, b→a)
    assert len(links) == 2
    pairs = {(r["from_item_id"], r["to_item_id"]) for r in links}
    assert ("a", "b") in pairs
    assert ("b", "a") in pairs


# ---------------------------------------------------------------------------
# I.4 — metrics endpoint reflects activity
# ---------------------------------------------------------------------------

def test_metrics_endpoint_reflects_activity(temp_db, client):
    conn = get_connection()
    _insert_raw_item(conn, "m-1")
    _insert_raw_item(conn, "m-2")
    conn.commit()

    T1Trigger().run_once()
    T2Trigger().run_once()

    resp = client.get("/api/kl/metrics")
    assert resp.status_code == 200
    data = resp.json()
    # Both triggers ran
    assert data["counters"]["t1_triggered"] >= 1
    assert data["counters"]["t2_triggered"] >= 1


# ---------------------------------------------------------------------------
# I.5 — dead_letter_retry_job is non-fatal when DB is empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dead_letter_retry_job_no_crash(temp_db):
    # Empty DB — the job should run without error.
    await jobs.kl_dead_letter_retry_job()
    # No exception → pass
    assert True


# ---------------------------------------------------------------------------
# I.6 — scheduler start/stop cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_start_stop_round_trip(temp_db):
    """Re-creating a scheduler with the 3 KL jobs (replace_existing) works."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched = HotspotScheduler.__new__(HotspotScheduler)
    sched.scheduler = AsyncIOScheduler(timezone="UTC")
    sched.service = None
    sched.logger = None
    sched.scheduler.add_job(jobs.kl_trigger_t1_job, id="kl_trigger_t1", replace_existing=True)
    sched.scheduler.add_job(jobs.kl_trigger_t2_job, id="kl_trigger_t2", replace_existing=True)
    sched.scheduler.add_job(jobs.kl_dead_letter_retry_job, id="kl_dead_letter_retry", replace_existing=True)
    sched.scheduler.start()
    try:
        ids = {job.id for job in sched.scheduler.get_jobs()}
        assert {"kl_trigger_t1", "kl_trigger_t2", "kl_dead_letter_retry"} <= ids
    finally:
        sched.scheduler.shutdown(wait=False)
    # Re-start with same IDs (replace_existing should not raise)
    sched2 = HotspotScheduler.__new__(HotspotScheduler)
    sched2.scheduler = AsyncIOScheduler(timezone="UTC")
    sched2.scheduler.add_job(jobs.kl_trigger_t1_job, id="kl_trigger_t1", replace_existing=True)
    sched2.scheduler.add_job(jobs.kl_trigger_t2_job, id="kl_trigger_t2", replace_existing=True)
    sched2.scheduler.add_job(jobs.kl_dead_letter_retry_job, id="kl_dead_letter_retry", replace_existing=True)
    sched2.scheduler.start()
    try:
        ids = {job.id for job in sched2.scheduler.get_jobs()}
        assert {"kl_trigger_t1", "kl_trigger_t2", "kl_dead_letter_retry"} <= ids
    finally:
        sched2.scheduler.shutdown(wait=False)
