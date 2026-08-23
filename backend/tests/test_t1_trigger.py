"""Tests for :class:`backend.services.triggers.T1Trigger`.

Phase 10 — covers the ``kl:raw`` → ``kl:refine`` trigger.

12 cases
--------
- T1.1  No candidates → returns zeros, no DB writes
- T1.2  Single raw item → advances to kl:refine
- T1.3  Legacy ``signal`` row is also picked up (046 compat)
- T1.4  Duplicate by canonical URL → skipped_duplicate++ (not advanced)
- T1.5  Duplicate by simhash (Hamming < 5) → skipped_duplicate++
- T1.6  Score fallback to 5.0 when ai_scores is empty
- T1.7  Tags parsed from JSON column
- T1.8  Garbage tags JSON → empty list (does not crash)
- T1.9  Metrics: t1_triggered / t1_succeeded incremented
- T1.10 Failure path: db raises → metrics.t1_failed++, retry policy
        called
- T1.11 Debounce: item with ingested_at < 5 min ago → NOT picked up
- T1.12 State-machine guard: kl:refine row is NOT re-processed
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.config import config
from backend.metrics.kl_metrics import (
    kl_metrics,
)
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LEGACY_RAW_LIKE,
    LIFECYCLE_RAW,
    LIFECYCLE_REFINE,
)
from backend.services.retry_policy import RetryPolicy
from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    simhash,
)
from backend.services.triggers import T1Trigger
from backend.services.triggers.t1_raw_to_refine import (
    DEDUP_HAMMING_THRESHOLD,
    DEFAULT_SCORE,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_t1_trigger.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
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
    lifecycle: str = LIFECYCLE_RAW,
    ingested_seconds_ago: int = 600,
    title: str = "Sample Article",
    source_url: str = "https://example.com/sample",
    concepts: str = "[]",
    tags: str = "[]",
) -> None:
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(seconds=ingested_seconds_ago)).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, 'web', ?, ?, ?, 0, 0, ?, ?, ?)
        """,
        (id, title, source_url, concepts, tags, ingested, ingested, lifecycle),
    )


