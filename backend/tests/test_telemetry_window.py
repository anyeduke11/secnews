"""v0.5 §18: 7 天遥测窗口 (telemetry window) 单元测试。

测试意图 (Rule 9):
- 台账驱动: 只有 retention.json 中 ``scheduled_in == "telemetry_window"``
  的表才被清理 — 窗口策略集中在台账, 代码不复制常量
- qcl 走归档语义 (archive 表保留行), truncate 表直接删除
- 窗口内 (< 7d) 数据必须保留, 这是"遥测窗口"的业务承诺
- dry_run 只读不动数据
- job 层: 有硬错误时抛异常让 instrument_job 记 ok=False;
  table_not_found 属 skip 不告警 (warm.db 尚未建库的合法状态)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services import maintenance_service as ms


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """隔离主库 + warm/cold 路径, 全量 schema。

    _isolate_temp_dbs (autouse) 已重定向 warm/cold; 这里补主库。
    crawler_runs / raw_items / quality_check_logs 经 T6.4 迁移后物理在
    warm.db — get_connection() 自动 ATTACH, 裸表名可达。
    """
    test_db = tmp_path / "telemetry.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _insert_telemetry(conn, *, old_days: int = 30, recent_days: int = 2) -> None:
    """向三张遥测表插入老/新两批数据。"""
    for days, n in ((old_days, 3), (recent_days, 2)):
        ts = _iso(days)
        for i in range(n):
            conn.execute(
                "INSERT INTO crawler_runs (source_id, category, started_at, status) "
                "VALUES (?, ?, ?, ?)",
                ("s1", "bid", ts, "success"),
            )
            conn.execute(
                "INSERT INTO raw_items (item_id, source_id, title, url, fetched_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"i-{days}-{i}", "s1", "t", f"http://x/{days}/{i}", ts),
            )
            conn.execute(
                "INSERT INTO quality_check_logs "
                "(item_id, gate_name, passed, score_deduction, flags, reason, "
                "error_msg, checked_at, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"q-{days}-{i}", "g", 1, 0, "[]", "r", None, ts, "loose"),
            )


def _counts(conn) -> dict[str, int]:
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("crawler_runs", "raw_items", "quality_check_logs")
    }


# ---------------------------------------------------------------------------
# 台账加载
# ---------------------------------------------------------------------------
def test_load_telemetry_specs_returns_three_tables():
    """retention.json 打了 telemetry_window 标签的表应恰好是遥测三件套。"""
    specs = ms.load_telemetry_specs()
    names = {s["table"] for s in specs}
    assert names == {"quality_check_logs", "crawler_runs", "raw_items"}
    # 窗口语义: 全部声明为 7 天
    assert all(s["retention_days"] == 7 for s in specs), (
        "SPEC §18.2: WARM 遥测层保留 7 天"
    )


# ---------------------------------------------------------------------------
# run_telemetry_window 核心行为
# ---------------------------------------------------------------------------
def test_run_telemetry_window_truncates_old_keeps_recent(temp_db):
    """>7 天清掉, <7 天保留 — 窗口语义的直接验证。"""
    conn = db.get_connection()
    _insert_telemetry(conn, old_days=30, recent_days=2)

    result = ms.run_telemetry_window(dry_run=False)

    counts = _counts(conn)
    assert counts["crawler_runs"] == 2, "crawler_runs 只留窗口内 2 行"
    assert counts["raw_items"] == 2, "raw_items 只留窗口内 2 行"
    assert result["rows_deleted"] == 6, "truncate 表合计删 6 行 (3+3)"
    assert result["failed"] == 0


def test_qcl_archives_instead_of_delete(temp_db):
    """quality_check_logs 必须走归档而非直删 (质量审计可追溯)。"""
    conn = db.get_connection()
    _insert_telemetry(conn, old_days=30, recent_days=2)

    ms.run_telemetry_window(dry_run=False)

    archived = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs_archive"
    ).fetchone()[0]
    assert archived == 3, ">7 天的 3 条应进入 archive 表 (非删除)"
    remaining = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs"
    ).fetchone()[0]
    assert remaining == 2, "主表只留窗口内 2 条"


def test_dry_run_touches_nothing(temp_db):
    """dry_run=True 是纯预览: 行数与 archive 表都不变。"""
    conn = db.get_connection()
    _insert_telemetry(conn, old_days=30, recent_days=2)

    result = ms.run_telemetry_window(dry_run=True)

    assert result["dry_run"] is True
    assert result["rows_deleted"] == 6, "预览应报告将要删除的数量"
    counts = _counts(conn)
    assert counts == {"crawler_runs": 5, "raw_items": 5, "quality_check_logs": 5}, (
        "dry_run 不得修改任何主表"
    )
    assert conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs_archive"
    ).fetchone()[0] == 0, "dry_run 不得写 archive 表"


def test_missing_table_is_skip_not_failure(temp_db):
    """台账含未建表时应记 skipped_reason, 且不算 failed。

    场景: warm.db 尚未建库时 truncate 表不存在 — 合法状态,
    不应触发 job 告警。
    """
    specs = [{"table": "no_such_table", "ts_column": "created_at",
              "action": "truncate", "retention_days": 7}]
    result = ms.run_telemetry_window(dry_run=False, specs=specs)
    assert result["failed"] == 0
    r = result["results"][0]
    assert not r["ok"]
    assert r["skipped_reason"] == "table_not_found"


def test_specs_injection_bypasses_ledger(temp_db):
    """specs 参数注入可脱离台账运行 (db_diet --table 同款调试能力)。"""
    conn = db.get_connection()
    _insert_telemetry(conn, old_days=30, recent_days=2)

    specs = [{"table": "crawler_runs", "ts_column": "started_at",
              "action": "truncate", "retention_days": 7}]
    result = ms.run_telemetry_window(dry_run=False, specs=specs)

    assert [r["table"] for r in result["results"]] == ["crawler_runs"]


# ---------------------------------------------------------------------------
# job 包装层
# ---------------------------------------------------------------------------
def test_job_raises_on_hard_error(temp_db, monkeypatch):
    """job 在硬错误时必须抛异常 → instrument_job 记 ok=False 推 SSE。

    job 内部延迟 import service 函数, patch 模块属性即可生效。
    """
    from backend.scheduler import jobs as jobs_mod

    def _raise(dry_run):
        raise RuntimeError("boom")

    monkeypatch.setattr(ms, "run_telemetry_window", _raise)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(jobs_mod.telemetry_window_job())


def test_job_swallows_skips(monkeypatch):
    """table_not_found 类 skip 不应让 job 抛异常 (周日链不被打断)。"""
    from backend.scheduler import jobs as jobs_mod

    def _fake(dry_run):
        return {
            "tables": 1, "rows_deleted": 0, "rows_archived": 0, "failed": 0,
            "results": [{"table": "ghost", "ok": False,
                         "skipped_reason": "table_not_found"}],
        }

    monkeypatch.setattr(ms, "run_telemetry_window", _fake)

    # 不抛即通过 (skip 类失败被容忍)
    asyncio.run(jobs_mod.telemetry_window_job())
