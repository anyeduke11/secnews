"""P0.1: quality_check_logs 归档机制单元测试。

测试意图 (Rule 9):
- 归档后主表行数应减少
- 归档表应保留被移除的行
- 7 天保留窗口内的日志应保留在主表
- 重复执行归档应幂等（不重复归档）
- VACUUM 后 DB 文件应缩小
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services.maintenance_service import archive_quality_logs, cleanup_quality_logs


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "quality_archive.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


def _insert_log(item_id: str, days_ago: int, passed: bool = True) -> None:
    """插入一条 quality_check_logs 记录, days_ago 天前。"""
    conn = db.get_connection()
    checked_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn.execute(
        "INSERT INTO quality_check_logs "
        "(item_id, gate_name, passed, score_deduction, flags, reason, "
        "error_msg, checked_at, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, "test_gate", 1 if passed else 0, 0, "[]", "test", None, checked_at, "loose"),
    )


def test_archive_table_created(temp_db):
    """归档表应在 migration 后存在。"""
    conn = db.get_connection()
    # 059 migration 应创建 quality_check_logs_archive
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='quality_check_logs_archive'"
    ).fetchall()
    assert len(rows) == 1, "quality_check_logs_archive 表应存在"


def test_archive_moves_old_logs(temp_db):
    """归档后: 超过保留窗口的日志应从主表移到归档表。"""
    # 插入: 3 条 10 天前 (应归档), 2 条 3 天前 (应保留)
    for i in range(3):
        _insert_log(f"old_{i}", days_ago=10)
    for i in range(2):
        _insert_log(f"new_{i}", days_ago=3)

    conn = db.get_connection()
    before_main = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    assert before_main == 5

    # 执行归档 (保留 7 天)
    result = archive_quality_logs(days=7, dry_run=False)

    after_main = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    archived = conn.execute("SELECT COUNT(*) FROM quality_check_logs_archive").fetchone()[0]

    assert after_main == 2, f"主表应剩 2 条, 实际 {after_main}"
    assert archived == 3, f"归档表应有 3 条, 实际 {archived}"
    assert result["rows_archived"] == 3


def test_archive_keeps_recent_logs(temp_db):
    """7 天内的日志不应被归档。"""
    _insert_log("recent_1", days_ago=1)
    _insert_log("recent_2", days_ago=6)

    result = archive_quality_logs(days=7, dry_run=False)

    conn = db.get_connection()
    main_count = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    assert main_count == 2, "7 天内的日志不应被归档"
    assert result["rows_archived"] == 0


def test_archive_is_idempotent(temp_db):
    """重复执行归档不应重复移动已归档的行。"""
    _insert_log("old_1", days_ago=10)
    _insert_log("old_2", days_ago=15)

    first = archive_quality_logs(days=7, dry_run=False)
    second = archive_quality_logs(days=7, dry_run=False)

    assert first["rows_archived"] == 2
    assert second["rows_archived"] == 0, "第二次归档不应有新行被移动"

    conn = db.get_connection()
    archived = conn.execute("SELECT COUNT(*) FROM quality_check_logs_archive").fetchone()[0]
    assert archived == 2


def test_archive_dry_run_does_not_move(temp_db):
    """dry_run=True 时不应实际移动数据。"""
    _insert_log("old_1", days_ago=10)

    result = archive_quality_logs(days=7, dry_run=True)

    conn = db.get_connection()
    main_count = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    archived_count = conn.execute("SELECT COUNT(*) FROM quality_check_logs_archive").fetchone()[0]

    assert main_count == 1, "dry_run 不应从主表删除"
    assert archived_count == 0, "dry_run 不应写入归档表"
    assert result["dry_run"] is True
    assert result["rows_to_archive"] == 1


def test_archive_preserves_data_integrity(temp_db):
    """归档后的数据应与原数据一致。"""
    _insert_log("old_1", days_ago=10)

    archive_quality_logs(days=7, dry_run=False)

    conn = db.get_connection()
    archived_row = conn.execute(
        "SELECT item_id, gate_name, passed, reason FROM quality_check_logs_archive WHERE item_id = ?",
        ("old_1",),
    ).fetchone()

    assert archived_row is not None
    assert archived_row["item_id"] == "old_1"
    assert archived_row["gate_name"] == "test_gate"
    assert archived_row["passed"] == 1
    assert archived_row["reason"] == "test"


def test_cleanup_quality_logs_uses_archive(temp_db):
    """cleanup_quality_logs 应先归档再删除 (而非直接 DELETE)。"""
    _insert_log("old_1", days_ago=30)
    _insert_log("old_2", days_ago=40)

    result = cleanup_quality_logs(days=7, dry_run=False)

    conn = db.get_connection()
    archived = conn.execute("SELECT COUNT(*) FROM quality_check_logs_archive").fetchone()[0]
    main = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]

    assert archived == 2, "老数据应先归档"
    assert main == 0, "主表应清空"
    assert result["rows_archived"] == 2
