"""Tests for KL pipeline engine and wiki filesystem.

Phase 0 acceptance: at least 5 basic test cases covering:
- KLQueue enqueue/due/mark operations
- WikiFs write/read roundtrip
- enrich_v2 pattern matching
- KLPipeline import availability
"""
from __future__ import annotations

import os
import sqlite3
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
from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.kl_pipeline.queue import STAGES
from backend.wiki_fs import WikiFs
from backend.wiki_fs.contract import parse_frontmatter, serialize_frontmatter


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
        fm = {"id": "test", "title": "Hello", "tags": ["a", "b"], "lifecycle": "kl:raw"}
        text = serialize_frontmatter(fm)
        parsed, body = parse_frontmatter(text)
        assert parsed["id"] == "test"
        assert parsed["title"] == "Hello"
        assert parsed["tags"] == ["a", "b"]

    def test_get_lifecycle_contract(self):
        """SCHEMA.md 契约字段为 lifecycle; 缺失默认 kl:raw; 兼容读 kl_stage。"""
        from backend.wiki_fs.contract import get_lifecycle
        assert get_lifecycle({"lifecycle": "kl:link"}) == "kl:link"
        assert get_lifecycle({}) == "kl:raw"
        assert get_lifecycle({"kl_stage": "kl:refine"}) == "kl:refine"  # 历史兼容
        assert get_lifecycle({"lifecycle": "", "kl_stage": "kl:link"}) == "kl:link"


# ---------------------------------------------------------------------------
# Wiki root resolution tests (llm-wiki-2.0 单根)
# ---------------------------------------------------------------------------
class TestWikiRoot:
    def test_env_override(self, tmp_path, monkeypatch):
        from backend.wiki_fs.root import resolve_wiki_root
        monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(tmp_path / "wiki-root"))
        assert resolve_wiki_root() == str(tmp_path / "wiki-root")

    def test_default_points_to_llm_wiki_v2(self, monkeypatch):
        from backend.wiki_fs.root import resolve_wiki_root
        monkeypatch.delenv("HOTSPOT_WIKI_ROOT", raising=False)
        assert os.path.basename(resolve_wiki_root()) == "llm-wiki-2.0"


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


# ---------------------------------------------------------------------------
# Lifecycle + wiki_events integration tests (2026-08-24 wiki 单根裁决)
# ---------------------------------------------------------------------------
class TestPipelineLifecycleAndEvents:
    def _enqueue_due(self, tmp_db, item_id: str, stage: str) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        tmp_db.execute(
            "INSERT INTO kl_queue (item_id, stage, next_run_at) VALUES (?, ?, ?)",
            (item_id, stage, past.isoformat()),
        )

    def test_drain_advances_lifecycle_field(self, tmp_db, tmp_wiki):
        """refine 后条目写 SCHEMA.md 契约字段 lifecycle=kl:refine。"""
        result = tmp_wiki.ingest_url("https://lifecycle.example/a", title="A", text="body")
        item_id = result["id"]
        self._enqueue_due(tmp_db, item_id, "kl:refine")

        pipeline = KLPipeline(wiki_fs=tmp_wiki, db_session=tmp_db)
        res = pipeline.drain_due()
        assert res == {"done": 1, "failed": 0}

        doc = tmp_wiki.read_item(item_id)
        assert doc["fm"]["lifecycle"] == "kl:refine"

    def test_drain_full_path_to_publish(self, tmp_db, tmp_wiki):
        """raw → refine → link → structure → publish 全链路走通。"""
        result = tmp_wiki.ingest_url("https://lifecycle.example/full", title="Full", text="body")
        item_id = result["id"]
        for stage in ("kl:refine", "kl:link", "kl:structure", "kl:publish"):
            self._enqueue_due(tmp_db, item_id, stage)

        pipeline = KLPipeline(wiki_fs=tmp_wiki, db_session=tmp_db)
        res = pipeline.drain_due(limit=10)
        assert res["failed"] == 0
        assert tmp_wiki.read_item(item_id)["fm"]["lifecycle"] == "kl:publish"

    def test_drain_logs_wiki_events(self, tmp_db, tmp_wiki):
        """阶段转换在 wiki_events 表留痕 (DB=事件管理层)。"""
        from backend.repository.db import get_connection

        result = tmp_wiki.ingest_url("https://events.example/a", title="E", text="body")
        item_id = result["id"]
        self._enqueue_due(tmp_db, item_id, "kl:refine")

        pipeline = KLPipeline(wiki_fs=tmp_wiki, db_session=tmp_db)
        pipeline.drain_due()

        rows = [dict(r) for r in get_connection().execute(
            "SELECT kind, agent, payload FROM wiki_events WHERE wiki_path = ?",
            (f"items/{item_id}.md",),
        )]
        kinds = {r["kind"] for r in rows}
        assert "kl_transition" in kinds
        assert all(r["agent"] == "kl_pipeline" for r in rows)

    def test_drain_failure_logs_kl_error(self, tmp_db, tmp_wiki):
        """阶段失败留 kl_error 事件且队列记错。"""
        from backend.repository.db import get_connection

        # 不存在的 item → handler 抛 ValueError。
        self._enqueue_due(tmp_db, "ghost-item", "kl:refine")
        pipeline = KLPipeline(wiki_fs=tmp_wiki, db_session=tmp_db)
        res = pipeline.drain_due()
        assert res["failed"] == 1

        rows = [dict(r) for r in get_connection().execute(
            "SELECT kind FROM wiki_events WHERE wiki_path = ?",
            ("items/ghost-item.md",),
        )]
        assert any(r["kind"] == "kl_error" for r in rows)
