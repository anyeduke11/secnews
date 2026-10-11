"""DEV-0321: 清理类 job 告警覆盖测试 (db_diet / interest_signals_purge / observability_ttl)。

测试意图 (Rule 9): DEV-0318 事故的根因不是"job 崩溃"而是"job 静默空转
且 status ok"。本文件锁定每个清理 job 的**静默盲区必须进告警链**:
- db_diet_job: envelope 逐表 skip / rc 非 0 / envelope 不可解析 / 子进程炸
- interest_signals_purge: 吞异常不抛 (链语义) 但告警必须落表
- observability_ttl_job: 告警 + 照旧 raise (instrument 语义保持)
并守卫健康路径零告警 (防刷屏 = 告警可信的前提)。
mock 形状 = scripts/db_diet.py --json 真实 envelope ({ok,code,duration_ms,data.results})。
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from types import SimpleNamespace

import pytest

from backend.config import config
from backend.repository import db
from backend.scheduler.jobs import maintenance as jm


@pytest.fixture
def alerts_db(temp_db):
    """temp_db 全 schema (含 observability_alerts) + 告警读取 helper。"""
    def _alerts(metric: str | None = None):
        conn = db.get_connection()
        if metric:
            return conn.execute(
                "SELECT level, value, detail FROM observability_alerts "
                "WHERE metric = ? ORDER BY id",
                (metric,),
            ).fetchall()
        return conn.execute(
            "SELECT metric, level FROM observability_alerts ORDER BY id"
        ).fetchall()
    return _alerts


def _diet_envelope(results: list[dict]) -> str:
    return json.dumps({
        "ok": all(r.get("ok") for r in results),
        "code": 0,
        "duration_ms": 120,
        "data": {"db": "backend/hotspot.db", "mode": "dry_run",
                 "results": results,
                 "summary": {"total": len(results)}},
    })


# ---------------------------------------------------------------------------
# db_diet_job
# ---------------------------------------------------------------------------
def test_db_diet_job_script_path_exists():
    """路径回归守卫: v0.6 拆分后 parents[2] 曾指向不存在的 backend/scripts/
    → 子进程 rc=2 静默 (DEV-0321 实弹捕获)。repo_root 必须解析到仓库根。"""
    from pathlib import Path

    repo_root = Path(jm.__file__).resolve().parents[3]
    assert (repo_root / "scripts" / "db_diet.py").exists()


def test_db_diet_healthy_no_alert(alerts_db, monkeypatch):
    """rc=0 全表 ok → 零告警 (防刷屏守卫)。"""
    env = _diet_envelope([
        {"table": "quality_check_logs", "ok": True, "archived": 3},
        {"table": "crawler_runs", "ok": True, "deleted": 5},
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=env, stderr=""),
    )
    asyncio.run(jm.db_diet_job())
    assert alerts_db() == []


def test_db_diet_no_retention_days_skip_is_legitimate(alerts_db, monkeypatch):
    """台账声明 retention_days=null 的表 (backup_service 管) = 合法 skip。

    实弹取证 2026-10-11: 生产全台账 dry-run 含数十项 no_retention_days —
    若当漂移告警, 周日链开屏即数十表刷屏, 告警可信度归零。
    """
    env = _diet_envelope([
        {"table": "favorites", "ok": False, "skipped_reason": "no_retention_days"},
        {"table": "alert_rules", "ok": False, "skipped_reason": "no_retention_days"},
        {"table": "crawler_runs", "ok": True, "deleted": 5},
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=env, stderr=""),
    )
    asyncio.run(jm.db_diet_job())
    assert alerts_db() == []


def test_db_diet_drift_skip_alerts(alerts_db, monkeypatch, tmp_path):
    """warm 已建立 + table_not_found = 契约漂移 → db_diet.skip warn。"""
    warm = tmp_path / "hotspot-warm.db"
    warm.touch()
    monkeypatch.setattr(config, "warm_db_path", warm)
    env = _diet_envelope([
        {"table": "raw_items", "ok": True, "deleted": 1},
        {"table": "crawler_runs", "ok": False, "skipped_reason": "table_not_found"},
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=env, stderr=""),
    )
    asyncio.run(jm.db_diet_job())
    rows = alerts_db("db_diet.skip")
    assert len(rows) == 1 and rows[0]["level"] == "warn"
    assert json.loads(rows[0]["detail"])["tables"] == ["crawler_runs"]


def test_db_diet_all_skipped_is_critical(alerts_db, monkeypatch, tmp_path):
    """全表 skip (事故指纹) → critical。"""
    warm = tmp_path / "hotspot-warm.db"
    warm.touch()
    monkeypatch.setattr(config, "warm_db_path", warm)
    env = _diet_envelope([
        {"table": "quality_check_logs", "ok": False, "skipped_reason": "table_not_found"},
        {"table": "crawler_runs", "ok": False, "skipped_reason": "table_not_found"},
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=env, stderr=""),
    )
    asyncio.run(jm.db_diet_job())
    rows = alerts_db("db_diet.skip")
    assert len(rows) == 1 and rows[0]["level"] == "critical"


def test_db_diet_unparseable_envelope_alerts(alerts_db, monkeypatch):
    """envelope 不可解析 = 预览失明 → critical (不静默容忍)。"""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=2, stdout="not-json",
                                        stderr="boom in cli_contract"),
    )
    asyncio.run(jm.db_diet_job())  # 不抛
    rows = alerts_db("db_diet.failed")
    assert len(rows) == 1 and rows[0]["level"] == "critical"
    assert json.loads(rows[0]["detail"])["error"] == "envelope_unparseable"


def test_db_diet_partial_rc1_with_failed_table(alerts_db, monkeypatch):
    """rc=1 + 表级硬错误 → db_diet.failed warn (含表清单)。"""
    env = _diet_envelope([
        {"table": "hotspots", "ok": False},  # failed: not ok, no skipped_reason
        {"table": "crawler_runs", "ok": True, "deleted": 1},
    ])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=env, stderr=""),
    )
    asyncio.run(jm.db_diet_job())
    rows = alerts_db("db_diet.failed")
    assert len(rows) == 1 and rows[0]["level"] == "warn"
    detail = json.loads(rows[0]["detail"])
    assert detail["rc"] == 1
    assert [f["table"] for f in detail["failed_tables"]] == ["hotspots"]


def test_db_diet_subprocess_crash_alerts_and_raises(alerts_db, monkeypatch):
    """子进程本身炸 (timeout 等) → 告警后照旧 raise。"""
    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="db_diet.py", timeout=60)

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(jm.db_diet_job())
    rows = alerts_db("db_diet.failed")
    assert len(rows) == 1 and rows[0]["level"] == "critical"
    assert "TimeoutExpired" in json.loads(rows[0]["detail"])["error"]


# ---------------------------------------------------------------------------
# interest_signals_purge (吞异常 job: 告警落表但不抛)
# ---------------------------------------------------------------------------
def test_interest_purge_failure_alerts_without_raise(alerts_db, monkeypatch):
    from backend.services import interest_engine_service as ies

    def _boom(self):
        raise RuntimeError("disk locked")

    monkeypatch.setattr(ies.InterestEngineService, "purge_expired", _boom)
    asyncio.run(jm.interest_signals_purge())  # 链语义: 不抛
    rows = alerts_db("interest_signals_purge.failure")
    assert len(rows) == 1 and rows[0]["level"] == "warn"
    assert "disk locked" in json.loads(rows[0]["detail"])["error"]


# ---------------------------------------------------------------------------
# observability_ttl_job (raise 语义保持 + 告警)
# ---------------------------------------------------------------------------
def test_ttl_crash_alerts_and_raises(alerts_db, temp_db):
    """缺表致主链 DELETE 炸 → 告警落表 + 照旧 raise。

    触发方式选 DROP api_events 而非 patch get_connection — 后者会连
    _fire_alert 自身的告警写入一起炸掉, 测不到"告警落表"。
    """
    conn = db.get_connection()
    conn.execute("DROP TABLE api_events")
    with pytest.raises(Exception, match="api_events"):
        asyncio.run(jm.observability_ttl_job())
    rows = alerts_db("observability_ttl.failure")
    assert len(rows) == 1 and rows[0]["level"] == "warn"
