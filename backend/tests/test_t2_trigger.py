"""Tests for :class:`backend.services.triggers.T2Trigger`.

Phase 10 — covers the ``kl:refine`` → ``kl:link`` trigger.

10 cases
--------
- T2.1  No candidates → zeros
- T2.2  Single refine item with no concepts → low_link, still advanced
- T2.3  Refine item with matching concept → knowledge_links row written
- T2.4  Refine item with multiple matches → up to MAX_RELATED links
- T2.5  Tags column is used as concept fallback when concepts is empty
- T2.6  Self-link is not written (item_id excluded from related)
- T2.7  Duplicate link writes are idempotent (INSERT OR IGNORE)
- T2.8  Legacy ``amplify:tagged`` rows are processed
- T2.9  Metrics: t2_triggered / t2_succeeded / t2_latency_ms
- T2.10 Failure path: db raises → metrics.t2_failed++ + retry policy
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.config import config
from backend.metrics.kl_metrics import kl_metrics
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LEGACY_REFINE_LIKE,
    LIFECYCLE_LINK,
    LIFECYCLE_REFINE,
)
from backend.services.retry_policy import RetryPolicy
from backend.services.triggers import T2Trigger
from backend.services.triggers.t2_refine_to_link import (
    LINK_CONFIDENCE,
    MAX_RELATED,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_t2_trigger.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    yield test_db
    db_module.close_db()


@pytest.fixture
def fresh_metrics():
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
    lifecycle: str = LIFECYCLE_REFINE,
    title: str = "Sample",
    concepts: str = "[]",
    tags: str = "[]",
    source_url: str = "https://example.com/x",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, 'web', ?, ?, ?, 0, 0, ?, ?, ?)
        """,
        (id, title, source_url, concepts, tags, now, now, lifecycle),
    )


def _trigger(fresh_metrics, retry_policy=None) -> T2Trigger:
    return T2Trigger(
        metrics=fresh_metrics,
        retry_policy=retry_policy or RetryPolicy(metrics=fresh_metrics),
    )


# ---------------------------------------------------------------------------
# T2.1 — no candidates
# ---------------------------------------------------------------------------

def test_run_once_no_candidates(temp_db, fresh_metrics):
    t2 = _trigger(fresh_metrics)
    report = t2.run_once()
    assert report == {
        "candidates": 0,
        "advanced": 0,
        "low_link": 0,
        "failed": 0,
    }
    assert fresh_metrics.counter_value("t2_triggered") == 1


# ---------------------------------------------------------------------------
# T2.2 — single refine item, no concepts → low_link but advanced
# ---------------------------------------------------------------------------

