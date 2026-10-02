"""_ensure_warm_indexes 单测 — v0.8.6 P0-2 / 审计 E19。

E19 根因: migration 063 裸名 CREATE INDEX 恒解析 main — 生产 knowledge_items
在 warm (4,348 行) 而索引建在 main 空壳表上, 热路径全表扫描。本测试锁定:
1. warm ATTACH 且有表 → 3 索引建于 warm 且查询计划 SCAN → SEARCH
2. 幂等 (重复 init 不炸不重建)
3. warm 未 ATTACH / 无表 → no-op
4. main 同名索引保留 (单库模式依赖)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.repository import db as db_mod


@pytest.fixture
def warm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离环境: main + warm 双库, warm 有带数据的 knowledge_items。"""
    main_db = tmp_path / "hotspot.db"
    warm_db = tmp_path / "hotspot-warm.db"

    # warm 库预置带数据的 knowledge_items (模拟生产投影)
    w = sqlite3.connect(warm_db)
    w.execute(
        "CREATE TABLE knowledge_items ("
        " id TEXT PRIMARY KEY, domain TEXT, lifecycle TEXT,"
        " ingested_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    w.executemany(
        "INSERT INTO knowledge_items VALUES (?,?,?,?,?)",
        [
            (f"i{n}", "security" if n % 3 else "ai",
             "kl:publish" if n % 2 else "kl:raw",
             f"2026-09-{(n % 28) + 1:02d}T00:00:00Z", "2026-10-01T00:00:00Z")
            for n in range(200)
        ],
    )
    w.commit()
    w.close()
    return main_db, warm_db


def _attached_conn(main_db: Path, warm_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(main_db)
    conn.execute(f"ATTACH DATABASE '{warm_db}' AS warm")
    return conn


class TestEnsureWarmIndexes:
    def test_indexes_created_on_warm_and_plan_searches(self, warm_env):
        """索引建于 warm (非 main), lifecycle 查询计划 SCAN → SEARCH。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            db_mod._ensure_warm_indexes(conn)

            idx = {
                r[0] for r in conn.execute(
                    "SELECT name FROM warm.sqlite_master WHERE type='index'"
                ).fetchall()
            }
            assert {"idx_ki_ingested", "idx_ki_lifecycle", "idx_ki_domain"} <= idx

            # 审计 E19 验收: EXPLAIN QUERY PLAN 由 SCAN 变 SEARCH
            plan = " ".join(
                r[3] for r in conn.execute(
                    "EXPLAIN QUERY PLAN SELECT id FROM warm.knowledge_items"
                    " WHERE lifecycle = 'kl:publish'"
                ).fetchall()
            )
            assert "SEARCH" in plan and "SCAN" not in plan, plan
        finally:
            conn.close()

    def test_idempotent_rerun(self, warm_env):
        """重复调用 no-op (IF NOT EXISTS) — 启动每轮 init 都跑, 不得炸。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            db_mod._ensure_warm_indexes(conn)
            before = conn.execute(
                "SELECT COUNT(*) FROM warm.sqlite_master WHERE type='index'"
            ).fetchone()[0]
            db_mod._ensure_warm_indexes(conn)
            after = conn.execute(
                "SELECT COUNT(*) FROM warm.sqlite_master WHERE type='index'"
            ).fetchone()[0]
            assert before == after
        finally:
            conn.close()

    def test_noop_when_warm_not_attached(self, tmp_path: Path):
        """单库模式 (测试环境常态): 无 warm ATTACH → 直接 no-op 不抛。"""
        conn = sqlite3.connect(tmp_path / "single.db")
        try:
            db_mod._ensure_warm_indexes(conn)  # 不应抛
        finally:
            conn.close()

    def test_noop_when_warm_table_missing(self, tmp_path: Path):
        """warm ATTACH 但无 knowledge_items 表 (新 warm 文件) → no-op。"""
        conn = sqlite3.connect(tmp_path / "main.db")
        warm_empty = tmp_path / "warm-empty.db"
        sqlite3.connect(warm_empty).close()  # 0 字节 → ATTACH 后无表
        conn.execute(f"ATTACH DATABASE '{warm_empty}' AS warm")
        try:
            db_mod._ensure_warm_indexes(conn)  # 不应抛
            idx = conn.execute(
                "SELECT COUNT(*) FROM warm.sqlite_master WHERE type='index'"
            ).fetchone()[0]
            assert idx == 0
        finally:
            conn.close()

    def test_main_indexes_preserved(self, warm_env):
        """main 上的 063 同名索引保留 — 单库模式 (无 warm) 下 main 是真实表。

        修 E19 不等于删 main 索引: 模拟单库 init (无 ATTACH) 跑 063 等价 DDL
        + ensure, 断言 main 索引仍在且可用。
        """
        main_db, _ = warm_env
        conn = sqlite3.connect(main_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS knowledge_items ("
                         " id TEXT PRIMARY KEY, domain TEXT, lifecycle TEXT,"
                         " ingested_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ki_lifecycle"
                         " ON knowledge_items(lifecycle)")
            db_mod._ensure_warm_indexes(conn)  # 无 warm → no-op, 不得动 main
            idx = {
                r[0] for r in conn.execute(
                    "SELECT name FROM main.sqlite_master WHERE type='index'"
                ).fetchall()
            }
            assert "idx_ki_lifecycle" in idx
        finally:
            conn.close()