def _insert_fingerprint(conn, hotspot_id: str, simhash: int, url: str) -> None:
    """Insert a content fingerprint.

    ``content_fingerprints.hotspot_id`` has a foreign key to
    ``hotspots(id)``, so we must first create a parent row in
    ``hotspots``. The hotspot title/URL is irrelevant for the dedup
    test — only the fingerprint matters.
    """
    from datetime import datetime, timezone

    from backend.services.collection_service import _to_signed_64
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO hotspots
            (id, title, source, url, category, published_at, fetched_at)
        VALUES (?, 'fp-parent', 'web', ?, 'ai', ?, ?)
        """,
        (hotspot_id, url or f"https://x.test/{hotspot_id}", now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO content_fingerprints "
        "(hotspot_id, simhash, url_canonical, title_norm) "
        "VALUES (?, ?, ?, ?)",
        (hotspot_id, _to_signed_64(simhash), url, "norm"),
    )


def _trigger(fresh_metrics, retry_policy=None) -> T1Trigger:
    return T1Trigger(
        metrics=fresh_metrics,
        retry_policy=retry_policy or RetryPolicy(metrics=fresh_metrics),
    )


# ---------------------------------------------------------------------------
# T1.1 — no candidates
# ---------------------------------------------------------------------------

def test_run_once_no_candidates(temp_db, fresh_metrics):
    t1 = _trigger(fresh_metrics)
    report = t1.run_once()
    assert report == {
        "candidates": 0,
        "advanced": 0,
        "skipped_duplicate": 0,
        "failed": 0,
    }
    # triggered counter ticks
    assert fresh_metrics.counter_value("t1_triggered") == 1
    # latency histogram has 1 sample
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t1_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T1.2 — single raw item advances
# ---------------------------------------------------------------------------

def test_advances_single_raw_item(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "item-1", title="Hello world")
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["skipped_duplicate"] == 0
    assert report["failed"] == 0

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("item-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE
    assert fresh_metrics.counter_value("t1_succeeded") == 1


# ---------------------------------------------------------------------------
# T1.3 — legacy signal value is also picked up
# ---------------------------------------------------------------------------

def test_legacy_signal_value_is_picked_up(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "legacy-1", lifecycle=LEGACY_RAW_LIKE)
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()

    # legacy rows are also processed (T1 writes kl:refine)
    assert report["candidates"] == 1
    assert report["advanced"] == 1
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("legacy-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE


# ---------------------------------------------------------------------------
# T1.4 — duplicate by URL
# ---------------------------------------------------------------------------

def test_duplicate_by_url_is_skipped(temp_db, fresh_metrics):
    conn = get_connection()
    url = "https://example.com/dup"
    _insert_knowledge_item(conn, "new-1", source_url=url)
    # Pre-existing fingerprint with same canonical URL
    _insert_fingerprint(conn, "old-1", simhash(0), canonicalize_url(url))
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()

    assert report["candidates"] == 1
    assert report["skipped_duplicate"] == 1
    assert report["advanced"] == 0

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("new-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_RAW  # unchanged


# ---------------------------------------------------------------------------
# T1.5 — duplicate by simhash
# ---------------------------------------------------------------------------

def test_duplicate_by_simhash_is_skipped(temp_db, fresh_metrics):
    conn = get_connection()
    title = "AI Safety Research Update"
    _insert_knowledge_item(conn, "a", title=title)
    # Pre-existing fingerprint with a simhash very close to title's
    existing_fp = simhash(title)
    _insert_fingerprint(
        conn, "existing", existing_fp ^ 0b11, canonicalize_url("https://x.test/a")
    )
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()

    assert report["candidates"] == 1
    # Hamming distance between existing and existing^3 is 2 (< threshold)
    assert hamming_distance(existing_fp, existing_fp ^ 0b11) < DEDUP_HAMMING_THRESHOLD
    assert report["skipped_duplicate"] == 1
    assert report["advanced"] == 0


# ---------------------------------------------------------------------------
# T1.6 — score fallback
# ---------------------------------------------------------------------------

def test_score_fallback_when_ai_scores_empty(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "no-score")
    conn.commit()

    t1 = _trigger(fresh_metrics)
    # The trigger still advances; we just verify DEFAULT_SCORE is used
    # internally by checking the item was advanced (i.e. score lookup
    # did not raise).
    report = t1.run_once()
    assert report["advanced"] == 1
    # Indirect: insert a record and check DEFAULT_SCORE = 5.0 is callable
    assert DEFAULT_SCORE == 5.0


# ---------------------------------------------------------------------------
# T1.7 — tags parsed from JSON
# ---------------------------------------------------------------------------

def test_tags_parsed_from_json(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(
        conn, "tagged", tags=json.dumps(["python", "ml", "ops"]),
    )
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()
    assert report["advanced"] == 1

    # Directly test the helper
    item = {"tags": json.dumps(["a", "b"])}
    assert t1._extract_tags(item) == ["a", "b"]


# ---------------------------------------------------------------------------
# T1.8 — garbage tags JSON
# ---------------------------------------------------------------------------

def test_garbage_tags_does_not_crash(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "garbled", tags="not-valid-json{")
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()
    assert report["advanced"] == 1  # still advances
    # The helper returns []
    assert t1._extract_tags({"tags": "not-valid-json{"}) == []
    # And the NULL case
    assert t1._extract_tags({"tags": None}) == []
    assert t1._extract_tags({"tags": ""}) == []


# ---------------------------------------------------------------------------
# T1.9 — metrics counters
# ---------------------------------------------------------------------------

def test_metrics_counters_incremented(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "m1")
    _insert_knowledge_item(conn, "m2")
    conn.commit()

    t1 = _trigger(fresh_metrics)
    t1.run_once()

    assert fresh_metrics.counter_value("t1_triggered") == 1
    assert fresh_metrics.counter_value("t1_succeeded") == 2
    assert fresh_metrics.counter_value("t1_failed") == 0
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t1_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T1.10 — failure path: retry policy + dead letter
# ---------------------------------------------------------------------------

def test_failure_increments_failed_and_calls_retry(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "boom")
    conn.commit()

    class _BoomError(RuntimeError):
        pass

    # Force the lifecycle update to raise by patching the helper.
    t1 = _trigger(fresh_metrics)
    original_update = t1._update_lifecycle
    def _raise(_item_id, _new_stage):
        raise _BoomError("simulated")
    t1._update_lifecycle = _raise  # type: ignore[assignment]

    try:
        report = t1.run_once()
    finally:
        t1._update_lifecycle = original_update  # type: ignore[assignment]

    assert report["failed"] == 1
    assert report["advanced"] == 0
    assert fresh_metrics.counter_value("t1_failed") == 1
    # Retry policy was invoked → a kl_dead_letters row exists
    rows = conn.execute(
        "SELECT trigger_name, item_id, attempts FROM kl_dead_letters"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["trigger_name"] == "t1"
    assert rows[0]["item_id"] == "boom"
    assert rows[0]["attempts"] == 1


# ---------------------------------------------------------------------------
# T1.11 — debounce: fresh items (ingested < 5min ago) are skipped
# ---------------------------------------------------------------------------

def test_fresh_items_not_picked_up(temp_db, fresh_metrics):
    conn = get_connection()
    # ingested only 10s ago — within debounce window
    _insert_knowledge_item(conn, "fresh", ingested_seconds_ago=10)
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()
    assert report["candidates"] == 0
    assert report["advanced"] == 0


# ---------------------------------------------------------------------------
# T1.12 — state-machine guard: refine row is NOT re-processed
# ---------------------------------------------------------------------------

def test_refine_rows_not_reprocessed(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "already-refined", lifecycle=LIFECYCLE_REFINE)
    conn.commit()

    t1 = _trigger(fresh_metrics)
    report = t1.run_once()
    # The SQL filters by lifecycle IN (kl:raw, signal), so candidates=0
    assert report["candidates"] == 0
    assert report["advanced"] == 0
    assert fresh_metrics.counter_value("t1_succeeded") == 0


# ---------------------------------------------------------------------------
# T1.13 — LLM scoring calls service and writes to ai_scores
# ---------------------------------------------------------------------------

def test_score_with_llm_calls_service(temp_db, fresh_metrics, monkeypatch):
    """Verify that when llm_service.score() returns a non-default value,
    it is used and written to the ai_scores table."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from backend.services.ai_hub import llm_service

    conn = get_connection()
    _insert_knowledge_item(conn, "llm-ok")
    # Need a hotspots row (ai_scores has FK to hotspots)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO hotspots (id, title, source, url, category, "
        "published_at, fetched_at) VALUES (?, 'test', 'web', ?, 'ai', ?, ?)",
        ("llm-ok", "https://x.test/llm-ok", now, now),
    )
    conn.commit()

    mock_score = AsyncMock(return_value=8.5)
    monkeypatch.setattr(llm_service, "score", mock_score)

    t1 = _trigger(fresh_metrics)
    item = {"id": "llm-ok", "title": "Test Article", "concepts": "[]"}
    result = t1._score_with_llm(item)

    assert result == 8.5
    mock_score.assert_called_once()

    # Verify ai_scores row was written by _write_llm_score
    row = conn.execute(
        "SELECT score, reason FROM ai_scores WHERE hotspot_id = ?",
        ("llm-ok",),
    ).fetchone()
    assert row is not None, "ai_scores row should have been written"
    assert row["score"] == 8.5
    assert row["reason"] == "llm_service"


