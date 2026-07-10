"""DB 初始化 / 连接管理 / 迁移 单元测试

每个测试使用 tmp_path 隔离的临时 SQLite 文件，并通过 monkeypatch
重定向 ``backend.config.config.db_path``，确保不污染真实
``backend/hotspot.db``。
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """重定向 config.db_path 到 tmp_path 下的临时文件。

    测试结束后调用 close_db() 释放 thread-local 连接。
    """
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    yield test_db
    db.close_db()


def test_init_db_creates_schema(temp_db):
    """init_db 后应创建 hotspots / settings / schema_version 三张表。"""
    db.init_db()
    conn = db.get_connection()
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "hotspots" in tables
    assert "settings" in tables
    assert "schema_version" in tables


def test_init_db_creates_indexes_and_fts_triggers(temp_db):
    """init_db 后应创建热点索引 + FTS5 同步触发器。"""
    db.init_db()
    conn = db.get_connection()

    indexes = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    ]
    # 业务索引必须存在
    for expected in (
        "idx_cat_pub",
        "idx_pub",
        "idx_fallback",
        "idx_source",
    ):
        assert expected in indexes, f"missing index: {expected}"

    # FTS5 同步触发器必须存在
    triggers = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    ]
    for expected in ("hotspots_ai", "hotspots_ad", "hotspots_au"):
        assert expected in triggers, f"missing trigger: {expected}"


def test_wal_mode(temp_db):
    """PRAGMA journal_mode 应返回 wal。"""
    db.init_db()
    conn = db.get_connection()
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row is not None
    assert row[0].lower() == "wal"


def test_integrity_check_ok(temp_db):
    """init_db 内置的 integrity_check 应返回 ok。"""
    db.init_db()
    conn = db.get_connection()
    row = conn.execute("PRAGMA integrity_check").fetchone()
    assert row is not None
    assert row[0] == "ok"


def test_migration_idempotent(temp_db):
    """连续 init_db 两次不应报错，且 schema_version 不应重复增长。"""
    v1 = db.init_db()
    v2 = db.init_db()
    # 两次调用结果应一致（migration 在第二次时已全部跳过）
    assert v1 == v2
    assert v1 >= 1

    conn = db.get_connection()
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    # 每个 migration 只能被记录一次
    versions = [r[0] for r in rows]
    assert len(versions) == len(set(versions))


def test_get_connection_thread_local(temp_db):
    """同一 thread 多次 get_connection 应返回同一 conn。"""
    db.init_db()
    c1 = db.get_connection()
    c2 = db.get_connection()
    c3 = db.get_connection()
    assert c1 is c2 is c3


def test_close_db_clears_connection(temp_db):
    """close_db 后再 get_connection 应返回新 conn。"""
    db.init_db()
    first = db.get_connection()
    db.close_db()
    second = db.get_connection()
    assert first is not second
    # 新连接必须仍能正常使用
    cur = second.execute("SELECT 1").fetchone()
    assert cur is not None and cur[0] == 1


def test_get_connection_distinct_per_thread(temp_db):
    """不同 thread 应各自拿到独立的 conn（thread-local 隔离）。"""
    db.init_db()
    main_conn = db.get_connection()

    results: dict[str, sqlite3.Connection] = {}

    def worker() -> None:
        # 在子线程中获取连接并写入
        c = db.get_connection()
        results["worker"] = c
        db.close_db()

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5.0)
    assert "worker" in results
    assert results["worker"] is not main_conn
