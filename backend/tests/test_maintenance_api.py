"""DEV-0318: /api/maintenance/cleanup-quality-logs 契约测试。

测试意图 (Rule 9): 该端点是 /maint 清理卡与 /settings DatabaseMaintenance
共同的清理入口。历史两层痛点由本测试钉死:
1. /maint 前端曾用 POST /cleanup + body{cutoff_days} —— 后端只认 query 参数
   (days/dry_run) 且 dry_run 默认 true → 按钮永远空跑, 53 万行积压两个月;
2. 真实归档 (53 万行 DELETE+INSERT) 曾在 async 端点内同步执行冻结事件循环
   (已改 asyncio.to_thread)。
本测试锁定「参数走 query + 响应为归档语义 dict 形状」这一前后端契约。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db):
    from backend.api.maintenance import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_qcl(db_path, rows: int, days_ago: int) -> None:
    """按生产存储的 T 格式 isoformat 时间戳灌 quality_check_logs 行。"""
    conn = sqlite3.connect(str(db_path))
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn.executemany(
        "INSERT INTO quality_check_logs (item_id, gate_name, passed, checked_at) "
        "VALUES (?, ?, ?, ?)",
        [(f"i{days_ago}-{i}", "gate1", 1, ts) for i in range(rows)],
    )
    conn.commit()
    conn.close()


def _counts(db_path):
    conn = sqlite3.connect(str(db_path))
    main = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    arch = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs_archive"
    ).fetchone()[0]
    conn.close()
    return main, arch


def test_dry_run_previews_without_modifying(client, temp_db):
    """dry_run=true 只报 rows_to_delete, 主表/archive 均不动。"""
    _seed_qcl(temp_db, rows=3, days_ago=30)

    r = client.post("/api/maintenance/cleanup-quality-logs?days=7&dry_run=true")
    assert r.status_code == 200
    body = r.json()
    # 前端清理卡读取的真实字段 (想象契约 deleted:number 永不存在)
    assert body["rows_to_delete"] == 3
    assert body["rows_archived"] == 0
    assert body["dry_run"] is True
    assert body["retention_days"] == 7
    assert _counts(temp_db) == (3, 0)


def test_real_run_archives_old_rows(client, temp_db):
    """dry_run=false 真实执行: 老行归档进 archive 表, 窗口内行保留。"""
    _seed_qcl(temp_db, rows=2, days_ago=30)  # 超 7 天窗口 → 应归档
    _seed_qcl(temp_db, rows=1, days_ago=1)  # 窗口内 → 保留

    r = client.post("/api/maintenance/cleanup-quality-logs?days=7&dry_run=false")
    assert r.status_code == 200
    body = r.json()
    assert body["rows_archived"] == 2
    assert body["rows_remaining_after"] == 1
    assert _counts(temp_db) == (1, 2)


# ---------------------------------------------------------------------------
# DEV-0320: GET /index-health 契约 (前端索引状态块依赖此形状)
# ---------------------------------------------------------------------------
def test_index_health_shape_and_ok(client):
    """响应必须含 mode/schemas[]/totals — 前端按实测形状渲染, 漂移即 CI 红。"""
    r = client.get("/api/maintenance/index-health")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "full"  # 默认深度检查
    assert body["schemas"], "temp_db 全 schema 下 main 必有索引"
    for s in body["schemas"]:
        for k in ("schema", "file", "user_indexes", "auto_indexes",
                  "tables_with_indexes", "stat1_covered", "check",
                  "check_errors", "check_ms"):
            assert k in s, f"schema 条目缺字段 {k}"
        assert s["check"] == "ok", f"新建库不应有 integrity 问题: {s}"
        # 统计覆盖分子 ≤ 分母 (口径一致性守卫)
        assert s["stat1_covered"] <= s["tables_with_indexes"]
    totals = body["totals"]
    assert totals["schemas_total"] == len(body["schemas"])
    assert totals["user_indexes"] == sum(s["user_indexes"] for s in body["schemas"])


def test_index_health_rejects_unknown_mode(client):
    """mode 白名单 (quick|full), 脏参数 422 而非静默兜底。"""
    r = client.get("/api/maintenance/index-health?mode=lucky")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# DEV-0322: 三档模型 (quality_log_tiers / 台账默认 / 可清理行同源)
# ---------------------------------------------------------------------------
def test_quality_log_tiers_bands(client, temp_db):
    """分档行数正确: 档1(0-7d)/档2(7-14d)/档3(14-21d)/超窗口(>21d)。"""
    _seed_qcl(temp_db, rows=3, days_ago=2)   # 档1
    _seed_qcl(temp_db, rows=2, days_ago=9)   # 档2
    _seed_qcl(temp_db, rows=1, days_ago=16)  # 档3
    _seed_qcl(temp_db, rows=4, days_ago=30)  # 超窗口

    r = client.get("/api/maintenance/quality-log-tiers?days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["tier_days"] == 7 and body["tiers"] == 3
    assert body["window_days"] == 21
    assert body["ledger_retention_days"] == 21
    assert body["total_rows"] == 10
    bands = body["bands"]
    assert [b["rows"] for b in bands] == [3, 2, 1, 4]
    assert [b["in_window"] for b in bands] == [True, True, True, False]
    out = bands[3]
    assert out["from_days"] is None and out["to_days"] == 21
    assert out["est_bytes"] == 4 * body["avg_row_bytes"] > 0


def test_quality_log_tiers_default_reads_ledger(client, temp_db):
    """不传 days → 档宽 = 台账 retention/tiers = 7 (单一事实源)。"""
    r = client.get("/api/maintenance/quality-log-tiers")
    assert r.status_code == 200
    assert r.json()["tier_days"] == 7
    assert r.json()["window_days"] == 21


def test_cleanup_endpoint_default_days_is_ledger(client, temp_db):
    """cleanup-quality-logs 不带 days → 保留窗口 = 台账 21 (3档×7),
    与 /maint 清理卡 days=档宽×3 同口径。"""
    _seed_qcl(temp_db, rows=2, days_ago=16)  # 档3 内 → 21d 窗口不动
    _seed_qcl(temp_db, rows=1, days_ago=30)  # 超窗口

    r = client.post("/api/maintenance/cleanup-quality-logs?dry_run=true")
    body = r.json()
    assert body["retention_days"] == 21
    assert body["rows_to_delete"] == 1


def test_dirty_report_cleanable_equals_out_window_band(client, temp_db):
    """「可清理行」(dirty-report) 与「超窗口档」(tiers) 必须同源恒等 —
    展示与执行两套数字正是 DEV-0318 想象契约的教训形态。"""
    _seed_qcl(temp_db, rows=5, days_ago=30)
    _seed_qcl(temp_db, rows=3, days_ago=1)

    d = client.get("/api/maintenance/dirty-report").json()["quality_check_logs"]
    t = client.get("/api/maintenance/quality-log-tiers?days=7").json()
    assert d["older_than_retention"] == 5
    assert d["retention_days"] == 21
    out_band = next(b for b in t["bands"] if not b["in_window"])
    assert d["older_than_retention"] == out_band["rows"]


# ---------------------------------------------------------------------------
# DEV-0323: GET /backups + POST /backups/compact 契约 (备份卡展示依赖)
# ---------------------------------------------------------------------------
def test_backups_inventory_shape(client):
    """隔离环境 (backup_dir 无产物) 也必须返回完整 shape — 前端按字段渲染。"""
    r = client.get("/api/maintenance/backups")
    assert r.status_code == 200
    body = r.json()
    for k in ("checked_at", "policy", "fulls", "chain", "side_dbs",
              "knowledge", "totals"):
        assert k in body
    assert body["policy"]["full_keep"] == 1
    assert body["policy"]["incremental_keep"] == 3
    assert isinstance(body["fulls"], list)
    assert "count" in body["chain"] and "files" in body["chain"]


def test_compact_endpoint_reports_honestly_without_full(client):
    """无 full 可合成 → 200 + ok=False + error 如实 (不假报成功)。"""
    r = client.post("/api/maintenance/backups/compact")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "no HOT full" in (body["error"] or "")
    assert body["compacted"] is False
