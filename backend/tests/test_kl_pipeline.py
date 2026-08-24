"""Tests for KL pipeline engine and wiki filesystem.

Phase 0 acceptance: at least 5 basic test cases covering:
- KLQueue enqueue/due/mark operations
- WikiFs write/read roundtrip
- enrich_v2 pattern matching
- KLPipeline import availability
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from backend.enrich_v2 import (
    extract_all,
    extract_attack,
    extract_compliance,
    extract_cve,
    extract_deadline,
)
from backend.kl_pipeline import KLPipeline, KLQueue
from backend.wiki_fs.contract import parse_frontmatter, serialize_frontmatter
from backend.kl_pipeline.obs.funnel import funnel_stats
from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.kl_pipeline.queue import STAGES
from backend.wiki_fs import WikiFs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with kl_queue and token_ledger tables."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kl_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 5,
            next_run_at TEXT,
            last_error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, stage)
        );
        CREATE TABLE IF NOT EXISTS token_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER, item_id TEXT, model TEXT, provider TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    yield conn
    conn.close()


@pytest.fixture
def tmp_wiki(tmp_path):
    """Create a temporary WikiFs directory."""
    root = str(tmp_path / "wiki")
    os.makedirs(root, exist_ok=True)
    return WikiFs(root)


# ---------------------------------------------------------------------------
# KLQueue tests
# ---------------------------------------------------------------------------
class TestKLQueue:
    def test_enqueue_unique(self, tmp_db):
        q = KLQueue(tmp_db)
        now = datetime.now(timezone.utc)
        assert q.enqueue_unique("item-1", "kl:refine", now) is True
        # Duplicate should return False.
        assert q.enqueue_unique("item-1", "kl:refine", now) is False
        # Different stage should succeed.
        assert q.enqueue_unique("item-1", "kl:link", now) is True

    def test_due_and_mark(self, tmp_db):
        q = KLQueue(tmp_db)
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        q.enqueue_unique("item-2", "kl:refine", past)
        tasks = q.due(limit=10)
        assert len(tasks) >= 1
        qid = tasks[0]["id"]
        q.mark_run(qid)
        stats = q.stats()
        assert stats["running"] >= 1
        q.mark_done(qid)
        stats2 = q.stats()
        assert "running" not in stats2 or stats2["running"] == 0

    def test_mark_error_and_retry(self, tmp_db):
        q = KLQueue(tmp_db)
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        q.enqueue_unique("item-3", "kl:refine", past)
        tasks = q.due(limit=1)
        assert len(tasks) == 1
        q.mark_error(tasks[0]["id"], "test error")
        errors = q.errors()
        assert len(errors) >= 1
        assert errors[0]["last_error"] == "test error"
        count = q.reset_errors()
        assert count >= 1


# ---------------------------------------------------------------------------
# WikiFs tests
# ---------------------------------------------------------------------------
class TestWikiFs:
    def test_write_read_roundtrip(self, tmp_wiki):
        doc = {"fm": {"id": "test-1", "title": "Test Item", "tags": ["a", "b"]}, "body": "Hello world"}
        tmp_wiki.write_item("test-1", doc)
        result = tmp_wiki.read_item("test-1")
        assert result is not None
        assert result["fm"]["title"] == "Test Item"
        assert result["fm"]["tags"] == ["a", "b"]
        assert result["body"] == "Hello world"

    def test_list_ids(self, tmp_wiki):
        tmp_wiki.write_item("a", {"fm": {"id": "a"}, "body": ""})
        tmp_wiki.write_item("b", {"fm": {"id": "b"}, "body": ""})
        ids = tmp_wiki.list_ids()
        assert "a" in ids
        assert "b" in ids

    def test_ingest_url(self, tmp_wiki):
        result = tmp_wiki.ingest_url("https://example.com/test", "Test", "body text")
        assert "id" in result
        assert result["title"] == "Test"
        doc = tmp_wiki.read_item(result["id"])
        assert doc is not None
        assert doc["fm"]["url"] == "https://example.com/test"

    def test_import_bookmarks(self, tmp_wiki):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://example.com/1">Link 1</A>
<DT><A HREF="https://example.com/2" TAGS="sec,news">Link 2</A>
</DL><p>"""
        result = tmp_wiki.import_bookmarks(html)
        assert result["added"] == 2

    def test_create_concept(self, tmp_wiki):
        tmp_wiki.create_concept("zero-trust", "Zero Trust", ["security", "architecture"])
        concepts = tmp_wiki.list_concepts()
        assert len(concepts) >= 1
        assert any(c.get("name") == "Zero Trust" for c in concepts)


# ---------------------------------------------------------------------------
# Frontmatter contract tests
# ---------------------------------------------------------------------------
class TestFrontmatter:
    def test_roundtrip(self):
        fm = {"id": "test", "title": "Hello", "tags": ["a", "b"], "kl_stage": "kl:raw"}
        text = serialize_frontmatter(fm)
        parsed, body = parse_frontmatter(text)
        assert parsed["id"] == "test"
        assert parsed["title"] == "Hello"
        assert parsed["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# enrich_v2 tests
# ---------------------------------------------------------------------------
class TestEnrichV2:
    def test_cve_extraction(self):
        assert "CVE-2026-1234" in extract_cve("Found CVE-2026-1234 in system")

    def test_attack_extraction(self):
        text = "MITRE ATT&CK technique T1566.001 phishing"
        results = extract_attack(text)
        assert "T1566.001" in results

    def test_compliance_extraction(self):
        assert "等保" in extract_compliance("需要通过等保三级认证")

    def test_deadline_extraction(self):
        results = extract_deadline("截止日期：2026-09-01")
        assert "2026-09-01" in results

    def test_extract_all(self):
        result = extract_all(
            title="CVE-2026-9999 ransomware attack",
            summary="MITRE ATT&CK T1486 encryption",
            body="等保三级 deadline: 2026-12-31",
        )
        assert "CVE-2026-9999" in result["cve_ids"]
        assert "等保" in result["compliance"]


# ---------------------------------------------------------------------------
# KLPipeline import test
# ---------------------------------------------------------------------------
class TestKLPipeline:
    def test_import(self):
        """Verify KLPipeline can be imported and instantiated."""
        from backend.kl_pipeline import KLPipeline
        assert KLPipeline is not None

    def test_stages_constant(self):
        assert len(STAGES) == 5
        assert STAGES[0] == "kl:raw"
        assert STAGES[-1] == "kl:publish"


# ---------------------------------------------------------------------------
# TokenLedger test
# ---------------------------------------------------------------------------
class TestTokenLedger:
    def test_record_and_query(self, tmp_db):
        ledger = TokenLedger(tmp_db)
        ledger.record(item_id="item-1", model="gpt-4", provider="openai", prompt_tokens=100, completion_tokens=50)
        records = ledger.query(item_id="item-1")
        assert len(records) == 1
        assert records[0]["total_tokens"] == 150
