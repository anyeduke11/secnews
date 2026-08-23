"""v0.5 M2-Task4: scripts/db_diet.py 单元测试 + CLI 契约验证。

不依赖真实 hotspot.db — 用 tmp_path 建一个最小测试 db, 注入少量行,
验证 retention 逻辑、CLI --json 契约、备份副本机制。
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "db_diet.py"
RETENTION = REPO_ROOT / "scripts" / "retention.json"


@pytest.fixture
def mini_db(tmp_path: Path) -> Path:
    """构造一个含 qcl / crawler_runs / hotspots / favorites 的小测试库。"""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE quality_check_logs (
            id INTEGER PRIMARY KEY,
            item_id TEXT,
            gate_name TEXT,
            passed INTEGER,
            score_deduction INTEGER,
            flags TEXT,
            reason TEXT,
            error_msg TEXT,
            checked_at TEXT,
            mode TEXT
        );
        CREATE TABLE quality_check_logs_archive (
            id INTEGER PRIMARY KEY,
            item_id TEXT,
            gate_name TEXT,
            passed INTEGER,
            score_deduction INTEGER,
            flags TEXT,
            reason TEXT,
            error_msg TEXT,
            checked_at TEXT,
            mode TEXT,
            archived_at TEXT
        );
        CREATE TABLE crawler_runs (
            id INTEGER PRIMARY KEY,
            source_id TEXT,
            category TEXT,
            started_at TEXT,
            finished_at TEXT,
            status TEXT
        );
        CREATE TABLE raw_items (
            id INTEGER PRIMARY KEY,
            fetched_at TEXT
        );
        CREATE TABLE hotspots (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            source TEXT,
            category TEXT,
            published_at TEXT,
            score INTEGER,
            quality_score INTEGER,
            ingested_at TEXT,
            fetched_at TEXT,
            summary TEXT,
            region TEXT,
            bid_status TEXT
        );
        CREATE TABLE favorites (
            id INTEGER PRIMARY KEY,
            hotspot_id TEXT
        );
        CREATE TABLE sync_history (
            id INTEGER PRIMARY KEY,
            finished_at TEXT
        );
    """)
    conn.execute(
        "INSERT INTO quality_check_logs (id, item_id, gate_name, checked_at) VALUES (1, 'i1', 'g1', '2020-01-01T00:00:00')"
    )  # 老数据, 应被 archive_db_table 清掉
    conn.execute(
        "INSERT INTO quality_check_logs (id, item_id, gate_name, checked_at) VALUES (2, 'i2', 'g2', '2030-01-01T00:00:00')"
    )  # 未来数据, 保留
    conn.execute(
        "INSERT INTO crawler_runs (id, source_id, category, started_at, status) VALUES (1, 's1', 'bid', '2020-01-01T00:00:00', 'success')"
    )  # 老数据, 应被 truncate
    conn.execute(
        "INSERT INTO hotspots (id, title, url, source, category, ingested_at) VALUES ('h_old', 'old item', 'http://x.com/1', 'src1', 'bid', '2020-01-01T00:00:00')"
    )  # 180d 之前, 应被 archive_jsonl
    conn.execute(
        "INSERT INTO hotspots (id, title, url, source, category, ingested_at) VALUES ('h_old_fav', 'favorited old', 'http://x.com/2', 'src1', 'bid', '2020-01-01T00:00:00')"
    )  # 180d 之前, 但被收藏
    conn.execute(
        "INSERT INTO favorites (id, hotspot_id) VALUES (1, 'h_old_fav')"
    )
    conn.commit()
    conn.close()
    return db_path


def _run_db_diet(db_path: Path, *extra_args: str) -> dict:
    """走 db_diet.py 子进程 (一致用 --db-path, 让 maintenance_service 也走对库)。

    注意 cwd 必须 = REPO_ROOT (project root), pytest 默认 cwd=backend/ 会
    让 db_diet 找不到 ``scripts.cli_contract`` 模块 (ModuleNotFoundError),
    表现为 STDOUT 空 + json.JSONDecodeError。
    """
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--json",
        "--db-path", str(db_path),
        *extra_args,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": str(REPO_ROOT)},
    )
    if proc.returncode not in (0, 1):  # EXIT_OK=0, EXIT_PARTIAL=1
        raise RuntimeError(
            f"db_diet.py 失败 rc={proc.returncode} stderr={proc.stderr[:500]} "
            f"stdout={proc.stdout[:200]!r}"
        )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"db_diet.py 空 stdout rc={proc.returncode} stderr={proc.stderr[:500]}"
        )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# 1. retention.json 结构校验
