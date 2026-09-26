"""migration 126 FK OFF 先例锚点 — 文件级防误删断言 + runner 纯注释兼容验证。

背景: 124_paper_category.sql 于 2026-09-26 22:29 生产执行时, 连接级
PRAGMA foreign_keys=ON 下 DROP TABLE hotspots 触发 hotspot_tags /
ai_scores 的 ON DELETE CASCADE, 数千行打标关联被级联清空 (终审
Critical)。修复 = 留痕 + 规约锚点, 不改已应用迁移的执行语义:

- 124 文件头必须保留事故记录 (防后来者删注释重蹈覆辙);
- 126 纯注释锚点文件必须存在且承载 FK OFF 规约;
- db.py docstring 必须含 124 事故引用 (销毁型 migration 规约);
- apply_migrations (executescript) 必须接受纯注释文件 — 若未来
  runner 改动导致纯注释迁移失败, 本测试先行报警。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.repository import db as db_mod

MIGRATIONS_DIR = Path(db_mod.__file__).resolve().parent / "migrations"


def test_126_anchor_file_exists_with_fk_off_lesson() -> None:
    """126 锚点文件存在, 且包含 FK OFF 教训关键词 (防误删/防漂移)。"""
    path = MIGRATIONS_DIR / "126_foreign_keys_off_note.sql"
    assert path.exists(), "126 FK OFF 先例锚点文件被删除 — 见 124 级联事故留痕"
    text = path.read_text(encoding="utf-8")
    assert "foreign_keys = OFF" in text or "foreign_keys=OFF" in text
    assert "112_remove_bid_data" in text, "必须引用 112 先例"
    assert "124" in text and "hotspot_tags" in text, "必须引用 124 事故"


def test_124_head_keeps_incident_record() -> None:
    """124 文件头事故记录 (2026-09-26 级联清空) 不得被移除。"""
    text = (MIGRATIONS_DIR / "124_paper_category.sql").read_text(encoding="utf-8")
    assert "事故记录" in text
    assert "2026-09-26" in text
    assert "ON DELETE CASCADE" in text
    # 执行语义保持不变: 124 的非注释行不得出现 FK PRAGMA
    # (已应用迁移, 只留痕不改语义; 头部注释引用 FK OFF 字样属正常)
    code_lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ]
    assert not any("foreign_keys" in ln.lower() for ln in code_lines)


def test_db_py_docstring_references_124_incident() -> None:
    """db.py 模块 docstring 必须含销毁型 migration FK OFF 规约 + 124 引用。"""
    doc = (db_mod.__doc__ or "")
    assert "Destructive migrations" in doc
    assert "foreign_keys=OFF" in doc
    assert "124" in doc
    assert "112_remove_bid_data" in doc


def test_runner_accepts_comment_only_migration(tmp_path: Path, monkeypatch) -> None:
    """apply_migrations/executescript 必须接受纯注释迁移文件。

    126 即纯注释形态; 若 runner 未来拒绝空语句文件, 此测试先行报警,
    避免生产启动被 126 卡死。
    """
    fake_dir = tmp_path / "migrations"
    fake_dir.mkdir()
    (fake_dir / "001_init.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    (fake_dir / "002_note.sql").write_text(
        "-- 纯注释迁移: 只承载教训, 无执行语义\n-- foreign_keys = OFF\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(db_mod, "MIGRATIONS_DIR", fake_dir)

    conn = sqlite3.connect(":memory:")
    applied = db_mod.apply_migrations(conn)
    assert applied == 2
    rows = conn.execute(
        "SELECT version FROM schema_version ORDER BY version"
    ).fetchall()
    assert [r[0] for r in rows] == ["001_init", "002_note"]