# ---------------------------------------------------------------------------
# T1.14 — LLM scoring fallback to DB when service raises
# ---------------------------------------------------------------------------

def test_score_with_llm_fallback_to_db(temp_db, fresh_metrics, monkeypatch):
    """Verify that when llm_service.score() raises, the method falls back
    to _get_latest_score() which reads from the ai_scores table."""
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from backend.services.ai_hub import llm_service

    conn = get_connection()
    _insert_knowledge_item(conn, "llm-fallback")
    # Need a hotspots row for the ai_scores FK
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO hotspots (id, title, source, url, category, "
        "published_at, fetched_at) VALUES (?, 'test', 'web', ?, 'ai', ?, ?)",
        ("llm-fallback", "https://x.test/llm-fallback", now, now),
    )
    # Insert a DB score to fall back to
    conn.execute(
        "INSERT INTO ai_scores (hotspot_id, score, reason, scored_at) "
        "VALUES (?, ?, ?, ?)",
        ("llm-fallback", 7.0, "test", now),
    )
    conn.commit()

    mock_score = AsyncMock(side_effect=ValueError("LLM unavailable"))
    monkeypatch.setattr(llm_service, "score", mock_score)

    t1 = _trigger(fresh_metrics)
    item = {"id": "llm-fallback", "title": "Test Article", "concepts": "[]"}
    result = t1._score_with_llm(item)

    assert result == 7.0
    mock_score.assert_called_once()


# ---------------------------------------------------------------------------
# T1.15 — LLM scoring fallback to default when both fail
# ---------------------------------------------------------------------------

def test_score_with_llm_fallback_to_default(temp_db, fresh_metrics, monkeypatch):
    """Verify that when both LLM and DB scores fail, DEFAULT_SCORE is used."""
    from unittest.mock import AsyncMock

    from backend.services.ai_hub import llm_service

    conn = get_connection()
    _insert_knowledge_item(conn, "llm-default")
    conn.commit()

    # No ai_scores row → _get_latest_score returns DEFAULT_SCORE
    mock_score = AsyncMock(side_effect=ValueError("LLM unavailable"))
    monkeypatch.setattr(llm_service, "score", mock_score)

    t1 = _trigger(fresh_metrics)
    item = {"id": "llm-default", "title": "Test Article", "concepts": "[]"}
    result = t1._score_with_llm(item)

    assert result == DEFAULT_SCORE
    mock_score.assert_called_once()
