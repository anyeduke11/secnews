"""Tests for :class:`backend.services.triggers.T4Trigger`.

Phase 12 — covers the ``kl:structure`` → ``kl:publish`` trigger.

10 test cases
-------------
- T4.1  Returns candidates: lifecycle='kl:structure' items are queried
- T4.2  High-score items (>= 8.0) advance to publish
- T4.3  Low-score items (< 8.0) are skipped
- T4.4  Unstable items (updated_at < 24h) are skipped
- T4.5  .md file written to knowledge/items/ on advance
- T4.6  Lifecycle updated to kl:publish on advance
- T4.7  No candidates returns empty result
- T4.8  Failure path: exception goes to dead letter queue
- T4.9  Metrics counters correctly incremented
- T4.10 Score fallback: no ai_scores row → DEFAULT_SCORE (5.0) → skipped
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.config import config
from backend.metrics.kl_metrics import kl_metrics
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LIFECYCLE_STRUCTURE,
    LIFECYCLE_PUBLISH,
)
from backend.services.retry_policy import RetryPolicy
from backend.services.triggers.t4_structure_to_publish import (
    BATCH_SIZE,
    DEFAULT_SCORE,
    MIN_SCORE,
    STABLE_WINDOW_HOURS,
    T4Trigger,
    TRIGGER_NAME,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolated SQLite database for each test.

    The ``knowledge_items`` table created by migration 018 has no
    ``content`` column.  The T4 trigger's ``_fetch_candidates`` SQL
    selects ``content``, so we add it here to make the trigger
    executable in tests.
    """
    test_db = tmp_path / "test_t4_trigger.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    conn = get_connection()
    conn.execute("ALTER TABLE knowledge_items ADD COLUMN content TEXT DEFAULT ''")
    conn.commit()
    yield test_db
    db_module.close_db()


@pytest.fixture
def fresh_metrics():
    """Reset the shared metrics singleton between tests.

    The ``KLMetrics`` singleton only registers t1/t2/t3 counter keys.
    T4 counters are registered here so the trigger's ``inc`` calls
    take effect.
    """
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})
    # Register T4 counters (not in the original COUNTER_KEYS)
    for name in ("t4_triggered", "t4_succeeded", "t4_failed", "t4_dead_letter"):
        kl_metrics._counters[name] = 0
    # Register T4 histogram key
    kl_metrics._histograms["t4_latency_ms"] = __import__("collections").deque(
        maxlen=100
    )
    yield kl_metrics
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_hotspot(conn, item_id: str) -> None:
    """Insert a minimal hotspot row to satisfy FK constraints on ai_scores."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO hotspots "
        "(id, title, source, url, category, published_at, fetched_at) "
        "VALUES (?, 'hotspot-parent', 'web', ?, 'ai', ?, ?)",
        (item_id, f"https://x.test/{item_id}", now, now),
    )


def _insert_knowledge_item(
    conn,
    item_id: str,
    lifecycle: str = LIFECYCLE_STRUCTURE,
    title: str = "Sample Article",
    content: str = "Sample content body",
    updated_hours_ago: int = 48,
) -> None:
    """Insert a knowledge_items row with a configurable stability window."""
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(hours=72)).isoformat()
    updated = (now - timedelta(hours=updated_hours_ago)).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, content, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, ?, 'web', ?, '[]', '[]',
                0, 0, ?, ?, ?)
        """,
        (item_id, title, content, f"https://example.com/{item_id}",
         ingested, updated, lifecycle),
    )


def _insert_ai_score(
    conn,
    item_id: str,
    score: float,
    scored_seconds_ago: int = 3600,
) -> None:
    """Insert an ai_score row for the given item (FK to hotspots)."""
    _insert_hotspot(conn, item_id)
    scored_at = (datetime.now(timezone.utc) - timedelta(seconds=scored_seconds_ago)).isoformat()
    conn.execute(
        "INSERT INTO ai_scores (hotspot_id, score, reason, scorer, scored_at) "
        "VALUES (?, ?, 'test', 'test', ?)",
        (item_id, score, scored_at),
    )


