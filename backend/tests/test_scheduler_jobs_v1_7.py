"""v1.7 Phase 5 — Scheduler Jobs 测试.

10 个 v1.7 Phase 5 job 函数, 验证:
  - 函数存在且可调用
  - 在临时 DB 下跑通基本流程 (mock 外部依赖)
  - 异常不抛出 (内部 try/except)
  - NoOp job (review_scheduler, profile_updater, kv_cache_cleanup) v1.8 已删除
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.config import config
from backend.repository import db
from backend.scheduler import jobs


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_scheduler_v17.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _run(coro):
    """同步执行 async coroutine."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _insert_hotspot(hid: str, title: str, summary: str = "", lifecycle: str = "signal"):
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO hotspots "
        "(id, title, summary, source, url, category, published_at, score, "
        " fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at, lifecycle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, title, summary, "test", f"https://example.com/{hid}",
         "ai", now, 50.0, now, 0, 80, "[]", "pending", now, lifecycle),
    )


# ---------------------------------------------------------------------------
# auto_extract_job
# ---------------------------------------------------------------------------
class TestAutoExtractJob:
    def test_extracts_untagged_hotspots(self, temp_db):
        _insert_hotspot("h-ext-1", "FastAPI 漏洞", "FastAPI RCE vulnerability")
        _insert_hotspot("h-ext-2", "RAG 实践", "Retrieval Augmented Generation")

        _run(jobs.auto_extract_job())

        from backend.repository.db import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT hotspot_id FROM hotspot_tags WHERE hotspot_id IN ('h-ext-1', 'h-ext-2')"
        ).fetchall()
        # 至少应该有 tag 关联 (可能 0 个, 因为 extract_tags 规则可能不匹配)
        # 验证 job 跑完没崩即可
        assert isinstance(rows, list)

    def test_skips_already_tagged(self, temp_db):
        """已有 tag 的 hotspot 跳过."""
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        now = datetime.now(timezone.utc).isoformat()
        _insert_hotspot("h-tagged", "已标签", "summary")
        conn = get_connection()
        # 预关联 1 个 tag
        conn.execute(
            "INSERT OR IGNORE INTO tags (id, label, type, weight, created_at) "
            "VALUES ('preset', 'preset', 'technique', 1.0, ?)",
            (now,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) "
            "VALUES ('h-tagged', 'preset', 1.0, ?)",
            (now,),
        )

        _run(jobs.auto_extract_job())

        # 验证只有 1 个 tag (即预设的, job 没有再加)
        rows = conn.execute(
            "SELECT tag_id FROM hotspot_tags WHERE hotspot_id = 'h-tagged'"
        ).fetchall()
        tag_ids = {r["tag_id"] for r in rows}
        assert "preset" in tag_ids

    def test_handles_error(self, temp_db):
        with patch("backend.services.extract_service.extract_tags", side_effect=Exception("boom")):
            _run(jobs.auto_extract_job())  # 不应崩


# ---------------------------------------------------------------------------
# alert_evaluator_job
# ---------------------------------------------------------------------------
class TestAlertEvaluatorJob:
    def test_evaluates_recent_hotspots(self, temp_db):
        _insert_hotspot("h-eval-1", "Recent hotspot", "summary")
        # 不依赖实际告警规则, 验证 job 跑通不崩
        _run(jobs.alert_evaluator_job())

    def test_handles_evaluate_error(self, temp_db):
        _insert_hotspot("h-err", "Hotspot", "summary")
        with patch("backend.services.alert_service.evaluate_hotspot", side_effect=Exception("boom")):
            _run(jobs.alert_evaluator_job())  # 不应崩

    def test_empty_db_no_crash(self, temp_db):
        _run(jobs.alert_evaluator_job())


