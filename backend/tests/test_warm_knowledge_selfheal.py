"""_ensure_warm_knowledge_items — warm 知识投影自愈回归测试 (治理 T4)。

意图锚定: 2026-09-18 warm.db 遗失 (migration 119 注释同口径) 重建后
``warm.knowledge_items`` 缺失,
所有知识写读静默抛 "no such table" → 知识入管断供 13 天。自愈必须保证
"warm 文件在、表缺失" 的库下次启动即恢复, 不再依赖手工 DDL。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db as db_module
from backend.repository.db import get_connection, knowledge_items_table


@pytest.fixture
def dual_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """main + warm 双库环境 — 复刻生产 ATTACH 拓扑 (空 warm 文件)。"""
    main_db = tmp_path / "main.db"
    warm_db = tmp_path / "warm.db"
    warm_db.write_bytes(b"")  # 空文件即可被 get_connection ATTACH
    monkeypatch.setattr(config, "db_path", main_db)
    monkeypatch.setattr(config, "warm_db_path", warm_db)
    db_module.close_db()
    yield main_db, warm_db
    db_module.close_db()


def _bootstrap_main_schema(conn) -> None:
    """在 main 建 knowledge_items 权威结构 — 直接复用 018 迁移本体
    (后续迁移在其上续跑, 自愈拷贝的 DDL 才与生产空壳一致)。"""
    sql = (db_module.MIGRATIONS_DIR / "018_knowledge.sql").read_text(encoding="utf-8")
    conn.executescript(sql)


def test_selfheal_rebuilds_missing_warm_table(dual_db):
    """warm 缺表 + main 有权威 DDL → init 后 warm 表可用且寻址解析为 warm 前缀。"""
    main_db, warm_db = dual_db
    conn = get_connection()
    _bootstrap_main_schema(conn)

    db_module.init_db()

    rebuilt = conn.execute(
        "SELECT COUNT(*) FROM warm.sqlite_master "
        "WHERE type = 'table' AND name = 'knowledge_items'"
    ).fetchone()[0]
    assert rebuilt == 1, "warm 缺表必须被 init_db 自愈重建"
    assert knowledge_items_table() == "warm.knowledge_items"

    # 重建出的表必须可写可读 (断供期间正是这一步在静默失败)
    conn.execute(
        "INSERT INTO warm.knowledge_items (id, title, source, lifecycle, ingested_at, updated_at) "
        "VALUES ('ki-1', 't', 'web', 'kl:raw', '2026-09-26T00:00:00+00:00', '2026-09-26T00:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT lifecycle FROM warm.knowledge_items WHERE id = 'ki-1'"
    ).fetchone()
    assert row["lifecycle"] == "kl:raw"


def test_selfheal_rebuilds_missing_warm_indexes(dual_db):
    """自愈不只建表 — 063 的 3 个索引必须同拷到 warm。

    2026-09-26 终审 Important: 只拷 CREATE TABLE 的话 ingested_at/lifecycle/
    domain 索引缺失, T1-T4 触发器与知识仪表盘热路径在 ~4k 行投影上退化为
    全表扫描。
    """
    main_db, warm_db = dual_db
    conn = get_connection()
    _bootstrap_main_schema(conn)

    db_module.init_db()  # apply_migrations 在 main 建全索引 (含 063) → 自愈同拷

    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM warm.sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'knowledge_items' "
            "AND sql IS NOT NULL"
        ).fetchall()
    }
    assert {"idx_ki_ingested", "idx_ki_lifecycle", "idx_ki_domain"} <= names, (
        "自愈必须把 063 的 3 个索引一并重建到 warm (≥3)"
    )

    # 索引必须真的指向 warm 表 (PLAN 用不上等于白建) — 插一行验证可写可查
    conn.execute(
        "INSERT INTO warm.knowledge_items (id, title, source, lifecycle, ingested_at, updated_at) "
        "VALUES ('ki-idx', 't', 'web', 'kl:raw', '2026-09-26T00:00:00+00:00', '2026-09-26T00:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT lifecycle FROM warm.knowledge_items WHERE lifecycle = 'kl:raw'"
    ).fetchone()
    assert row is not None


def test_selfheal_preserves_existing_warm_data(dual_db):
    """warm 表健在 → 幂等 no-op, 已有数据原样保留 (不许重建清库)。"""
    main_db, warm_db = dual_db
    conn = get_connection()
    _bootstrap_main_schema(conn)
    db_module.init_db()  # 首次: 自愈建表
    conn.execute(
        "INSERT INTO warm.knowledge_items (id, title, source, lifecycle, ingested_at, updated_at) "
        "VALUES ('keep-1', 't', 'web', 'kl:publish', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')"
    )

    db_module.init_db()  # 二次: 必须不动

    row = conn.execute(
        "SELECT lifecycle FROM warm.knowledge_items WHERE id = 'keep-1'"
    ).fetchone()
    assert row is not None, "表已存在时自愈必须 no-op, 不清数据"
    assert row["lifecycle"] == "kl:publish"


def test_no_warm_attach_keeps_bare_name(monkeypatch, tmp_path):
    """warm 文件不存在 (测试/单库模式) → 不 ATTACH, 寻址保持裸名 (现有契约)。"""
    main_db = tmp_path / "single.db"
    monkeypatch.setattr(config, "db_path", main_db)
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "absent-warm.db")
    db_module.close_db()
    try:
        db_module.init_db()
        assert knowledge_items_table() == "knowledge_items"
    finally:
        db_module.close_db()
