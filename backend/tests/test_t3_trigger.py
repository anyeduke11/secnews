"""Tests for :class:`backend.services.triggers.T3Trigger`.

Phase 12 — covers the ``kl:link`` → ``kl:structure`` trigger.

10 cases
--------
- T3.1  No candidates → returns zeros, no DB writes
- T3.2  Single ``kl:link`` item → candidates returned
- T3.3  Items with ≥3 links → advanced (low_link=0)
- T3.4  Items with <3 links → also advanced (low_link=1)
- T3.5  Summary extracted from content first 200 chars
- T3.6  Lifecycle updated to ``kl:structure``
- T3.7  Failure: exception → dead letter queue
- T3.8  ``_count_links`` query returns correct count
- T3.9  Metrics: t3_triggered / t3_succeeded / t3_failed
- T3.10 Empty content yields empty summary
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.config import config
from backend.metrics.kl_metrics import (
    COUNTER_KEYS,
    HISTOGRAM_KEYS,
    kl_metrics,
)
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LIFECYCLE_LINK,
    LIFECYCLE_STRUCTURE,
)
from backend.services.retry_policy import RetryPolicy
from backend.services.triggers import T3Trigger
from backend.services.triggers.t3_link_to_structure import (
    BATCH_SIZE,
    LOW_LINK_THRESHOLD,
    TRIGGER_NAME,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_t3_trigger.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    # The T3 trigger SELECTs content from knowledge_items, but the column
    # is not part of the current migration set. Add it here for test isolation.
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE knowledge_items ADD COLUMN content TEXT DEFAULT ''")
    except Exception:
        pass
    yield test_db
    db_module.close_db()


@pytest.fixture
def fresh_metrics():
    """Reset the shared metrics singleton between tests.

    Resets counters, histograms, and the stage gauge so each test
    starts from a clean slate.
    """
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})
    yield kl_metrics
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})


def _insert_knowledge_item(
    conn,
    id: str,
    lifecycle: str = LIFECYCLE_LINK,
    ingested_seconds_ago: int = 600,
    title: str = "Sample Article",
    source_url: str = "https://example.com/sample",
    concepts: str = "[]",
    tags: str = "[]",
    content: str = "",
) -> None:
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(seconds=ingested_seconds_ago)).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle, content)
        VALUES (?, ?, 'web', ?, ?, ?, 0, 0, ?, ?, ?, ?)
        """,
        (id, title, source_url, concepts, tags, ingested, ingested, lifecycle, content),
    )


def _insert_knowledge_link(conn, from_item_id: str, to_item_id: str, link_type: str = "similar") -> None:
    """Insert a row into ``knowledge_links``.

    Uses INSERT OR IGNORE to avoid collisions on the
    (from_item_id, to_item_id, link_type) UNIQUE constraint.
    """
    conn.execute(
        "INSERT OR IGNORE INTO knowledge_links "
        "(from_item_id, to_item_id, link_type, confidence, created_by) "
        "VALUES (?, ?, ?, 0.5, 'agent')",
        (from_item_id, to_item_id, link_type),
    )


def _trigger(fresh_metrics, retry_policy=None) -> T3Trigger:
    return T3Trigger(
        metrics=fresh_metrics,
        retry_policy=retry_policy or RetryPolicy(metrics=fresh_metrics),
    )


# ---------------------------------------------------------------------------
# T3.1 — no candidates
# ---------------------------------------------------------------------------

def test_t3_no_candidates(temp_db, fresh_metrics):
    """No ``kl:link`` items → report is all zeros, no DB writes."""
    t3 = _trigger(fresh_metrics)
    report = t3.run_once()
    assert report == {
        "candidates": 0,
        "advanced": 0,
        "low_link": 0,
        "failed": 0,
    }
    # triggered counter ticks
    assert fresh_metrics.counter_value("t3_triggered") == 1
    # latency histogram has 1 sample
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t3_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T3.2 — returns candidates
# ---------------------------------------------------------------------------

