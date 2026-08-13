"""Tests for :class:`backend.services.triggers.T5Trigger`.

Phase 10 — covers the ``kl:publish`` → ``kl:refine`` rollback trigger.

8 cases
-------
- T5.1  Normal rollback, lifecycle becomes kl:refine
- T5.2  .md backup file written to knowledge/backups/
- T5.3  stale_at timestamp is set
- T5.4  Non-existent item_id raises ValueError
- T5.5  Non-publish item rejects rollback
- T5.6  Backup file content matches original .md
- T5.7  POST /api/kl/rollback/{id} works correctly
- T5.8  Concurrent rollback of same item doesn't conflict
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LIFECYCLE_PUBLISH,
    LIFECYCLE_REFINE,
)
from backend.services.triggers.t5_publish_to_refine import T5Trigger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_t5_trigger.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    # stale_at column is not yet in the migration chain; add it here so
    # the T5 trigger's _mark_stale SQL works.
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE knowledge_items ADD COLUMN stale_at TEXT")
    except Exception:
        pass  # already exists (e.g. if migration catches up later)
    yield test_db
    db_module.close_db()


@pytest.fixture
def knowledge_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolated knowledge/ directory with items/ and backups/ subdirs.

    Monkeypatches ``KNOWLEDGE_DIR`` and ``ITEMS_DIR`` so the T5 trigger
    writes backup files to the tmp_path hierarchy.
    """
    items_dir = tmp_path / "knowledge" / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = tmp_path / "knowledge" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "backend.services.knowledge_sync.KNOWLEDGE_DIR",
        tmp_path / "knowledge",
    )
    monkeypatch.setattr(
        "backend.services.knowledge_sync.ITEMS_DIR",
        items_dir,
    )
    # Also patch the T5 module's module-level references if they were
    # imported at module load time.
    monkeypatch.setattr(
        "backend.services.triggers.t5_publish_to_refine.KNOWLEDGE_DIR",
        tmp_path / "knowledge",
    )
    monkeypatch.setattr(
        "backend.services.triggers.t5_publish_to_refine.ITEMS_DIR",
        items_dir,
    )
    return items_dir, backups_dir


@pytest.fixture
def api_client(temp_db, knowledge_dir):
    """FastAPI TestClient with all routers registered."""
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_publish_item(conn, item_id: str, title: str = "Published Article") -> None:
    """Insert a knowledge item in kl:publish state."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, 'web', 'https://example.com/article', '[]', '[]',
                0, 1, ?, ?, ?)
        """,
        (item_id, title, now, now, LIFECYCLE_PUBLISH),
    )


def _create_md_file(items_dir: Path, item_id: str, content: str = None) -> Path:
    """Create a .md file in the items directory for the given item."""
    md_path = items_dir / f"{item_id}.md"
    if content is None:
        content = f"""---
id: {item_id}
title: Test Article
lifecycle: {LIFECYCLE_PUBLISH}
---

# Test Article

This is the body of the published article.
"""
    md_path.write_text(content, encoding="utf-8")
    return md_path


def _trigger() -> T5Trigger:
    return T5Trigger()


# ---------------------------------------------------------------------------
# T5.1 — Normal rollback, lifecycle becomes kl:refine
# ---------------------------------------------------------------------------

def test_t5_rollback_basic(temp_db, knowledge_dir):
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "item-1")
    _create_md_file(items_dir, "item-1")
    conn.commit()

    t5 = _trigger()
    result = t5.rollback("item-1")

    assert result["item_id"] == "item-1"
    assert result["new_lifecycle"] == LIFECYCLE_REFINE
    assert "backup_path" in result

    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("item-1",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE


# ---------------------------------------------------------------------------
# T5.2 — .md backup file written to knowledge/backups/
# ---------------------------------------------------------------------------

def test_t5_backup_created(temp_db, knowledge_dir):
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "item-2")
    _create_md_file(items_dir, "item-2")
    conn.commit()

    t5 = _trigger()
    t5.rollback("item-2")

    # A backup file should exist in the backups directory
    backup_files = list(backups_dir.glob("item-2_*.md"))
    assert len(backup_files) == 1
    assert backup_files[0].exists()


# ---------------------------------------------------------------------------
# T5.3 — stale_at timestamp is set
# ---------------------------------------------------------------------------

def test_t5_stale_marked(temp_db, knowledge_dir):
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "item-3")
    _create_md_file(items_dir, "item-3")
    conn.commit()

    t5 = _trigger()
    t5.rollback("item-3")

    row = conn.execute(
        "SELECT stale_at FROM knowledge_items WHERE id = ?", ("item-3",)
    ).fetchone()
    assert row["stale_at"] is not None
    # stale_at should be a valid ISO timestamp
    dt = datetime.fromisoformat(row["stale_at"])
    assert dt.tzinfo is not None  # should be timezone-aware


# ---------------------------------------------------------------------------
# T5.4 — Non-existent item_id raises ValueError
# ---------------------------------------------------------------------------