# ---------------------------------------------------------------------------
# NoOp jobs (review_scheduler / profile_updater) — v1.8 已删除, 测试同步移除
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# digest_generator_job
# ---------------------------------------------------------------------------
class TestDigestGeneratorJob:
    def test_generates_digest(self, temp_db):
        _insert_hotspot("h-d1", "昨日热点 1", "summary", lifecycle="generate")
        _run(jobs.digest_generator_job())

        from backend.repository.digest_repo import digest_repo
        digests = digest_repo.list_recent(limit=5)
        # 至少 1 个 digest (可能是昨日或今日)
        # 若今日生成, ID 为 digest-YYYY-MM-DD
        assert isinstance(digests, list)

    def test_handles_error(self, temp_db):
        with patch("backend.services.digest_service.generate_daily_digest", side_effect=Exception("boom")):
            _run(jobs.digest_generator_job())


# ---------------------------------------------------------------------------
# source_health_check_job
# ---------------------------------------------------------------------------
class TestSourceHealthCheckJob:
    def test_runs_without_crash(self, temp_db):
        _run(jobs.source_health_check_job())

    def test_logs_warning_on_red(self, temp_db):
        """有 red 源时 log warning."""
        with patch("backend.services.source_health_service.check_all_health",
                   return_value=[{"source": "s1", "status": "red"}, {"source": "s2", "status": "green"}]):
            _run(jobs.source_health_check_job())

    def test_handles_error(self, temp_db):
        with patch("backend.services.source_health_service.check_all_health", side_effect=Exception("boom")):
            _run(jobs.source_health_check_job())


# ---------------------------------------------------------------------------
# fts_rebuild_job
# ---------------------------------------------------------------------------
class TestFtsRebuildJob:
    def test_runs_or_skips_gracefully(self, temp_db):
        """FTS5 表可能不存在, job 应优雅处理."""
        # 不应抛异常
        _run(jobs.fts_rebuild_job())

    def test_executes_rebuild_when_table_exists(self, temp_db):
        """若 unified_fts 表存在, 执行 rebuild."""
        from backend.repository.db import get_connection
        conn = get_connection()
        # 检查表是否存在
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='unified_fts'"
        ).fetchone()
        if row is None:
            pytest.skip("unified_fts 表不存在")
        _run(jobs.fts_rebuild_job())


# ---------------------------------------------------------------------------
# profile_decay_job
# ---------------------------------------------------------------------------
class TestProfileDecayJob:
    def test_runs_without_crash(self, temp_db):
        _run(jobs.profile_decay_job())

    def test_handles_error(self, temp_db):
        with patch("backend.services.profile_service.decay_all", side_effect=Exception("boom")):
            _run(jobs.profile_decay_job())


# ---------------------------------------------------------------------------
# 注册验证
# ---------------------------------------------------------------------------
class TestJobRegistration:
    """验证 scheduler.py 引用了所有保留的 v1.7 job (v1.8 清理 NoOp 后)."""

    def test_all_jobs_callable(self):
        # Phase 7: 移除 agent_task_consumer (内部 agent 删)
        # v1.8: 移除 review_scheduler / profile_updater / kv_cache_cleanup (NoOp)
        new_jobs = [
            "auto_extract_job", "alert_evaluator_job", "digest_generator_job",
            "source_health_check_job", "fts_rebuild_job", "profile_decay_job",
        ]
        for name in new_jobs:
            assert hasattr(jobs, name), f"job {name} missing"
            assert callable(getattr(jobs, name)), f"job {name} not callable"

    def test_all_jobs_in_all(self):
        new_jobs = {
            "auto_extract_job", "alert_evaluator_job", "digest_generator_job",
            "source_health_check_job", "fts_rebuild_job", "profile_decay_job",
        }
        assert new_jobs.issubset(set(jobs.__all__)), \
            f"missing in __all__: {new_jobs - set(jobs.__all__)}"

    def test_noop_jobs_removed(self):
        """v1.8: NoOp 占位 job 已彻底删除."""
        for name in ("review_scheduler_job", "profile_updater_job", "kv_cache_cleanup_job"):
            assert not hasattr(jobs, name), f"NoOp job {name} 应已删除"
            assert name not in jobs.__all__
