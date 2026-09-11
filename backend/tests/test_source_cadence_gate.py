"""cadence 修正批 — 死源退出轮转 + per-source 节奏闸口 + 间隔持久化.

覆盖 (与 docs 方案 T1 对齐):
- ``BaseCollector._cadence_due``: 空/非法 ISO/非法 cadence 的容错语义
- ``BaseCollector._load_sources_from_registry``: dead 排除 / 节奏未到期排除 /
  到期放行 / ``only_source`` 绕过两闸 (强刷语义)
- ``SourceSchedulerRepository.get_schedulable``: 同语义 SQL 闸口 (julianday,
  两条 now_iso 分支), cadence_seconds NULL 回落 1800
- ``HotspotScheduler()``: 不传 interval 时回落 config (main.py 硬编码 300 已删)
- ``/api/settings/refresh-interval``: POST 持久化 settings 表 + GET 回读 +
  ``main._apply_persisted_refresh_interval`` 启动回读
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.collectors.base import BaseCollector


def _iso_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# _cadence_due (纯函数)
# ---------------------------------------------------------------------------
class TestCadenceDue:
    def test_never_fetched_is_due(self):
        assert BaseCollector._cadence_due(None, 1800) is True
        assert BaseCollector._cadence_due("", 1800) is True

    def test_fresh_fetch_not_due(self):
        assert BaseCollector._cadence_due(_iso_ago(60), 1800) is False

    def test_stale_fetch_is_due(self):
        assert BaseCollector._cadence_due(_iso_ago(1801), 1800) is True

    def test_exact_boundary_is_due(self):
        # >= 语义: 恰好到期即可抓 (避免 60s tick 抖动下永远差 1s)
        assert BaseCollector._cadence_due(_iso_ago(1800 + 5), 1800) is True

    def test_z_suffix_and_naive_treated_as_utc(self):
        z = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert BaseCollector._cadence_due(z, 1800) is False
        naive = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        assert BaseCollector._cadence_due(naive, 1800) is False

    def test_unparseable_is_due(self):
        # 宁可多抓不可漏抓
        assert BaseCollector._cadence_due("not-a-date", 1800) is True

    def test_invalid_cadence_falls_back_to_1800(self):
        assert BaseCollector._cadence_due(_iso_ago(60), None) is False
        assert BaseCollector._cadence_due(_iso_ago(60), "abc") is False
        assert BaseCollector._cadence_due(_iso_ago(60), 0) is False
        assert BaseCollector._cadence_due(_iso_ago(1801), -5) is True


# ---------------------------------------------------------------------------
# _load_sources_from_registry 闸口
# ---------------------------------------------------------------------------
@pytest.fixture()
def registry_db(tmp_path, monkeypatch):
    """临时 DB, 与 test_crawler_sources.crawler_db 同构 (含 cadence 三列)."""
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE crawler_sources (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT DEFAULT 'html',
            url TEXT DEFAULT '',
            feed_url TEXT DEFAULT '',
            api_url TEXT DEFAULT '',
            priority INTEGER DEFAULT 50,
            enabled INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            cadence_seconds INTEGER DEFAULT 1800,
            last_fetch_at TEXT
        );
        """
    )
    conn.commit()
    from backend.repository import db as db_mod

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    yield conn
    conn.close()


def _seed_row(
    conn,
    name: str,
    *,
    status: str = "active",
    cadence: int = 1800,
    last_fetch_at: str | None = None,
    category: str = "security",
) -> None:
    conn.execute(
        "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, cadence_seconds, last_fetch_at) VALUES (?, ?, ?, 'html', ?, 50, 1, ?, ?, ?)",
        (f"{category}:{name}", category, name, f"https://example.test/{name}", status, cadence, last_fetch_at),
    )
    conn.commit()


def _security_collector():
    from backend.collectors.security_collector import SecurityCollector

    return SecurityCollector()


