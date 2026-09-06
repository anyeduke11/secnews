"""v1.0 T09 F01 修复 — LegacyHoldService 测试 (53 pending → legacy_hold).

覆盖 (对应 V0.8.3_CRITICAL_REVIEW §F01 + EXECUTION_GUIDE §4 T09 通过证据):
  1. 53 pending → legacy_hold (主路径)
  2. 幂等: 重复跑不重复标
  3. audit_log 落库正确 (actor / action / target / detail)
  4. 非 pending 票据不动 (running/done/failed 保留原状态)
  5. 不删原行, 只改 status (T16 迁移可反查)
  6. 真实库零写入 (conftest 隔离)
  7. list_legacy_hold_tickets / list_legacy_hold_audit / get_stats 查询
"""
from __future__ import annotations

import json
import sqlite3

from backend.repository.db import get_connection
from backend.services.legacy_hold_service import (
    LEGACY_HOLD_ACTION,
    LEGACY_HOLD_ACTOR,
    LEGACY_HOLD_STATUS,
    LegacyHoldResult,
    LegacyHoldService,
)


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
def _insert_pending_ticket(
    conn: sqlite3.Connection,
    ticket_id: str,
    *,
    target_type: str = "skill",
    target_id: str = "skill-default",
    status: str = "pending",
    source: str = "manual",
) -> None:
    """塞一条 trigger_tickets (默认 status=pending, 可改)."""
    conn.execute(
        "INSERT INTO trigger_tickets "
        "(ticket_id, target_type, target_id, priority, source, user_id, "
        " inputs, status, attempts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ticket_id,
            target_type,
            target_id,
            1,
            source,
            None,
            json.dumps({"k": "v"}, ensure_ascii=False),
            status,
            0,
        ),
    )


# ---------------------------------------------------------------------------
# 1. 53 pending → legacy_hold (主路径)
# ---------------------------------------------------------------------------
def test_reap_53_pending_to_legacy_hold(temp_db) -> None:
    """53 pending 票据 → status 全部改 legacy_hold + audit_log 留痕."""
    conn = get_connection()
    for i in range(53):
        _insert_pending_ticket(conn, f"tg-{i:03d}", target_id=f"skill-{i:03d}")
    conn.commit()

    svc = LegacyHoldService()
    result = svc.reap_pending_tickets()
    assert isinstance(result, LegacyHoldResult)
    assert result.candidate_count == 53
    assert result.reclassified_count == 53
    assert result.audit_log_count == 53
    assert result.duration_ms >= 0

    # 验证 status 全部改完
    rows = conn.execute(
        "SELECT status, COUNT(*) AS c FROM trigger_tickets GROUP BY status"
    ).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    assert counts.get(LEGACY_HOLD_STATUS) == 53
    assert counts.get("pending", 0) == 0


# ---------------------------------------------------------------------------
# 2. 幂等: 重复跑不重复标
# ---------------------------------------------------------------------------
def test_reap_is_idempotent(temp_db) -> None:
    """第二次跑: candidate 仍可能 > 0 (若新增 pending), reclassified=0."""
    conn = get_connection()
    for i in range(5):
        _insert_pending_ticket(conn, f"tg-idem-{i}")
    conn.commit()

    svc = LegacyHoldService()
    first = svc.reap_pending_tickets()
    assert first.reclassified_count == 5
    assert first.audit_log_count == 5

    second = svc.reap_pending_tickets()
    assert second.candidate_count == 0  # 已无 pending
    assert second.reclassified_count == 0
    assert second.audit_log_count == 0


def test_reap_idempotent_with_new_pending(temp_db) -> None:
    """第一次跑后再插新 pending → 第二次跑只标新行."""
    conn = get_connection()
    for i in range(3):
        _insert_pending_ticket(conn, f"tg-new-{i}")
    conn.commit()

    svc = LegacyHoldService()
    first = svc.reap_pending_tickets()
    assert first.reclassified_count == 3

    # 新增 2 条
    _insert_pending_ticket(conn, "tg-fresh-1")
    _insert_pending_ticket(conn, "tg-fresh-2")
    conn.commit()

    second = svc.reap_pending_tickets()
    assert second.candidate_count == 2
    assert second.reclassified_count == 2
    assert second.audit_log_count == 2