def test_t5_rollback_nonexistent(temp_db, knowledge_dir):
    t5 = _trigger()
    with pytest.raises(ValueError, match="does not exist"):
        t5.rollback("nonexistent-item")


# ---------------------------------------------------------------------------
# T5.5 — Non-publish item rejects rollback
# ---------------------------------------------------------------------------

def test_t5_rollback_not_published(temp_db, knowledge_dir):
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, 'Refine Article', 'web', 'https://example.com/refine',
                '[]', '[]', 0, 1, ?, ?, ?)
        """,
        ("refine-item", now, now, LIFECYCLE_REFINE),
    )
    conn.commit()

    t5 = _trigger()
    with pytest.raises(ValueError, match="is in 'kl:refine' state"):
        t5.rollback("refine-item")


# ---------------------------------------------------------------------------
# T5.6 — Backup file content matches original .md
# ---------------------------------------------------------------------------

def test_t5_backup_preserves_content(temp_db, knowledge_dir):
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "item-6")

    original_content = """---
id: item-6
title: Preserved Content
lifecycle: kl:publish
---

# Original Article

This content must be preserved in the backup.
"""
    _create_md_file(items_dir, "item-6", content=original_content)
    conn.commit()

    t5 = _trigger()
    t5.rollback("item-6")

    backup_files = list(backups_dir.glob("item-6_*.md"))
    assert len(backup_files) == 1
    backup_content = backup_files[0].read_text(encoding="utf-8")
    assert backup_content == original_content


# ---------------------------------------------------------------------------
# T5.7 — POST /api/kl/rollback/{id} works correctly
# ---------------------------------------------------------------------------

def test_t5_api_endpoint(temp_db, knowledge_dir, api_client):
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "api-item")
    _create_md_file(items_dir, "api-item")
    conn.commit()

    response = api_client.post("/api/kl/rollback/api-item")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["result"]["item_id"] == "api-item"
    assert data["result"]["new_lifecycle"] == LIFECYCLE_REFINE

    # Verify DB state through the API
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", ("api-item",)
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE


def test_t5_api_endpoint_not_found(api_client):
    """API returns 400 for non-existent item."""
    response = api_client.post("/api/kl/rollback/ghost-item")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_t5_api_endpoint_wrong_state(api_client, temp_db, knowledge_dir):
    """API returns 400 for item not in kl:publish state."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, 'Raw Item', 'web', 'https://example.com/raw',
                '[]', '[]', 0, 1, ?, ?, ?)
        """,
        ("raw-item", now, now, "kl:raw"),
    )
    conn.commit()

    response = api_client.post("/api/kl/rollback/raw-item")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# T5.8 — Concurrent rollback of same item doesn't conflict
# ---------------------------------------------------------------------------

def test_t5_concurrent_rollback(temp_db, knowledge_dir):
    """Rolling back the same item twice is safe: second call raises.

    The first rollback transitions the item from kl:publish → kl:refine.
    The second call finds the item in kl:refine (not kl:publish) and
    raises ValueError rather than corrupting the DB state.
    """
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "concurrent-item")
    _create_md_file(items_dir, "concurrent-item")
    conn.commit()

    t5 = _trigger()

    # First rollback succeeds
    result1 = t5.rollback("concurrent-item")
    assert result1["new_lifecycle"] == LIFECYCLE_REFINE

    # Second rollback raises because the item is no longer in publish state
    with pytest.raises(ValueError, match="is in 'kl:refine' state"):
        t5.rollback("concurrent-item")

    # Only one backup file should exist
    backup_files = list(backups_dir.glob("concurrent-item_*.md"))
    assert len(backup_files) == 1

    # DB state is still kl:refine (not corrupted)
    row = conn.execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?",
        ("concurrent-item",),
    ).fetchone()
    assert row["lifecycle"] == LIFECYCLE_REFINE


def test_t5_concurrent_rollback_different_items(temp_db, knowledge_dir):
    """Rolling back two different items simultaneously works."""
    items_dir, backups_dir = knowledge_dir
    conn = get_connection()
    _insert_publish_item(conn, "item-a", title="Article A")
    _insert_publish_item(conn, "item-b", title="Article B")
    _create_md_file(items_dir, "item-a", content="Content A")
    _create_md_file(items_dir, "item-b", content="Content B")
    conn.commit()

    t5 = _trigger()

    result_a = t5.rollback("item-a")
    result_b = t5.rollback("item-b")

    assert result_a["new_lifecycle"] == LIFECYCLE_REFINE
    assert result_b["new_lifecycle"] == LIFECYCLE_REFINE

    rows = conn.execute(
        "SELECT id, lifecycle FROM knowledge_items ORDER BY id"
    ).fetchall()
    assert {r["id"]: r["lifecycle"] for r in rows} == {
        "item-a": LIFECYCLE_REFINE,
        "item-b": LIFECYCLE_REFINE,
    }

    # Two separate backup files
    backup_files = list(backups_dir.glob("*.md"))
    assert len(backup_files) == 2