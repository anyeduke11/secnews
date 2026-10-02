"""v0.8.6 P0-4 (审计 S2): 迁移器 duplicate column 幂等语义 — 逐语句容忍重放。

S2 缺陷 (修复前): executescript 遇 "duplicate column" 整文件中止, 直接
记版本 + continue — 同文件**后续语句被静默丢弃且永久标记完成** (静默半
应用)。任何未来 "已存在列 + 后续语句" 的迁移 (如 migration 131 在历史
手工改库上的半应用) 都会踩中。

验收标准 (PRD P0-4): "已存在列+后续语句"用例后续语句生效。

构造约定: 历史库半应用状态 = 分阶段放文件 (先 apply 001, 手工补历史列,
再放 002 触发 duplicate column), 而非 apply 全部后回滚 — SQLite 无法
可靠回滚已 auto-commit 的 DDL。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.repository import db as db_mod


def _make_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_dir = tmp_path / "migrations"
    fake_dir.mkdir()
    monkeypatch.setattr(db_mod, "MIGRATIONS_DIR", fake_dir)
    return fake_dir


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _applied_versions(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()]


# ---------------------------------------------------------------------------
# 验收用例: 已存在列 + 后续语句 → 后续语句必须生效
# ---------------------------------------------------------------------------


def test_duplicate_column_subsequent_statements_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2 核心: 历史库已手工加 legacy_col 时, 同文件后续 ALTER/CREATE 必须生效。

    修复前: executescript 在第一条 ALTER 抛 duplicate column → 整文件
    标记完成, new_col/t2 永远不建 (静默半应用)。
    """
    d = _make_dir(tmp_path, monkeypatch)
    (d / "001_init.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    conn = sqlite3.connect(":memory:")
    db_mod.apply_migrations(conn)
    # 模拟历史库: 002 的第一条已被手工满足 (列已存在)
    conn.execute("ALTER TABLE t1 ADD COLUMN legacy_col INTEGER")
    # 现在才放入 002 — 首跑即触发 duplicate column
    (d / "002_legacy_half.sql").write_text(
        "-- 历史库已手工加过 legacy_col\n"
        "ALTER TABLE t1 ADD COLUMN legacy_col INTEGER;\n"
        "ALTER TABLE t1 ADD COLUMN new_col TEXT;\n"
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )

    applied = db_mod.apply_migrations(conn)

    # 后续语句生效 (S2 验收)
    assert "new_col" in _columns(conn, "t1"), "duplicate column 之后的 ALTER 被静默丢弃 (S2)"
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='t2'"
    ).fetchone()[0] == 1, "duplicate column 之后的 CREATE TABLE 被静默丢弃 (S2)"
    # 版本记录 + 返回值正确
    assert "002_legacy_half" in _applied_versions(conn)
    assert applied == 2


def test_replay_tolerates_already_exists_from_partial_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """executescript 已 auto-commit 的非幂等 DDL, 重放抛 already exists 也容忍。

    executescript 逐句执行: 第 1 条 CREATE TABLE t_new 在全新库成功提交,
    第 2 条 ALTER 抛 duplicate column → 进 tolerant 重放 → 重放第 1 条
    必然再抛 "table t_new already exists" — 必须视为已满足, 否则修复
    自己把自己卡死。
    """
    d = _make_dir(tmp_path, monkeypatch)
    (d / "001_init.sql").write_text(
        "CREATE TABLE t_old (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    conn = sqlite3.connect(":memory:")
    db_mod.apply_migrations(conn)
    conn.execute("ALTER TABLE t_old ADD COLUMN legacy_col INTEGER")  # 历史列
    (d / "002_partial.sql").write_text(
        "CREATE TABLE t_new (id INTEGER PRIMARY KEY);\n"          # executescript 已提交
        "ALTER TABLE t_old ADD COLUMN legacy_col TEXT;\n"         # 触发 duplicate
        "CREATE TABLE t_after (id INTEGER PRIMARY KEY);\n",       # 后续必须生效
        encoding="utf-8",
    )

    applied = db_mod.apply_migrations(conn)

    for table in ("t_new", "t_after"):
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0] == 1, f"{table} 未生效"
    assert "002_partial" in _applied_versions(conn)
    assert applied == 2