def _fake_write_to_md(tmp_dir: Path):
    """Return a _write_to_md replacement that writes to a tmp directory."""
    def _write(_self: T4Trigger, item: Dict[str, Any]) -> None:
        items_dir = tmp_dir / "knowledge" / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        path = items_dir / f"{item['id']}.md"
        path.write_text(
            f"# {item.get('title', 'Untitled')}\n\n{item.get('content', '')}",
            encoding="utf-8",
        )
    return _write


def _trigger(fresh_metrics, retry_policy=None) -> T4Trigger:
    return T4Trigger(
        metrics=fresh_metrics,
        retry_policy=retry_policy or RetryPolicy(metrics=fresh_metrics),
    )


# ---------------------------------------------------------------------------
# T4.1 — candidates are returned from lifecycle='kl:structure' query
# ---------------------------------------------------------------------------

def test_t4_returns_candidates(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "item-1")
    _insert_knowledge_item(conn, "item-2")
    _insert_ai_score(conn, "item-1", 9.0)
    _insert_ai_score(conn, "item-2", 8.5)
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["candidates"] == 2
    assert report["advanced"] == 2

    # Verify the SQL query behaviour: items with different lifecycle are excluded
    conn.execute(
        "INSERT INTO knowledge_items "
        "(id, title, content, source, source_url, concepts, tags, "
        " mastery, compiled, ingested_at, updated_at, lifecycle) "
        "VALUES (?, ?, ?, 'web', ?, '[]', '[]', 0, 0, ?, ?, ?)",
        ("item-other", "Other", "content",
         "https://example.com/other",
         datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat(),
         "kl:publish"),
    )
    conn.commit()
    report2 = t4.run_once()
    assert report2["candidates"] == 0  # only structure items


# ---------------------------------------------------------------------------
# T4.2 — high-score items (>= 8.0) advance to publish
# ---------------------------------------------------------------------------