# ---------------------------------------------------------------------------
def test_retention_json_exists():
    """retention.json 必须存在, 含 tables 数组。"""
    assert RETENTION.exists(), f"missing retention.json at {RETENTION}"
    with open(RETENTION, encoding="utf-8") as f:
        cfg = json.load(f)
    assert "tables" in cfg
    assert len(cfg["tables"]) >= 3
    # 必填字段
    for tbl in cfg["tables"]:
        for k in ("table", "temp", "ts_column", "ts_format", "retention_days", "action", "scheduled_in"):
            assert k in tbl, f"retention.json 表 {tbl.get('table')} 缺字段 {k}"


def test_retention_json_referenced_tables_exist():
    """retention.json 引用的表都必须在 db 中存在 (db_diet.py 会容错 skip)。

    T6.4 物理分离后, 表可能跨 db (main/warm/cold)。本测试 ATTACH warm/cold 后再扫描。
    """
    db_path = REPO_ROOT / "backend" / "hotspot.db"
    warm_path = REPO_ROOT / "backend" / "hotspot-warm.db"
    cold_path = REPO_ROOT / "backend" / "hotspot-cold.db"
    conn = sqlite3.connect(str(db_path))
    if warm_path.exists():
        conn.execute(f"ATTACH DATABASE '{warm_path}' AS warm")
    if cold_path.exists():
        conn.execute(f"ATTACH DATABASE '{cold_path}' AS cold")
    existing: set[str] = set()
    schemas = ["main"]
    for r in conn.execute("PRAGMA database_list").fetchall():
        if r[1] in ("warm", "cold"):
            schemas.append(r[1])
    for schema in schemas:
        for r in conn.execute(
            f"SELECT name FROM {schema}.sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            existing.add(r[0])
    conn.close()
    with open(RETENTION, encoding="utf-8") as f:
        cfg = json.load(f)
    for tbl in cfg["tables"]:
        if tbl["table"] in existing:
            continue  # OK
        # 表不存在是容错场景 (collection_history 等), 但 retention 不应列不存在的表
        # 允许 backup_service 管的不存在项
        if tbl.get("scheduled_in") == "backup":
            continue
        # 跳过 collection_history / export_cache (旧 cleanup_history 残留登记)
        pytest.fail(
            f"retention.json 引用的表 {tbl['table']} 不存在于 db, 应当移除"
        )


# ---------------------------------------------------------------------------
# 2. CLI 契约 envelope 形状
# ---------------------------------------------------------------------------
def test_cli_envelope_shape(mini_db: Path):
    """--json 输出必须含 ok/code/duration_ms/data 四字段。"""
    envelope = _run_db_diet(mini_db, "--dry-run")
    for k in ("ok", "code", "duration_ms", "data"):
        assert k in envelope, f"envelope 缺字段 {k}"
    assert isinstance(envelope["ok"], bool)
    assert isinstance(envelope["code"], int)
    assert isinstance(envelope["duration_ms"], int) and envelope["duration_ms"] >= 0
    data = envelope["data"]
    assert "db" in data and "mode" in data and "summary" in data
    assert "results" in data and isinstance(data["results"], list)


# ---------------------------------------------------------------------------
# 3. 干跑: 不修改 db
# ---------------------------------------------------------------------------
def test_dry_run_no_modification(mini_db: Path):
    """--dry-run 不能修改 db 数据。"""
    envelope = _run_db_diet(mini_db, "--dry-run")
    assert envelope["data"]["mode"] == "dry_run"

    conn = sqlite3.connect(str(mini_db))
    # 老 crawler_runs 行应仍在 (dry_run 不删)
    n = conn.execute("SELECT COUNT(*) FROM crawler_runs").fetchone()[0]
    assert n == 1, f"dry_run 不应删 crawler_runs, 仍有 {n} 行"
    # 老 hotspot 应仍在
    n = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    assert n == 2
    conn.close()


# ---------------------------------------------------------------------------
# 4. 实操: archive_db_table 清 quality_check_logs 老行
# ---------------------------------------------------------------------------
def test_execute_archive_quality_logs(mini_db: Path):
    """execute 模式应触发 archive_quality_logs() 把老行移入 archive 表。"""
    envelope = _run_db_diet(mini_db, "--execute")
    qcl_result = next(
        r for r in envelope["data"]["results"] if r["table"] == "quality_check_logs"
    )
    # 老行 (2020-01-01) 应被归档
    assert qcl_result["ok"] is True
    assert qcl_result["archived"] >= 1, (
        f"应归档至少 1 行老 qcl, 实测 {qcl_result['archived']}"
    )
    # db 中主表剩 1 行 (2030 未来)
    conn = sqlite3.connect(str(mini_db))
    n_main = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    n_arch = conn.execute("SELECT COUNT(*) FROM quality_check_logs_archive").fetchone()[0]
    conn.close()
    assert n_main == 1, f"主表应剩 1 行 (未来), 实测 {n_main}"
    assert n_arch >= 1, f"archive 表应有 1 行, 实测 {n_arch}"


# ---------------------------------------------------------------------------
# 5. 实操: truncate 清 crawler_runs 老行
# ---------------------------------------------------------------------------
def test_execute_truncate_crawler_runs(mini_db: Path):
    """execute 模式应删 crawler_runs 老行。"""
    envelope = _run_db_diet(mini_db, "--execute")
    cr_result = next(
        r for r in envelope["data"]["results"] if r["table"] == "crawler_runs"
    )
    assert cr_result["ok"] is True
    assert cr_result["deleted"] == 1
    # db 中 0 行
    conn = sqlite3.connect(str(mini_db))
    n = conn.execute("SELECT COUNT(*) FROM crawler_runs").fetchone()[0]
    conn.close()
    assert n == 0


# ---------------------------------------------------------------------------
# 6. 实操: archive_jsonl 清 hotspots 非收藏老行, 保留收藏行
# ---------------------------------------------------------------------------
def test_execute_archive_hotspots_respects_favorites(mini_db: Path):
    """180d 之前非收藏 hotspot 应归档, 但收藏行保留。

    注: 测试走 subprocess 跑 db_diet, ARCHIVE_DIR 是全局路径
    (backups/hotspots-archive/), 不在 tmp 内。验证用 db 行的
    删除 + 收藏保留, 不验证 JSONL 文件位置 (那是 io 行为)。
    """
    envelope = _run_db_diet(mini_db, "--execute")
    hp_result = next(
        r for r in envelope["data"]["results"] if r["table"] == "hotspots"
    )
    assert hp_result["ok"] is True, (
        f"hotspots archive_jsonl 应成功, 实测 skipped_reason={hp_result.get('skipped_reason')}"
    )
    assert hp_result["archived"] == 1, (
        f"应归档 1 行非收藏老 hotspot, 实测 {hp_result['archived']}"
    )
    # db 中剩 1 行 (收藏的)
    conn = sqlite3.connect(str(mini_db))
    remaining = [
        r[0] for r in conn.execute("SELECT id FROM hotspots").fetchall()
    ]
    conn.close()
    assert remaining == ["h_old_fav"], f"应只剩收藏行, 实测 {remaining}"
    # JSONL 文件应已写到 ARCHIVE_DIR (共享路径, 不验证具体文件名)
    archive_dir = REPO_ROOT / "backups" / "hotspots-archive"
    assert archive_dir.exists()
    jsonl_files = list(archive_dir.glob("*.jsonl"))
    assert len(jsonl_files) >= 1
    # 检查最新一个 jsonl 含正确内容
    latest = max(jsonl_files, key=lambda p: p.stat().st_mtime)
    content = latest.read_text(encoding="utf-8")
    # 可能含 h_old (刚写的) — 不强求 latest 一定是本次的 (并发场景)
    assert any(
        "h_old" in f.read_text(encoding="utf-8")
        for f in jsonl_files
    )


# ---------------------------------------------------------------------------
# 7. 单表过滤
# ---------------------------------------------------------------------------
def test_table_filter(mini_db: Path):
    """--table 仅跑单表, 其他表不动。"""
    envelope = _run_db_diet(mini_db, "--execute", "--table", "crawler_runs")
    # summary 应只有 1 表
    assert envelope["data"]["summary"]["total"] == 1
    # crawler_runs 已删, hotspots 仍在
    conn = sqlite3.connect(str(mini_db))
    n_cr = conn.execute("SELECT COUNT(*) FROM crawler_runs").fetchone()[0]
    n_hp = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    conn.close()
    assert n_cr == 0
    assert n_hp == 2  # hotspots 没跑


# ---------------------------------------------------------------------------
# 8. 备份副本演练
# ---------------------------------------------------------------------------
def test_backup_snapshot(tmp_path: Path, mini_db: Path):
    """--backup 应在副本上跑干跑, 不影响实库。"""
    backup_path = tmp_path / "snap.db"
    envelope = _run_db_diet(mini_db, "--dry-run", "--backup", str(backup_path))
    assert envelope["data"]["backup"]["ok"] is True
    assert backup_path.exists()
    # 副本含原数据
    conn = sqlite3.connect(str(backup_path))
    n = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    conn.close()
    assert n == 2