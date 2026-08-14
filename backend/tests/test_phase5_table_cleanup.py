"""v1.7 Phase 7 — Phase 5 表清理 + favorites.created_via 测试.

覆盖:
  - migration 038 删除 5 张 Phase 5 表 (knowledge_tasks / agent_heartbeats / ...)
  - kv_cache 表**保留** (不在删除范围)
  - migration 039 favorites.created_via 列存在 + 默认 'ui'
  - created_via CHECK 约束 (非法值降级为 'ui')
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_cleanup.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------- Migration 038 — DROP 5 张 Phase 5 表 ----------


def test_mcp_tool_registry_exists(temp_db):
    """Migration 037 — mcp_tool_registry 表存在."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_tool_registry'"
    ).fetchall()
    assert len(rows) == 1


def test_phase5_tables_dropped(temp_db):
    """Migration 038 — 5 张 Phase 5 表已删除; 058 重建了 knowledge_tasks。

    P0 收尾: 058_v1.7_recreate_knowledge_tasks.sql 重建 knowledge_tasks,
    因此该表现在存在; 其余 4 张 Phase 5 表 (agent_heartbeats /
    agent_task_skills / skill_config / mcp_tool_invocations) 保持删除。
    """
    conn = db.get_connection()
    # knowledge_tasks 已被 058 重建 → 存在
    rt = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_tasks'"
    ).fetchall()
    assert len(rt) == 1, "knowledge_tasks 已被 058 重建, 应存在"
    # 其余 4 张 Phase 5 表保持删除
    dropped = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('agent_heartbeats', 'agent_task_skills', "
        "'skill_config', 'mcp_tool_invocations')"
    ).fetchall()
    assert len(dropped) == 0, f"Phase 5 表应已删除, 实际存在: {[r[0] for r in dropped]}"


def test_kv_cache_dropped(temp_db):
    """kv_cache 表已删除 (Phase 15 迁移 051 删除)."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='kv_cache'"
    ).fetchall()
    assert len(rows) == 0, "kv_cache 表应已删除"


# ---------- Migration 039 — favorites.created_via ----------


def test_favorite_created_via_column_exists(temp_db):
    """Migration 039 — favorites.created_via 列存在."""
    conn = db.get_connection()
    cols = conn.execute("PRAGMA table_info(favorites)").fetchall()
    col_names = {c["name"] for c in cols}
    assert "created_via" in col_names


def test_favorite_default_created_via_ui():
    """未指定 created_via 时, 默认 'ui'."""
    import os
    import tempfile
    from pathlib import Path

    from backend.repository.favorite_repo import FavoriteRepository

    # 隔离 DB
    test_db = Path(tempfile.mkdtemp()) / "test_default.db"
    orig = os.environ.get("HOTSPOT_DB_PATH", "")
    os.environ["HOTSPOT_DB_PATH"] = str(test_db)
    try:
        from backend.config import config
        config.db_path = test_db
        db.close_db()
        db.init_db()

        repo = FavoriteRepository()
        created, item = repo.add(
            hotspot_id="h-1",
            category="ai",
            title="Test",
            source="src",
            url="https://example.com/h-1",
        )
        assert created is True
        assert item.created_via == "ui"
    finally:
        os.environ["HOTSPOT_DB_PATH"] = orig
        db.close_db()


def test_favorite_invalid_created_via_fallsback():
    """非法 created_via 降级为 'ui' (安全保护)."""
    import os
    import tempfile
    from pathlib import Path

    from backend.repository.favorite_repo import FavoriteRepository

    test_db = Path(tempfile.mkdtemp()) / "test_invalid.db"
    orig = os.environ.get("HOTSPOT_DB_PATH", "")
    os.environ["HOTSPOT_DB_PATH"] = str(test_db)
    try:
        from backend.config import config
        config.db_path = test_db
        db.close_db()
        db.init_db()

        repo = FavoriteRepository()
        _created, item = repo.add(
            hotspot_id="h-2",
            category="ai",
            title="Test",
            source="src",
            url="https://example.com/h-2",
            created_via="bogus-value",  # 非法
        )
        assert item.created_via == "ui"  # 降级
    finally:
        os.environ["HOTSPOT_DB_PATH"] = orig
        db.close_db()


def test_favorite_explicit_mcp():
    """显式 created_via='mcp' 走 MCP tool 路径."""
    import os
    import tempfile
    from pathlib import Path

    from backend.repository.favorite_repo import FavoriteRepository

    test_db = Path(tempfile.mkdtemp()) / "test_mcp.db"
    orig = os.environ.get("HOTSPOT_DB_PATH", "")
    os.environ["HOTSPOT_DB_PATH"] = str(test_db)
    try:
        from backend.config import config
        config.db_path = test_db
        db.close_db()
        db.init_db()

        repo = FavoriteRepository()
        _created, item = repo.add(
            hotspot_id="h-3",
            category="ai",
            title="Test",
            source="src",
            url="https://example.com/h-3",
            created_via="mcp",
        )
        assert item.created_via == "mcp"
    finally:
        os.environ["HOTSPOT_DB_PATH"] = orig
        db.close_db()