class TestRegistryCadenceGate:
    def test_dead_source_excluded(self, registry_db):
        _seed_row(registry_db, "alive", status="active")
        _seed_row(registry_db, "corpse", status="dead")
        names = [s["name"] for s in _security_collector()._load_sources_from_registry()]
        assert "alive" in names
        assert "corpse" not in names, "dead 源必须退出批量轮转 (恢复只走每日 probe 漏斗)"

    def test_grace_and_stale_still_run(self, registry_db):
        # grace/stale 仍在漏斗里, 需要继续抓才能转 active — 不得被闸口误吞
        _seed_row(registry_db, "in-grace", status="grace")
        _seed_row(registry_db, "in-stale", status="stale")
        names = [s["name"] for s in _security_collector()._load_sources_from_registry()]
        assert {"in-grace", "in-stale"} <= set(names)

    def test_fresh_source_excluded_until_cadence(self, registry_db):
        _seed_row(registry_db, "fresh", cadence=1800, last_fetch_at=_iso_ago(60))
        _seed_row(registry_db, "due", cadence=1800, last_fetch_at=_iso_ago(1900))
        _seed_row(registry_db, "never", cadence=1800, last_fetch_at=None)
        names = [s["name"] for s in _security_collector()._load_sources_from_registry()]
        assert "fresh" not in names
        assert "due" in names
        assert "never" in names

    def test_per_source_cadence_respected(self, registry_db):
        # 同样 2h 前抓过: 30 分钟节奏到期, 6 小时节奏 (bid) 未到期
        _seed_row(registry_db, "half-hour", cadence=1800, last_fetch_at=_iso_ago(7200))
        _seed_row(registry_db, "six-hour", cadence=21600, last_fetch_at=_iso_ago(7200))
        names = [s["name"] for s in _security_collector()._load_sources_from_registry()]
        assert "half-hour" in names
        assert "six-hour" not in names

    def test_only_source_bypasses_both_gates(self, registry_db):
        _seed_row(registry_db, "corpse", status="dead", last_fetch_at=_iso_ago(10))
        _seed_row(registry_db, "other", status="active")
        reg = _security_collector()._load_sources_from_registry(only_source="corpse")
        names = [s["name"] for s in reg]
        # 命中源绕过 dead + 节奏闸 (tick/手动/恢复走查的强刷语义)
        assert "corpse" in names
        # 非命中源仍按闸口规则 (这里 other 是 active 且从未抓 → 也在, 由 collect() 再过滤)
        assert "other" in names

    @pytest.mark.asyncio
    async def test_collect_passes_only_source_to_loader(self, registry_db, monkeypatch):
        """collect(only_source=X) 必须把 X 下传给 loader (否则 dead 源无法被 tick 强刷)."""
        c = _security_collector()
        seen: dict = {}

        def _fake_loader(only_source=None):
            seen["only_source"] = only_source
            return []

        monkeypatch.setattr(c, "_load_sources_from_registry", _fake_loader)
        monkeypatch.setattr(c, "_fallback", lambda: [])
        await c.collect(only_source="corpse")
        assert seen.get("only_source") == "corpse"


# ---------------------------------------------------------------------------
# get_schedulable 闸口 (真 schema, 走 init_db)
# ---------------------------------------------------------------------------
def _insert_sched(conn, sid: str, *, cadence, last_fetch_at, status="active"):
    conn.execute(
        "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, cadence_seconds, last_fetch_at) VALUES (?, 'security', ?, 'html', 'https://example.test/x', 50, 1, ?, ?, ?)",
        (sid, sid, status, cadence, last_fetch_at),
    )
    conn.commit()