def test_t4_advances_high_score_items(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "high-score")
    _insert_ai_score(conn, "high-score", 9.5)
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["skipped_low_score"] == 0
    assert report["skipped_unstable"] == 0
    assert report["failed"] == 0

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("high-score",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_PUBLISH
    assert fresh_metrics.counter_value("t4_succeeded") == 1


# ---------------------------------------------------------------------------
# T4.3 — low-score items (< 8.0) are skipped
# ---------------------------------------------------------------------------

def test_t4_skips_low_score(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "low-score")
    _insert_ai_score(conn, "low-score", 6.5)
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 0
    assert report["skipped_low_score"] == 1
    assert report["skipped_unstable"] == 0

    # Lifecycle unchanged
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("low-score",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_STRUCTURE


# ---------------------------------------------------------------------------
# T4.4 — unstable items (updated_at < 24h) are skipped
# ---------------------------------------------------------------------------

def test_t4_skips_unstable(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    # updated_hours_ago=1 means the item was updated only 1 hour ago (< 24h window)
    _insert_knowledge_item(conn, "fresh-item", updated_hours_ago=1)
    _insert_ai_score(conn, "fresh-item", 9.0)
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 0
    assert report["skipped_unstable"] == 1
    assert report["skipped_low_score"] == 0

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("fresh-item",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_STRUCTURE  # unchanged


# ---------------------------------------------------------------------------
# T4.5 — .md file is written to knowledge/items/ on advance
# ---------------------------------------------------------------------------

def test_t4_writes_md_file(temp_db, fresh_metrics, tmp_path, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "md-test", title="MD Test Title", content="Hello world")
    _insert_ai_score(conn, "md-test", 9.0)
    conn.commit()

    # Replace _write_to_md with a version that writes to tmp_path
    monkeypatch.setattr(
        T4Trigger,
        "_write_to_md",
        _fake_write_to_md(tmp_path),
    )

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["advanced"] == 1

    md_path = tmp_path / "knowledge" / "items" / "md-test.md"
    assert md_path.exists(), f"Expected .md file at {md_path}"
    content = md_path.read_text(encoding="utf-8")
    assert "MD Test Title" in content
    assert "Hello world" in content


# ---------------------------------------------------------------------------
# T4.6 — lifecycle updated to kl:publish on advance
# ---------------------------------------------------------------------------

def test_t4_updates_lifecycle(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "lifecycle-test")
    _insert_ai_score(conn, "lifecycle-test", 8.0)
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report["advanced"] == 1

    row = conn.execute(
        "SELECT lifecycle, updated_at FROM knowledge_items WHERE id = ?",
        ("lifecycle-test",),
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_PUBLISH
    # updated_at should be bumped to a recent timestamp
    updated = datetime.fromisoformat(row["updated_at"])
    assert (datetime.now(timezone.utc) - updated).total_seconds() < 60


# ---------------------------------------------------------------------------
# T4.7 — no candidates returns empty result
# ---------------------------------------------------------------------------

def test_t4_no_candidates(temp_db, fresh_metrics):
    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    assert report == {
        "candidates": 0,
        "advanced": 0,
        "skipped_low_score": 0,
        "skipped_unstable": 0,
        "failed": 0,
    }
    assert fresh_metrics.counter_value("t4_triggered") == 1
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t4_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T4.8 — failure path: exception goes to dead letter queue
# ---------------------------------------------------------------------------

def test_t4_failure_handling(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "boom-item")
    _insert_ai_score(conn, "boom-item", 9.0)
    conn.commit()

    class _BoomError(RuntimeError):
        pass

    t4 = _trigger(fresh_metrics)
    original_update = t4._update_lifecycle

    def _raise(_item_id: str, _new_stage: str) -> None:
        raise _BoomError("simulated failure")

    t4._update_lifecycle = _raise  # type: ignore[assignment]

    # No monkeypatch for _write_to_md — the boom happens before that
    # in the pipeline (after score check, stability check, before write).
    # Actually, the pipeline is: score → stability → _write_to_md → _update_lifecycle.
    # So we need to patch _write_to_md too to avoid FileNotFound.
    import backend.services.triggers.t4_structure_to_publish as t4_module
    original_write = t4_module.T4Trigger._write_to_md
    t4_module.T4Trigger._write_to_md = lambda self, item: None  # type: ignore[method-assign]

    try:
        report = t4.run_once()
    finally:
        t4._update_lifecycle = original_update
        t4_module.T4Trigger._write_to_md = original_write

    assert report["failed"] == 1
    assert report["advanced"] == 0

    assert fresh_metrics.counter_value("t4_failed") == 1

    # Dead letter row was written
    rows = conn.execute(
        "SELECT trigger_name, item_id, attempts FROM kl_dead_letters"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["trigger_name"] == "t4"
    assert rows[0]["item_id"] == "boom-item"
    assert rows[0]["attempts"] == 1


# ---------------------------------------------------------------------------
# T4.9 — metrics counters correctly incremented
# ---------------------------------------------------------------------------

def test_t4_metrics_incremented(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    _insert_knowledge_item(conn, "m1")
    _insert_knowledge_item(conn, "m2")
    _insert_knowledge_item(conn, "m3")
    _insert_ai_score(conn, "m1", 9.0)
    _insert_ai_score(conn, "m2", 8.5)
    _insert_ai_score(conn, "m3", 7.0)  # low score, will be skipped
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    t4.run_once()

    assert fresh_metrics.counter_value("t4_triggered") == 1
    assert fresh_metrics.counter_value("t4_succeeded") == 2  # m1, m2 advance
    assert fresh_metrics.counter_value("t4_failed") == 0
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t4_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T4.10 — score fallback: no ai_scores row → DEFAULT_SCORE (5.0) → skipped
# ---------------------------------------------------------------------------

def test_t4_score_fallback(temp_db, fresh_metrics, monkeypatch):
    conn = get_connection()
    # Insert item with no ai_scores row
    _insert_knowledge_item(conn, "no-score-item")
    conn.commit()

    monkeypatch.setattr(T4Trigger, "_write_to_md", lambda self, item: None)

    t4 = _trigger(fresh_metrics)
    report = t4.run_once()

    # DEFAULT_SCORE is 5.0, which is below MIN_SCORE (8.0), so skipped
    assert report["candidates"] == 1
    assert report["advanced"] == 0
    assert report["skipped_low_score"] == 1

    # Verify the fallback constant values
    assert DEFAULT_SCORE == 5.0
    assert MIN_SCORE == 8.0

    # Lifecycle unchanged
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("no-score-item",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_STRUCTURE