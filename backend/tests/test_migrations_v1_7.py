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
        "personal_profile", "digests",
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


def test_078_hotspots_fts_update_removes_old_terms(temp_db):
    """078: contentless 'delete' 触发器修复 — UPDATE 后旧词条不再假阳性。

    缺陷背景: 001 的 hotspots_au 在 'delete' 命令里只给 rowid, 词条静默
    残留 (SQLite 3.53 实证不报错但不移除); 078 重建为提供旧值的写法。
    """
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
        "VALUES ('h1', '供应链投毒事件', 'src', 'https://x/1', 'security', '2026-01-01', '2026-01-01')"
    )
    conn.execute("UPDATE hotspots SET title = '勒索软件复盘' WHERE id = 'h1'")
    stale = conn.execute(
        "SELECT rowid FROM hotspots_fts WHERE hotspots_fts MATCH ?",
        ('"供应链投毒"',),
    ).fetchall()
    assert stale == []
    fresh = conn.execute(
        "SELECT rowid FROM hotspots_fts WHERE hotspots_fts MATCH ?",
        ('"勒索软件复盘"',),
    ).fetchall()
    assert fresh != []


def test_078_hotspots_fts_delete_removes_terms(temp_db):
    """078: DELETE 后词条从 hotspots_fts 消失 (旧触发器只清 rowid 不清词条)。"""
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
        "VALUES ('h1', '零日漏洞预警', 'src', 'https://x/1', 'security', '2026-01-01', '2026-01-01')"
    )
    conn.execute("DELETE FROM hotspots WHERE id = 'h1'")
    rows = conn.execute(
        "SELECT rowid FROM hotspots_fts WHERE hotspots_fts MATCH ?",
        ('"零日漏洞预警"',),
    ).fetchall()
    assert rows == []


def test_078_fts_index_rebuilt_without_stale_terms(temp_db):
    """078: 迁移内 delete-all + 全量重灌 — 存量行可检索且无重复导入。"""
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
        "VALUES ('h1', 'APT 活动追踪', 'src', 'https://x/1', 'security', '2026-01-01', '2026-01-01')"
    )
    # 迁移已应用 (078 在建库时跑), 存量重灌发生在迁移时点 — 此处手动重跑
    # 迁移的清理段, 验证幂等且行数对齐。
    conn.execute("INSERT INTO hotspots_fts(hotspots_fts) VALUES ('delete-all')")
    conn.execute(
        "INSERT INTO hotspots_fts(rowid, title, summary) "
        "SELECT rowid, title, IFNULL(summary, '') FROM hotspots"
    )
    hits = conn.execute(
        "SELECT rowid FROM hotspots_fts WHERE hotspots_fts MATCH ?",
        ('"APT 活动追踪"',),
    ).fetchall()
    assert len(hits) == 1
    n_fts = conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0]
    n_hot = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    assert n_fts == n_hot