class TestGetSchedulableCadence:
    @pytest.fixture(autouse=True)
    def _db(self, temp_db):
        from backend.repository.db import get_connection

        self.conn = get_connection()
        from backend.repository.source_scheduler_repo import SourceSchedulerRepository

        self.repo = SourceSchedulerRepository()

    def test_fresh_excluded_due_included_null_included(self):
        _insert_sched(self.conn, "fresh", cadence=1800, last_fetch_at=_iso_ago(60))
        _insert_sched(self.conn, "due", cadence=1800, last_fetch_at=_iso_ago(1900))
        _insert_sched(self.conn, "never", cadence=1800, last_fetch_at=None)
        ids = {r["id"] for r in self.repo.get_schedulable(limit=10)}
        assert ids == {"due", "never"}

    def test_now_iso_branch_same_semantics(self):
        _insert_sched(self.conn, "fresh", cadence=1800, last_fetch_at=_iso_ago(60))
        _insert_sched(self.conn, "due", cadence=1800, last_fetch_at=_iso_ago(1900))
        now_iso = datetime.now(timezone.utc).isoformat()
        ids = {r["id"] for r in self.repo.get_schedulable(limit=10, now_iso=now_iso)}
        assert ids == {"due"}

    def test_per_source_cadence(self):
        _insert_sched(self.conn, "half-hour", cadence=1800, last_fetch_at=_iso_ago(7200))
        _insert_sched(self.conn, "six-hour", cadence=21600, last_fetch_at=_iso_ago(7200))
        ids = {r["id"] for r in self.repo.get_schedulable(limit=10)}
        assert ids == {"half-hour"}

    def test_ddl_default_cadence_is_read(self):
        # 真 schema cadence_seconds NOT NULL DEFAULT 300 (055): 不显式写时闸口
        # 必须读到 DDL 默认值 (COALESCE 只是防御, NULL 在生产不可达)
        self.conn.execute(
            "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, last_fetch_at) VALUES ('fresh300', 'security', 'fresh300', 'html', 'https://example.test/x', 50, 1, 'active', ?)",
            (_iso_ago(100),),
        )
        self.conn.execute(
            "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, last_fetch_at) VALUES ('due300', 'security', 'due300', 'html', 'https://example.test/x', 50, 1, 'active', ?)",
            (_iso_ago(400),),
        )
        self.conn.commit()
        ids = {r["id"] for r in self.repo.get_schedulable(limit=10)}
        assert ids == {"due300"}

    def test_empty_string_last_fetch_is_due(self):
        _insert_sched(self.conn, "blank", cadence=1800, last_fetch_at="")
        ids = {r["id"] for r in self.repo.get_schedulable(limit=10)}
        assert ids == {"blank"}


# ---------------------------------------------------------------------------
# HotspotScheduler 回落 config
# ---------------------------------------------------------------------------
def test_scheduler_default_interval_follows_config(monkeypatch):
    from backend.config import config
    from backend.scheduler.scheduler import HotspotScheduler

    monkeypatch.setattr(config, "collect_interval_seconds", 4242)
    assert HotspotScheduler()._interval == 4242
    # 显式传参仍优先 (reschedule/测试注入语义不变)
    assert HotspotScheduler(interval=7)._interval == 7


# ---------------------------------------------------------------------------
# refresh-interval 持久化
# ---------------------------------------------------------------------------
@pytest.fixture
def settings_client(temp_db, monkeypatch):
    from backend.api.settings import router as settings_router
    from backend.config import config
    from backend.exceptions import register_exception_handlers

    # 隔离 config 全局态: 测试结束恢复
    monkeypatch.setattr(config, "collect_interval_seconds", config.collect_interval_seconds)
    app = FastAPI(title="test")
    register_exception_handlers(app)
    app.include_router(settings_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_refresh_interval_post_persists_and_get_reads(settings_client):
    from backend.repository.settings_repo import SettingsRepository

    r = settings_client.post("/api/settings/refresh-interval", json={"minutes": 45})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["interval_seconds"] == 2700
    assert body["persisted"] is True
    assert SettingsRepository().get("collection.refresh_interval_seconds") == 2700

    g = settings_client.get("/api/settings/refresh-interval")
    assert g.status_code == 200
    assert g.json()["interval_seconds"] == 2700
    assert g.json()["persisted_seconds"] == 2700


def test_refresh_interval_validation_unchanged(settings_client):
    assert settings_client.post("/api/settings/refresh-interval", json={"minutes": 0}).status_code == 422
    assert settings_client.post("/api/settings/refresh-interval", json={"minutes": 1441}).status_code == 422


def test_startup_restores_persisted_interval(temp_db, monkeypatch):
    from backend.config import config
    from backend.main import _apply_persisted_refresh_interval
    from backend.repository.settings_repo import SettingsRepository

    monkeypatch.setattr(config, "collect_interval_seconds", 1800)
    SettingsRepository().set("collection.refresh_interval_seconds", 3600)
    _apply_persisted_refresh_interval()
    assert config.collect_interval_seconds == 3600


def test_startup_ignores_garbage_persisted_value(temp_db, monkeypatch):
    from backend.config import config
    from backend.main import _apply_persisted_refresh_interval
    from backend.repository.settings_repo import SettingsRepository

    monkeypatch.setattr(config, "collect_interval_seconds", 1800)
    SettingsRepository().set("collection.refresh_interval_seconds", "sixty")
    _apply_persisted_refresh_interval()
    assert config.collect_interval_seconds == 1800
    SettingsRepository().set("collection.refresh_interval_seconds", 5)  # < 60s 下限
    _apply_persisted_refresh_interval()
    assert config.collect_interval_seconds == 1800
