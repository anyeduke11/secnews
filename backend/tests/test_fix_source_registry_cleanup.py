"""fix_source_registry_cleanup 脚本核心逻辑测试 (采集闭环 T2).

锁定的契约 (与 scripts/fix_source_registry_cleanup.py docstring 同源):
1. dry-run (默认, 无 --execute): 只报告变更面, 零写入
2. --execute: 删 hotspots/crawler_sources/custom_sources 测试残留
   (source/id IN ('rss','test-src')) + 僵尸注册行
   (enabled=0 AND status='unknown' AND last_success_at IS NULL)
   归档为 status='retired' + source_alerts(source_archived, P2), 不物理删
3. 幂等: 第二次 execute 零变更、告警不重复积累
4. 不匹配的行原样保留 (enabled=1 僵尸 / 曾成功源 / 相似名源)

执行:
    python -m pytest backend/tests/test_fix_source_registry_cleanup.py -v
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fix_source_registry_cleanup.py"


def _load_script():
    """以独立模块名加载脚本 (scripts/ 不在包路径, standalone 约定)。"""
    spec = importlib.util.spec_from_file_location(
        "fix_source_registry_cleanup", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path (全量 migration, 与 test_source_alerter 同模式)。"""
    test_db = tmp_path / "test_fix_cleanup.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _insert_hotspot(hid: str, source: str) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid,
            f"item {hid}",
            "",
            source,
            f"https://example.com/{hid}",
            "ai",
            datetime.now(timezone.utc).isoformat(),
            50,
            datetime.now(timezone.utc).isoformat(),
            0,
            100,
            "[]",
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _insert_crawler_source(
    sid: str,
    *,
    name: str | None = None,
    status: str = "unknown",
    enabled: int = 0,
    last_success_at: str | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, status, priority, enabled,
             last_success_at, consecutive_failures, health_score,
             created_at, updated_at)
        VALUES (?, 'ai', ?, 'html', ?, 50, ?, ?, 0, 1.0,
                datetime('now'), datetime('now'))
        """,
        (sid, name or sid, status, enabled, last_success_at),
    )


def _insert_custom_source(name: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO custom_sources (url, name, category, created_at) "
        "VALUES (?, ?, 'ai', datetime('now'))",
        (f"https://example.com/custom/{name}", name),
    )


def _counts() -> dict:
    conn = get_connection()
    return {
        "residual_hotspots": conn.execute(
            "SELECT COUNT(*) FROM hotspots WHERE source IN ('rss', 'test-src')"
        ).fetchone()[0],
        "residual_crawler": conn.execute(
            "SELECT COUNT(*) FROM crawler_sources WHERE id IN ('rss', 'test-src')"
        ).fetchone()[0],
        "residual_custom": conn.execute(
            "SELECT COUNT(*) FROM custom_sources WHERE name IN ('rss', 'test-src')"
        ).fetchone()[0],
        "zombies_unknown": conn.execute(
            "SELECT COUNT(*) FROM crawler_sources "
            "WHERE enabled = 0 AND status = 'unknown' AND last_success_at IS NULL"
        ).fetchone()[0],
        "zombies_retired": conn.execute(
            "SELECT COUNT(*) FROM crawler_sources WHERE status = 'retired'"
        ).fetchone()[0],
        "archived_alerts": conn.execute(
            "SELECT COUNT(*) FROM source_alerts WHERE alert_type = 'source_archived'"
        ).fetchone()[0],
    }


def _seed_all() -> None:
    """造全量变更面: hotspots 残留 x2 + 三表同名源 + 僵尸 x1 + 正常源。"""
    _insert_hotspot("h-rss", "rss")
    _insert_hotspot("h-test", "test-src")
    _insert_crawler_source("rss", name="rss", status="disabled")
    _insert_crawler_source("test-src", name="test-src", status="disabled")
    _insert_custom_source("rss")
    _insert_crawler_source("ai:量子位", name="量子位")  # 僵尸: 默认 unknown+enabled=0
    # 正常源: 不应被任何动作波及
    _insert_crawler_source("ai:AGI Hunt", name="AGI Hunt", status="active", enabled=1)
    _insert_crawler_source(
        "ai:曾成功", name="曾成功", last_success_at="2026-09-01T00:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# 契约测试
# ---------------------------------------------------------------------------
class TestDryRun:
    def test_default_dry_run_reports_but_never_writes(self, temp_db):
        mod = _load_script()
        _seed_all()
        before = _counts()

        rc = mod.main([])  # 无 --execute → dry-run

        assert rc == 0
        assert _counts() == before, "dry-run 不得改变任何行"


class TestExecute:
    def test_execute_applies_all_three_actions(self, temp_db):
        mod = _load_script()
        _seed_all()

        rc = mod.main(["--execute"])

        assert rc == 0
        c = _counts()
        # ① hotspots 残留删除
        assert c["residual_hotspots"] == 0
        # ② crawler_sources / custom_sources 同名残留删除
        assert c["residual_crawler"] == 0
        assert c["residual_custom"] == 0
        # ③ 僵尸归档: unknown → retired + source_archived P2 告警, 不物理删
        assert c["zombies_unknown"] == 0
        assert c["zombies_retired"] == 1
        assert c["archived_alerts"] == 1
        conn = get_connection()
        row = conn.execute(
            "SELECT enabled FROM crawler_sources WHERE id = 'ai:量子位'"
        ).fetchone()
        assert row["enabled"] == 0, "归档语义: enabled 保持 0"
        alert = conn.execute(
            "SELECT level, source_id FROM source_alerts "
            "WHERE alert_type = 'source_archived'"
        ).fetchone()
        assert (alert["level"], alert["source_id"]) == ("P2", "ai:量子位")

    def test_non_matching_rows_untouched(self, temp_db):
        mod = _load_script()
        _seed_all()
        mod.main(["--execute"])

        conn = get_connection()
        # 正常 active 源不被动
        assert conn.execute(
            "SELECT status FROM crawler_sources WHERE id = 'ai:AGI Hunt'"
        ).fetchone()[0] == "active"
        # enabled=0 + unknown 但曾成功 → 有 last_success_at, 不归档
        assert conn.execute(
            "SELECT status FROM crawler_sources WHERE id = 'ai:曾成功'"
        ).fetchone()[0] == "unknown"


class TestIdempotency:
    def test_second_execute_is_zero_change(self, temp_db):
        mod = _load_script()
        _seed_all()
        mod.main(["--execute"])
        after_first = _counts()

        rc = mod.main(["--execute"])

        assert rc == 0
        assert _counts() == after_first, "重复执行必须零变更"
        assert after_first["archived_alerts"] == 1, "告警不重复积累"

    def test_clean_db_is_noop(self, temp_db):
        mod = _load_script()
        rc = mod.main(["--execute"])
        assert rc == 0
        assert _counts()["residual_hotspots"] == 0
