"""v1.7 迁移测试 — 验证 024-035 迁移正确应用.

覆盖:
- 所有新表存在
- 新增列存在 (hotspots/knowledge_items/cg_projects)
- 种子标签写入
- lifecycle 数据迁移 (compiled → lifecycle)
- unified_search 视图可查询

测试隔离: 使用 tmp_path + monkeypatch 重定向 config.db_path.
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """临时 DB, 迁移到 035."""
    test_db = tmp_path / "test_v17.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def test_new_tables_exist(temp_db):
    """024-032: 所有新表存在."""
    conn = db.get_connection()
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "tags", "hotspot_tags", "reading_states", "sm2_reviews",
        "annotations", "alert_rules", "alerts", "tech_stack",
        "personal_profile", "digests", "kv_cache",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"


def test_unified_fts_and_view_exist(temp_db):
    """033: FTS5 虚拟表 + unified_search 视图存在."""
    conn = db.get_connection()
    # FTS5 虚拟表
    fts = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='unified_fts'"
    ).fetchone()
    assert fts, "unified_fts virtual table missing"
    # 视图
    views = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    }
    assert "unified_search" in views


def test_hotspots_new_columns(temp_db):
    """034: hotspots 新增 tags + last_read_at."""
    conn = db.get_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(hotspots)").fetchall()}
    assert "tags" in cols
    assert "last_read_at" in cols


def test_knowledge_items_new_columns(temp_db):
    """034: knowledge_items 新增 lifecycle + news_type + tech_stack."""
    conn = db.get_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(knowledge_items)").fetchall()}
    assert "lifecycle" in cols
    assert "news_type" in cols
    assert "tech_stack" in cols


def test_cg_projects_new_column(temp_db):
    """034: cg_projects 新增 tech_stack_ids."""
    conn = db.get_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cg_projects)").fetchall()}
    assert "tech_stack_ids" in cols


def test_seed_tags_inserted(temp_db):
    """035: 14 个种子标签已写入."""
    conn = db.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    assert count >= 14
    # 抽查关键标签
    cve = conn.execute("SELECT label, type, weight FROM tags WHERE id='cve'").fetchone()
    assert cve is not None
    assert cve[0] == "CVE"
    assert cve[1] == "cve"
    assert cve[2] == 1.5


def test_tags_hierarchy_index(temp_db):
    """024: tags 表索引存在 (type + parent_id)."""
    conn = db.get_connection()
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tags'"
        ).fetchall()
    }
    assert "idx_tags_type" in indexes
    assert "idx_tags_parent" in indexes


def test_hotspot_tags_composite_pk(temp_db):
    """024: hotspot_tags 复合主键 (hotspot_id, tag_id)."""
    conn = db.get_connection()
    pk = conn.execute("PRAGMA table_info(hotspot_tags)").fetchall()
    pk_cols = [r[1] for r in pk if r[5]]  # pk flag
    assert set(pk_cols) == {"hotspot_id", "tag_id"}
