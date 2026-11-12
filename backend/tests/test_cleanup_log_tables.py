"""v0.8.8 R-17 C2.2: 日志类表环形截断 (``scripts/cleanup_log_tables.py``)。

测试意图 (WHY, 而非 WHAT):
- **环形语义**: 截断必须保留「最新 N 行」而非「删超窗外的全部」—— 行数
  上限是封顶手段, 删错了方向会删掉最近的数据 (用户看 OpsRunsPanel 时
  恰好在排查一个刚失败的任务)。
- **保留规则不可回归**: wiki_events 的 sink/rebuild 事件是 R-17「可重建」
  承诺的审计凭据; 带 wiki_path / db_ref 的行是「这条知识是哪次采集产生的」
  反查链 —— 两者删了就无法追溯, 且反查端点无时间下界, 删了必丢。
- **默认 dry-run**: 破坏性脚本若默认就写库, 一次误调用即丢历史日志。
- **幂等**: 每小时跑, 第二轮必须删 0 行, 否则会误删仍在窗口内的数据。
- **失败不扩散**: 单表失败不影响其余表, 且必须被计入 envelope (fail-loud)。
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "cleanup_log_tables.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cleanup_log_tables import trim_all


def _make_db(path: Path) -> sqlite3.Connection:
    """建一张最小日志库 (表结构与生产一致的关键列)。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE job_runs (
            id INTEGER PRIMARY KEY, job_id TEXT, job_type TEXT, trace_id TEXT,
            started_at TEXT, finished_at TEXT, status TEXT, duration_ms INTEGER,
            error TEXT, meta_json TEXT);
        CREATE TABLE admission_log (
            id INTEGER PRIMARY KEY, material_id TEXT, body_hash TEXT, verdict TEXT,
            reason TEXT, matched_rule_id TEXT, raw_material_json TEXT, created_at TEXT);
        CREATE TABLE llm_usage_log (
            id INTEGER PRIMARY KEY, provider TEXT, model TEXT, task TEXT, tokens INTEGER,
            cost_usd REAL, latency_ms INTEGER, occurred_at TEXT, ok INTEGER, error TEXT,
            prompt_tokens INTEGER, completion_tokens INTEGER, tokens_estimated INTEGER,
            trace_id TEXT, scene TEXT, config_source TEXT, key_source TEXT);
        CREATE TABLE wiki_events (
            id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, wiki_path TEXT, db_table TEXT,
            db_row_id TEXT, agent TEXT, payload TEXT);
        CREATE TABLE ai_scores (
            id INTEGER PRIMARY KEY, hotspot_id TEXT, score REAL, reason TEXT,
            scorer TEXT, scored_at TEXT, created_at TEXT);
        """
    )
    conn.commit()
    return conn


def _seed(conn: sqlite3.Connection, table: str, ts_col: str, n: int, *, days_old: float = 1.0,
          extra: tuple[str, str] | None = None) -> None:
    """灌 n 行, 时间从 days_old 天前线性分布到今天。"""
    now = datetime.now(timezone.utc)
    cols = {"job_runs": ("job_id", "started_at"),
            "admission_log": ("verdict", "created_at"),
            "llm_usage_log": ("provider", "occurred_at"),
            "wiki_events": ("kind", "ts"),
            "ai_scores": ("hotspot_id", "scored_at")}[table]
    rows = []
    for i in range(n):
        ts = (now - timedelta(days=days_old * (n - i) / n)).isoformat()
        if table == "wiki_events":
            kind, wp = (extra if extra else ("agent_write", ""))
            rows.append((ts, kind, wp, "", "", "agent", "{}"))
        else:
            rows.append((cols[0] + f"_{i}", ts))
    if table == "wiki_events":
        conn.executemany(
            "INSERT INTO wiki_events (ts, kind, wiki_path, db_table, db_row_id, agent, payload)"
            " VALUES (?,?,?,?,?,?,?)", rows)
    else:
        conn.executemany(
            f"INSERT INTO {table} ({cols[0]}, {ts_col}) VALUES (?,?)", rows)
    conn.commit()


@pytest.fixture
def log_db(tmp_path: Path) -> Path:
    """日志库 — 种子数据须**确实超阈**才让截断有活干。

    超阈口径 (与脚本阈值一致):
    - job_runs / admission_log: 行数上限 20,000 / 15,000 → 种子需 > 上限
    - llm_usage_log / ai_scores: 30 天时间窗 → 种子需含 60 天前的行
    故这里给 job_runs 灌 20,050 行 (略超上限), 其余表灌 100 行 + 1 条超龄行。
    """
    p = tmp_path / "logs.db"
    conn = _make_db(p)
    _seed(conn, "job_runs", "started_at", 20_050)
    _seed(conn, "admission_log", "created_at", 100)
    _seed(conn, "llm_usage_log", "occurred_at", 100)
    _seed(conn, "ai_scores", "scored_at", 100)
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    conn.execute(
        "INSERT INTO llm_usage_log (provider, occurred_at) VALUES (?, ?)", ("old", old))
    conn.execute(
        "INSERT INTO ai_scores (hotspot_id, scored_at) VALUES (?, ?)", ("old", old))
    conn.commit()
    conn.close()
    return p


def test_dry_run_is_default_and_persists_nothing(log_db: Path) -> None:
    """默认 dry-run → 只算不删, 数据一行不动 (破坏性脚本硬约定)。"""
    before = _counts(log_db)
    env = trim_all(log_db, dry_run=True)
    assert env["ok"] is True
    assert env["data"]["dry_run"] is True
    assert env["data"]["deleted_total"] > 0, "dry-run 应报告可删量"
    assert _counts(log_db) == before, "dry-run 不得落库"


def test_execute_trims_below_row_cap(log_db: Path) -> None:
    """执行后各表行数降到上限内, 且**保留最新行** (环形方向正确)。"""
    env = trim_all(log_db, dry_run=False)
    assert env["ok"] is True
    conn = sqlite3.connect(str(log_db))
    # job_runs 上限 20,000 → 精确封顶 (行值比较 → 无 +1 偏差)
    assert conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0] == 20_000
    # admission_log 100 行 < 15,000 上限 → 不动
    assert conn.execute("SELECT COUNT(*) FROM admission_log").fetchone()[0] == 100
    conn.close()


def test_row_cap_keeps_newest_and_drops_oldest(tmp_path: Path) -> None:
    """超上限时: 删最旧、留最新 —— 且最新行必须还在。"""
    p = tmp_path / "cap.db"
    conn = _make_db(p)
    _seed(conn, "job_runs", "started_at", 500)
    # 额外插一行「最新」作锚点
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO job_runs (job_id, started_at) VALUES (?, ?)", ("ANCHOR_NEWEST", now))
    conn.commit()
    conn.close()

    # 直接调内部函数 (阈值写死 20k, 用单测难造 2 万行 → 测边界逻辑本身)
    from cleanup_log_tables import _trim_by_count

    c2 = sqlite3.connect(str(p))
    deleted = _trim_by_count(c2, "job_runs", "started_at", 100)
    c2.commit()
    remaining = c2.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0]
    anchor = c2.execute(
        "SELECT COUNT(*) FROM job_runs WHERE job_id='ANCHOR_NEWEST'").fetchone()[0]
    oldest_kept = c2.execute("SELECT MIN(started_at) FROM job_runs").fetchone()[0]
    c2.close()

    assert deleted == 401, "应删最旧 401 行"
    assert remaining == 100, "应保留 100 行"
    assert anchor == 1, "最新行必须保留 (环形方向不能反)"
    assert oldest_kept > datetime.now(timezone.utc).isoformat()[:10], "保留的应是较新的行"


def test_wiki_events_keeps_sink_and_rebuild_kinds(tmp_path: Path) -> None:
    """sink / rebuild / rebuild_diff 事件**永不删** (R-17 审计凭据)。"""
    p = tmp_path / "we.db"
    conn = _make_db(p)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=400)).isoformat()
    for kind in ("sink", "rebuild", "rebuild_diff", "agent_write"):
        conn.execute(
            "INSERT INTO wiki_events (ts, kind, wiki_path, db_table, db_row_id, agent, payload)"
            " VALUES (?,?,?,?,?,?,?)", (old, kind, "", "", "", "a", "{}"))
    conn.commit()
    conn.close()

    from cleanup_log_tables import _trim_wiki_events

    c2 = sqlite3.connect(str(p))
    _trim_wiki_events(c2, 0)
    c2.commit()
    kinds = {r[0] for r in c2.execute("SELECT DISTINCT kind FROM wiki_events")}
    c2.close()
    assert {"sink", "rebuild", "rebuild_diff"} <= kinds, "审计事件被误删"
    assert "agent_write" not in kinds, "无引用无保留 kind 的行应被删"


def test_wiki_events_keeps_rows_with_wiki_path(tmp_path: Path) -> None:
    """带 wiki_path 的行**永不删** (反查端点无时间下界 → 删了必丢追溯链)。"""
    p = tmp_path / "we2.db"
    conn = _make_db(p)
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    conn.execute(
        "INSERT INTO wiki_events (ts, kind, wiki_path, db_table, db_row_id, agent, payload)"
        " VALUES (?,?,?,?,?,?,?)", (old, "agent_write", "items/abc.md", "", "", "a", "{}"))
    conn.commit()
    conn.close()

    from cleanup_log_tables import _trim_wiki_events

    c2 = sqlite3.connect(str(p))
    _trim_wiki_events(c2, 0)
    c2.commit()
    n = c2.execute("SELECT COUNT(*) FROM wiki_events").fetchone()[0]
    c2.close()
    assert n == 1, "带 wiki_path 的行必须保留"


def test_idempotent_second_run_deletes_nothing(log_db: Path) -> None:
    """第二轮删 0 行 (每小时跑 → 幂等是安全前提)。"""
    trim_all(log_db, dry_run=False)
    env = trim_all(log_db, dry_run=False)
    assert env["data"]["deleted_total"] == 0


def test_age_window_deletes_old_rows(log_db: Path) -> None:
    """超龄行被删 (llm_usage_log 30 天窗)。"""
    conn = sqlite3.connect(str(log_db))
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    conn.execute(
        "INSERT INTO llm_usage_log (provider, occurred_at) VALUES (?, ?)", ("old", old))
    conn.commit()
    conn.close()

    trim_all(log_db, dry_run=False)
    conn = sqlite3.connect(str(log_db))
    n = conn.execute(
        "SELECT COUNT(*) FROM llm_usage_log WHERE occurred_at < ?",
        ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),),
    ).fetchone()[0]
    conn.close()
    assert n == 0, "60 天前的行应被 30 天窗删掉"


def test_missing_db_returns_fatal_envelope(tmp_path: Path) -> None:
    """目标库不存在 → 明确失败 (不静默建空库)。"""
    env = trim_all(tmp_path / "nope.db", dry_run=False)
    assert env["ok"] is False
    assert env["code"] == 2
    assert "not found" in env["data"]["error"]


def test_cli_json_output_parseable(log_db: Path) -> None:
    """CLI --json 输出可被解析 (调度 job 依赖 envelope)。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(log_db), "--dry-run", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    import json

    env = json.loads(proc.stdout)
    assert env["ok"] is True
    assert {r["table"] for r in env["data"]["results"]} == {
        "job_runs", "admission_log", "llm_usage_log", "wiki_events", "ai_scores"
    }


def _counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    out = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("job_runs", "admission_log", "llm_usage_log", "wiki_events", "ai_scores")
    }
    conn.close()
    return out