def test_advance_with_no_concepts_is_low_link(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "solo", concepts="[]", tags="[]")
    conn.commit()

    t2 = _trigger(fresh_metrics)
    report = t2.run_once()

    assert report["candidates"] == 1
    assert report["advanced"] == 1
    assert report["low_link"] == 1  # no related items

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("solo",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_LINK

    # No link rows should have been written
    links = conn.execute("SELECT * FROM knowledge_links").fetchall()
    assert len(links) == 0


# ---------------------------------------------------------------------------
# T2.3 — single match → 1 link row
# ---------------------------------------------------------------------------

def test_single_concept_match_writes_one_link(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(
        conn, "src", concepts=json.dumps(["rag", "llm"]),
    )
    _insert_knowledge_item(
        conn, "dst", lifecycle=LIFECYCLE_REFINE,
        concepts=json.dumps(["rag", "vector-db"]),
    )
    conn.commit()

    t2 = _trigger(fresh_metrics)
    report = t2.run_once()
    assert report["advanced"] == 2  # both promoted to kl:link
    assert report["low_link"] == 0  # both have at least one related

    links = conn.execute(
        "SELECT from_item_id, to_item_id, link_type, confidence, created_by "
        "FROM knowledge_links ORDER BY id"
    ).fetchall()
    # Each item finds the other → 2 directed link rows
    assert len(links) == 2
    pairs = {(r["from_item_id"], r["to_item_id"]) for r in links}
    assert ("src", "dst") in pairs
    assert ("dst", "src") in pairs
    for r in links:
        assert r["link_type"] == "similar"
        assert r["confidence"] == LINK_CONFIDENCE
        assert r["created_by"] == "trigger"


# ---------------------------------------------------------------------------
# T2.4 — multiple matches capped at MAX_RELATED
# ---------------------------------------------------------------------------

def test_matches_capped_at_max_related(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "src", concepts=json.dumps(["python"]))
    # 10 candidate items all sharing the concept
    for i in range(10):
        _insert_knowledge_item(
            conn, f"dst-{i:02d}", concepts=json.dumps(["python", f"topic-{i}"]),
        )
    conn.commit()

    t2 = _trigger(fresh_metrics)
    t2.run_once()

    links = conn.execute(
        "SELECT to_item_id FROM knowledge_links WHERE from_item_id = ?",
        ("src",),
    ).fetchall()
    assert len(links) == MAX_RELATED


# ---------------------------------------------------------------------------
# T2.5 — tags fallback as concept source
# ---------------------------------------------------------------------------

def test_tags_used_when_concepts_empty(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(
        conn, "src", concepts="[]", tags=json.dumps(["docker", "k8s"]),
    )
    _insert_knowledge_item(
        conn, "dst", lifecycle=LIFECYCLE_REFINE,
        concepts="[]", tags=json.dumps(["docker"]),
    )
    conn.commit()

    t2 = _trigger(fresh_metrics)
    report = t2.run_once()
    assert report["low_link"] == 0  # found related via tags

    links = conn.execute(
        "SELECT COUNT(*) AS n FROM knowledge_links WHERE from_item_id = 'src'"
    ).fetchone()
    assert links["n"] == 1


# ---------------------------------------------------------------------------
# T2.6 — self not in related
# ---------------------------------------------------------------------------

def test_self_is_not_in_related(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "self-1", concepts=json.dumps(["x"]))
    conn.commit()

    t2 = _trigger(fresh_metrics)
    t2.run_once()

    links = conn.execute(
        "SELECT * FROM knowledge_links WHERE from_item_id = 'self-1' "
        "AND to_item_id = 'self-1'"
    ).fetchall()
    assert len(links) == 0


# ---------------------------------------------------------------------------
# T2.7 — duplicate link writes are idempotent
# ---------------------------------------------------------------------------

def test_duplicate_links_are_idempotent(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "a", concepts=json.dumps(["t"]))
    _insert_knowledge_item(conn, "b", concepts=json.dumps(["t"]))
    conn.commit()

    t2 = _trigger(fresh_metrics)
    t2.run_once()  # first cycle
    t2.run_once()  # second cycle (idempotent)

    # No duplicates: the unique index on (from,to,link_type) blocks them
    rows = conn.execute("SELECT * FROM knowledge_links").fetchall()
    assert len(rows) == 2  # one each direction


# ---------------------------------------------------------------------------
# T2.8 — legacy ``amplify:tagged`` is processed
# ---------------------------------------------------------------------------

def test_legacy_refine_value_is_picked_up(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "legacy-1", lifecycle=LEGACY_REFINE_LIKE)
    conn.commit()

    t2 = _trigger(fresh_metrics)
    report = t2.run_once()
    assert report["candidates"] == 1
    assert report["advanced"] == 1

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("legacy-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_LINK


# ---------------------------------------------------------------------------
# T2.9 — metrics
# ---------------------------------------------------------------------------

def test_metrics_counters_and_histogram(temp_db, fresh_metrics):
    conn = get_connection()
    _insert_knowledge_item(conn, "m1")
    _insert_knowledge_item(conn, "m2")
    conn.commit()

    t2 = _trigger(fresh_metrics)
    t2.run_once()

    assert fresh_metrics.counter_value("t2_triggered") == 1
    assert fresh_metrics.counter_value("t2_succeeded") == 2
    assert fresh_metrics.counter_value("t2_failed") == 0
    snap = fresh_metrics.snapshot()
    assert snap["histograms"]["t2_latency_ms"]["count"] == 1


# ---------------------------------------------------------------------------
# T2.10 — failure path: retry policy + dead letter
# ---------------------------------------------------------------------------

def test_failure_increments_failed_and_writes_dead_letter(
    temp_db, fresh_metrics
):
    conn = get_connection()
    _insert_knowledge_item(conn, "boom")
    conn.commit()

    t2 = _trigger(fresh_metrics)
    def _raise(_item_id, _new_stage):
        raise RuntimeError("simulated")
    t2._update_lifecycle = _raise  # type: ignore[assignment]

    report = t2.run_once()
    assert report["failed"] == 1
    assert report["advanced"] == 0
    assert fresh_metrics.counter_value("t2_failed") == 1

    rows = conn.execute(
        "SELECT trigger_name, item_id, attempts FROM kl_dead_letters"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["trigger_name"] == "t2"
    assert rows[0]["item_id"] == "boom"
    assert rows[0]["attempts"] == 1