def test_t3_returns_candidates(temp_db, fresh_metrics):
    """Query lifecycle='kl:link' items returns candidates."""
    conn = get_connection()
    _insert_knowledge_item(conn, "link-item-1", lifecycle=LIFECYCLE_LINK)
    # Non-link item should NOT be picked up
    _insert_knowledge_item(conn, "raw-item", lifecycle="kl:raw")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    report = t3.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["failed"] == 0


# ---------------------------------------------------------------------------
# T3.3 — high-link items (≥3 links) advance
# ---------------------------------------------------------------------------

def test_t3_advances_high_link_items(temp_db, fresh_metrics):
    """Items with ≥3 links advance normally; low_link=0."""
    conn = get_connection()
    _insert_knowledge_item(conn, "high-link-item")
    # Insert exactly 3 links (≥ LOW_LINK_THRESHOLD)
    for i in range(3):
        _insert_knowledge_link(conn, "high-link-item", f"target-{i}")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    report = t3.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["low_link"] == 0  # 3 links ≥ threshold → not low_link
    assert report["failed"] == 0


# ---------------------------------------------------------------------------
# T3.4 — low-link items (<3 links) also advance
# ---------------------------------------------------------------------------

def test_t3_low_link_also_advances(temp_db, fresh_metrics):
    """Items with <3 links advance but are marked low_link=1."""
    conn = get_connection()
    _insert_knowledge_item(conn, "low-link-item")
    # Insert only 1 link (< LOW_LINK_THRESHOLD)
    _insert_knowledge_link(conn, "low-link-item", "target-1")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    report = t3.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["low_link"] == 1  # 1 link < 3 → marked low_link
    assert report["failed"] == 0


# ---------------------------------------------------------------------------
# T3.5 — summary from content
# ---------------------------------------------------------------------------

def test_t3_generates_summary(temp_db, fresh_metrics):
    """Summary is extracted from the first 200 characters of content."""
    conn = get_connection()
    content = "A" * 500
    _insert_knowledge_item(conn, "summary-item", content=content)
    conn.commit()

    t3 = _trigger(fresh_metrics)
    report = t3.run_once()

    assert report["advanced"] == 1
    # Directly test the static helper
    assert t3._generate_summary({"content": content}) == content[:200]
    assert len(t3._generate_summary({"content": content})) == 200


# ---------------------------------------------------------------------------
# T3.6 — lifecycle update
# ---------------------------------------------------------------------------

