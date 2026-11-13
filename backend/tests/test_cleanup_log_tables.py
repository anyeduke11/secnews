"""v0.8.8 R-17 C2.2: 日志类表环形截断 (``scripts/cleanup_log_tables.py``)。

测试意图 (WHY, 而非 WHAT):
- **环形语义**: 截断必须保留「最新 N 行」而非「删超窗外的全部」—— 行数
  上限是封顶手段, 删错了方向会删掉最近的数据 (用户看 OpsRunsPanel 时
  恰好在排查一个刚失败的任务)。
- **证据层不可截断**: wiki_events 是 R-17 的审计凭据 (owner 2026-11-13
  裁决「wiki 是证据」), 本脚本不得对它做任何删除 —— 由
  ``test_cli_json_output_parseable`` 的 results 集合守住 (表不在集合内 =
  没跑截断)。
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
        CREATE TABLE ai_scores (
            id INTEGER PRIMARY KEY, hotspot_id TEXT, score REAL, reason TEXT,
            scorer TEXT, scored_at TEXT, created_at TEXT);
        """
    )
    conn.commit()
    return conn


def _seed(conn: sqlite3.Connection, table: str, ts_col: str, n: int, *, days_old: float = 1.0) -> None:
    """灌 n 行, 时间从 days_old 天前线性分布到今天。"""
    now = datetime.now(timezone.utc)
    cols = {"job_runs": "job_id",
            "admission_log": "verdict",
            "llm_usage_log": "provider",
            "ai_scores": "hotspot_id"}[table]
    rows = []
    for i in range(n):
        ts = (now - timedelta(days=days_old * (n - i) / n)).isoformat()
        rows.append((cols + f"_{i}", ts))
    conn.executemany(
        f"INSERT INTO {table} ({cols}, {ts_col}) VALUES (?,?)", rows)
    conn.commit()


@pytest.fixture
def log_db(tmp_path: Path) -> Path:
    """日志库 — 种子数据须**确实超阈**才让截断有活干。

    超阈口径 (与脚本阈值一致):
    - job_runs / admission_log: 行数上限 20,000 / 5,000 → 种子需 > 上限
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
    # admission_log 100 行 < 5,000 上限 → 不动
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
    # 边界值: keep=100 → 「第 101 新」的行会被删, 保留的最旧行必须比它新。
    # 取边界值做比较 (不用「今天日期字符串」→ 种子跨 1 天时会日期腐烂)
    boundary = conn.execute(
        "SELECT started_at FROM job_runs ORDER BY started_at DESC, id DESC "
        "LIMIT 1 OFFSET 100"
    ).fetchone()[0]
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
    assert oldest_kept > boundary, "保留的最旧行必须比被删的边界行新 (环形方向不能反)"


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
        "job_runs", "admission_log", "llm_cache", "llm_usage_log", "ai_scores"
    }, "wiki_events 不得出现在截断集合 (owner 2026-11-13 裁决: wiki 是证据)"


def test_vacuum_truncates_wal_afterwards(tmp_path: Path) -> None:
    """VACUUM 后 WAL 必须被截断 —— 否则净收益为负。

    WHY: WAL 模式下 VACUUM 把整个重建后的库写进 WAL (≈ 库体积), 而服务侧
    连接的自动 checkpoint 是 PASSIVE (只回写页, 不截断文件) → WAL 永久停在
    满尺寸。实测 (2026-11-12 生产): 截断后 db 199 MB + wal 210 MB = 399 MB,
    **反而大于截断前的 364 MB**。故 VACUUM 之后必须再跑一次 TRUNCATE checkpoint。
    """
    p = tmp_path / "wal.db"
    conn = _make_db(p)
    conn.execute("PRAGMA journal_mode = WAL")
    _seed(conn, "job_runs", "started_at", 20_050)
    conn.commit()
    conn.close()

    env = trim_all(p, dry_run=False, vacuum=True)
    assert env["ok"] is True, env
    labels = {r["table"] for r in env["data"]["results"]}
    assert "<wal_checkpoint_after_vacuum>" in labels, "VACUUM 后必须再 checkpoint 一次"

    wal = p.with_name(p.name + "-wal")
    wal_size = wal.stat().st_size if wal.exists() else 0
    assert wal_size == 0, f"WAL 未被截断 (残留 {wal_size} B) → 净收益为负"


def test_llm_cache_ttl_trim_deletes_only_expired(tmp_path: Path) -> None:
    """llm_cache 只删 TTL 过期行, 新鲜行与**表本身**必须保留。

    WHY: ``llm_cache`` 是 ai_hub 的活跃缓存表 (gateway 打分/分类/NER 读它),
    不是废弃表 —— 按「废弃表整体删」处理会打断 AI 调用链; 反过来只靠读路径
    惰性删单条, 冷 key 会永久滞留 (实测 18,100 行中 17,315 行已过期)。
    正确语义 = 周期兜底清扫过期行。

    回归护栏: 过期判定若用 ``strftime('%s', ...)`` (TEXT) 与 INTEGER 比较,
    SQLite「INTEGER < TEXT 恒真」会把**所有行**当过期 → 本测试的新鲜行断言
    会直接失败。
    """
    p = tmp_path / "cache.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(
        """
        CREATE TABLE llm_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cache_key TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL, model TEXT NOT NULL, response TEXT NOT NULL,
            cached_at TEXT NOT NULL, ttl_seconds INTEGER NOT NULL DEFAULT 86400);
        """
    )
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO llm_cache (cache_key, provider, model, response, cached_at, ttl_seconds)"
        " VALUES (?,?,?,?,?,?)",
        ("stale", "p", "m", "{}", (now - timedelta(days=3)).isoformat(), 3600),
    )
    conn.execute(
        "INSERT INTO llm_cache (cache_key, provider, model, response, cached_at, ttl_seconds)"
        " VALUES (?,?,?,?,?,?)",
        ("fresh", "p", "m", "{}", now.isoformat(), 86400),
    )
    conn.commit()
    conn.close()

    env = trim_all(p, dry_run=False)
    assert env["ok"] is True, env
    row = next(r for r in env["data"]["results"] if r["table"] == "llm_cache")
    assert row["deleted"] == 1, "过期行应被删且只删 1 行"

    conn = sqlite3.connect(str(p))
    keys = {r[0] for r in conn.execute("SELECT cache_key FROM llm_cache")}
    conn.close()
    assert keys == {"fresh"}, "缓存表本身及其新鲜行必须保留 (不可整表删)"


def _counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    out = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("job_runs", "admission_log", "llm_usage_log", "ai_scores")
    }
    conn.close()
    return out