def test_replay_other_errors_still_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重放中非已满足类错误必须向上抛, 且版本不落账 (不冒充完成)。"""
    d = _make_dir(tmp_path, monkeypatch)
    (d / "001_init.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    conn = sqlite3.connect(":memory:")
    db_mod.apply_migrations(conn)
    conn.execute("ALTER TABLE t1 ADD COLUMN dup_col TEXT")  # 历史列
    (d / "002_bad.sql").write_text(
        "ALTER TABLE t1 ADD COLUMN dup_col TEXT;\n"   # duplicate → 进重放
        "INSERT INTO missing_table VALUES (1);\n",    # 重放中真实错误 → raise
        encoding="utf-8",
    )

    with pytest.raises(sqlite3.OperationalError):
        db_mod.apply_migrations(conn)

    assert "002_bad" not in _applied_versions(conn), "失败迁移不得落账 (冒充完成)"


def test_fresh_db_normal_path_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归: 无 duplicate column 的常规多语句迁移仍走 executescript 快路径。"""
    d = _make_dir(tmp_path, monkeypatch)
    (d / "001_ok.sql").write_text(
        "CREATE TABLE a (id INTEGER PRIMARY KEY);\n"
        "ALTER TABLE a ADD COLUMN note TEXT;\n"
        "CREATE TABLE b (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(":memory:")
    assert db_mod.apply_migrations(conn) == 1
    assert _columns(conn, "a") == ["id", "note"]
    assert "001_ok" in _applied_versions(conn)
    # 幂等: 再跑一次 no-op
    assert db_mod.apply_migrations(conn) == 1


# ---------------------------------------------------------------------------
# 切分器: trigger 安全 (migrations 有 20+ 处 CREATE TRIGGER ... BEGIN...END)
# ---------------------------------------------------------------------------


def test_split_statements_trigger_safe() -> None:
    sql = (
        "CREATE TABLE t (id INTEGER PRIMARY KEY);\n"
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n"
        "  INSERT INTO log VALUES (new.id, 'x');\n"
        "  UPDATE stats SET n = n + 1;\n"
        "END;\n"
        "CREATE INDEX IF NOT EXISTS idx_t ON t(id);\n"
    )
    stmts = db_mod._split_sql_statements(sql)
    assert len(stmts) == 3, "trigger 体 (体内含 ;) 不得被撕碎"
    assert "CREATE TRIGGER" in stmts[1]
    assert "END" in stmts[1] and "UPDATE stats" in stmts[1]
    assert "CREATE INDEX" in stmts[2]


def test_split_statements_drops_comment_only_tail() -> None:
    sql = (
        "-- 头注释\n"
        "CREATE TABLE t (id INTEGER PRIMARY KEY);\n"
        "-- 尾注释 (126 纯注释锚点同形态)\n"
    )
    stmts = db_mod._split_sql_statements(sql)
    assert len(stmts) == 1
    assert stmts[0].startswith("-- 头注释")  # 注释附着在下一条语句上, 一起执行
    assert "CREATE TABLE" in stmts[0]


def test_tolerant_replay_handles_trigger_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端到端: 含 trigger 的迁移在 duplicate column 重放中 trigger 语句完整生效。"""
    d = _make_dir(tmp_path, monkeypatch)
    (d / "001_init.sql").write_text(
        "CREATE TABLE hot (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE log (id INTEGER, tag TEXT);\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(":memory:")
    db_mod.apply_migrations(conn)
    conn.execute("ALTER TABLE hot ADD COLUMN score REAL")  # 历史列
    (d / "002_trg.sql").write_text(
        "ALTER TABLE hot ADD COLUMN score REAL;\n"  # 历史已加 → duplicate
        "CREATE TRIGGER hot_ai AFTER INSERT ON hot BEGIN\n"
        "  INSERT INTO log VALUES (new.id, 'auto');\n"
        "END;\n",
        encoding="utf-8",
    )

    db_mod.apply_migrations(conn)

    # trigger 已建且工作 (后续语句生效的最强证明 — trigger 体未被撕碎)
    conn.execute("INSERT INTO hot (id, score) VALUES (1, 0.5)")
    assert conn.execute("SELECT COUNT(*) FROM log").fetchone()[0] == 1