def test_t3_updates_lifecycle(temp_db, fresh_metrics):
    """Lifecycle is updated to kl:structure after processing."""
    conn = get_connection()
    _insert_knowledge_item(conn, "lifecycle-item")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    t3.run_once()

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("lifecycle-item",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_STRUCTURE


# ---------------------------------------------------------------------------
# T3.7 — failure path: dead letter queue
# ---------------------------------------------------------------------------

def test_t3_failure_handling(temp_db, fresh_metrics):
    """Exception during processing → t3_failed++ and dead letter written."""
    conn = get_connection()
    _insert_knowledge_item(conn, "boom")
    conn.commit()

    class _BoomError(RuntimeError):
        pass

    # Force the lifecycle update to raise by patching the method.
    t3 = _trigger(fresh_metrics)
    original_update = t3._update_lifecycle

    def _raise(_item_id, _new_stage):
        raise _BoomError("simulated")

    t3._update_lifecycle = _raise  # type: ignore[assignment]

    try:
        report = t3.run_once()
    finally:
        t3._update_lifecycle = original_update  # type: ignore[assignment]

    assert report["failed"] == 1
    assert report["advanced"] == 0
    assert fresh_metrics.counter_value("t3_failed") == 1
    # Retry policy was invoked → a kl_dead_letters row exists
    rows = conn.execute(
        "SELECT trigger_name, item_id, attempts FROM kl_dead_letters"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["trigger_name"] == TRIGGER_NAME
    assert rows[0]["item_id"] == "boom"
    assert rows[0]["attempts"] == 1


# ---------------------------------------------------------------------------
# T3.8 — link count query
# ---------------------------------------------------------------------------

def test_t3_link_count_query(temp_db, fresh_metrics):
    """_count_links returns correct count from knowledge_links."""
    conn = get_connection()
    _insert_knowledge_item(conn, "source-item")
    # Insert 5 links
    for i in range(5):
        _insert_knowledge_link(conn, "source-item", f"target-{i}")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    count = t3._count_links("source-item")
    assert count == 5

    # Non-existent item returns 0
    assert t3._count_links("nonexistent") == 0


# ---------------------------------------------------------------------------
# T3.9 — metrics counters
# ---------------------------------------------------------------------------

def test_t3_metrics_incremented(temp_db, fresh_metrics):
    """Verify t3_triggered, t3_succeeded, t3_failed are correct."""
    conn = get_connection()
    _insert_knowledge_item(conn, "m1")
    _insert_knowledge_item(conn, "m2")
    conn.commit()

    t3 = _trigger(fresh_metrics)
    t3.run_once()

    assert fresh_metrics.counter_value("t3_triggered") == 1
    assert fresh_metrics.counter_value("t3_succeeded") == 2
    assert fresh_metrics.counter_value("t3_failed") == 0
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t3_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T3.10 — empty content
# ---------------------------------------------------------------------------

def test_t3_empty_content(temp_db, fresh_metrics):
    """Empty / None content yields an empty summary string."""
    t3 = _trigger(fresh_metrics)
    assert t3._generate_summary({"content": ""}) == ""
    assert t3._generate_summary({"content": None}) == ""
    assert t3._generate_summary({"no_content_key": "blah"}) == ""


# ---------------------------------------------------------------------------
# T3.11 — LLM summarization calls service
# ---------------------------------------------------------------------------

def test_summarize_with_llm_calls_service(temp_db, fresh_metrics, monkeypatch):
    """When llm_service.summarize() returns a non-empty string, it is used."""
    async def _mock_summarize(chunks):
        return "LLM-generated summary of the article"

    monkeypatch.setattr(
        "backend.services.triggers.t3_link_to_structure.llm_service.summarize",
        _mock_summarize,
    )

    t3 = _trigger(fresh_metrics)
    result = t3._summarize_with_llm({"content": "A" * 500})
    assert result == "LLM-generated summary of the article"


# ---------------------------------------------------------------------------
# T3.12 — LLM summarization fallback
# ---------------------------------------------------------------------------

def test_summarize_with_llm_fallback(temp_db, fresh_metrics, monkeypatch):
    """When llm_service.summarize() raises an exception, fallback to truncation."""
    async def _mock_summarize(chunks):
        raise RuntimeError("LLM service unavailable")

    monkeypatch.setattr(
        "backend.services.triggers.t3_link_to_structure.llm_service.summarize",
        _mock_summarize,
    )

    t3 = _trigger(fresh_metrics)
    content = "B" * 500
    result = t3._summarize_with_llm({"content": content})
    assert result == content[:200]
    assert len(result) == 200


# ---------------------------------------------------------------------------
# T3.13 — empty content skips LLM
# ---------------------------------------------------------------------------

def test_summarize_with_llm_empty_content(temp_db, fresh_metrics, monkeypatch):
    """When content is empty, LLM is not called and empty string is returned."""
    calls: list = []

    async def _mock_summarize(chunks):
        calls.append(1)
        return "should not be called"

    monkeypatch.setattr(
        "backend.services.triggers.t3_link_to_structure.llm_service.summarize",
        _mock_summarize,
    )

    t3 = _trigger(fresh_metrics)
    result = t3._summarize_with_llm({"content": ""})
    assert result == ""
    assert len(calls) == 0  # LLM was never called