# ---------------------------------------------------------------------------
# 3. audit_log 留痕正确
# ---------------------------------------------------------------------------
def test_audit_log_persisted_correctly(temp_db) -> None:
    """audit_log 每条受影响票据一条, actor/action/target/detail 完整."""
    conn = get_connection()
    _insert_pending_ticket(conn, "tg-audit-1", target_type="playbook", target_id="pb-x")
    _insert_pending_ticket(conn, "tg-audit-2", target_type="skill", target_id="sk-y")
    conn.commit()

    svc = LegacyHoldService()
    svc.reap_pending_tickets()

    rows = conn.execute(
        "SELECT actor, action, target, detail FROM audit_log "
        "WHERE action = ? ORDER BY target",
        (LEGACY_HOLD_ACTION,),
    ).fetchall()
    assert len(rows) == 2
    assert all(r["actor"] == LEGACY_HOLD_ACTOR for r in rows)
    targets = sorted(r["target"] for r in rows)
    assert targets == [
        "trigger_ticket:tg-audit-1",
        "trigger_ticket:tg-audit-2",
    ]

    detail0 = json.loads(rows[0]["detail"])
    assert detail0["target_type"] == "playbook"
    assert detail0["target_id"] == "pb-x"
    assert detail0["previous_status"] == "pending"
    assert detail0["new_status"] == LEGACY_HOLD_STATUS
    assert "F01" in detail0["reason"]


# ---------------------------------------------------------------------------
# 4. 非 pending 票据不动
# ---------------------------------------------------------------------------
def test_non_pending_tickets_unchanged(temp_db) -> None:
    """running/done/failed 票据不动, 只改 pending."""
    conn = get_connection()
    _insert_pending_ticket(conn, "tg-pending-1")
    _insert_pending_ticket(conn, "tg-running-1", status="running")
    _insert_pending_ticket(conn, "tg-done-1", status="done")
    _insert_pending_ticket(conn, "tg-failed-1", status="failed")
    conn.commit()

    svc = LegacyHoldService()
    result = svc.reap_pending_tickets()
    assert result.candidate_count == 1
    assert result.reclassified_count == 1
    assert result.audit_log_count == 1

    rows = conn.execute(
        "SELECT ticket_id, status FROM trigger_tickets ORDER BY ticket_id"
    ).fetchall()
    statuses = {r["ticket_id"]: r["status"] for r in rows}
    assert statuses["tg-pending-1"] == LEGACY_HOLD_STATUS
    assert statuses["tg-running-1"] == "running"
    assert statuses["tg-done-1"] == "done"
    assert statuses["tg-failed-1"] == "failed"


# ---------------------------------------------------------------------------
# 5. 不删原行, 只改 status (T16 迁移可反查)
# ---------------------------------------------------------------------------
def test_rows_not_deleted_status_only(temp_db) -> None:
    """收口后行数不变, ticket_id + 原字段保留."""
    conn = get_connection()
    for i in range(10):
        _insert_pending_ticket(conn, f"tg-preserve-{i}", target_id=f"id-{i}")
    conn.commit()

    before = conn.execute("SELECT COUNT(*) FROM trigger_tickets").fetchone()[0]
    svc = LegacyHoldService()
    svc.reap_pending_tickets()
    after = conn.execute("SELECT COUNT(*) FROM trigger_tickets").fetchone()[0]
    assert before == after == 10

    # 原 ticket_id / target_id 全部可查
    rows = conn.execute(
        "SELECT ticket_id, target_id, status FROM trigger_tickets "
        "WHERE status = ?",
        (LEGACY_HOLD_STATUS,),
    ).fetchall()
    assert len(rows) == 10
    assert all(r["ticket_id"].startswith("tg-preserve-") for r in rows)
    assert all(r["target_id"].startswith("id-") for r in rows)


# ---------------------------------------------------------------------------
# 6. 查询接口
# ---------------------------------------------------------------------------
def test_list_legacy_hold_tickets(temp_db) -> None:
    """list_legacy_hold_tickets 返回 legacy_hold 行."""
    conn = get_connection()
    _insert_pending_ticket(conn, "tg-list-1")
    _insert_pending_ticket(conn, "tg-list-2")
    _insert_pending_ticket(conn, "tg-other-1", status="running")
    conn.commit()

    svc = LegacyHoldService()
    svc.reap_pending_tickets()

    rows = svc.list_legacy_hold_tickets()
    assert len(rows) == 2
    ticket_ids = {r["ticket_id"] for r in rows}
    assert ticket_ids == {"tg-list-1", "tg-list-2"}


def test_get_stats_includes_legacy_hold(temp_db) -> None:
    """get_stats 字典含 legacy_hold 键."""
    conn = get_connection()
    _insert_pending_ticket(conn, "tg-stats-1")
    _insert_pending_ticket(conn, "tg-stats-2")
    _insert_pending_ticket(conn, "tg-stats-running", status="running")
    conn.commit()

    svc = LegacyHoldService()
    svc.reap_pending_tickets()

    stats = svc.get_stats()
    assert stats.get(LEGACY_HOLD_STATUS) == 2
    assert stats.get("running") == 1
    assert stats.get("pending", 0) == 0


# ---------------------------------------------------------------------------
# 7. empty DB 路径
# ---------------------------------------------------------------------------
def test_reap_empty_db_noop(temp_db) -> None:
    """空 DB: candidate=0 / reclassified=0 / audit=0, 不抛."""
    svc = LegacyHoldService()
    result = svc.reap_pending_tickets()
    assert result.candidate_count == 0
    assert result.reclassified_count == 0
    assert result.audit_log_count == 0
