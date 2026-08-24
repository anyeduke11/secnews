"""v0.5 T6.4 修订: migrate_temp_layers.py 的 FTS5 vtab 处理能力单测。

背景 (PROGRESS.md warm 库 FTS5 事故): 跨库迁移把虚表当普通表搬 → 源库 DROP 后
虚表定义丢失, 目标库只剩孤儿影子表。本测试锁定三类 vtab 形态的正确迁移语义:
  external (content=X)   → dst 建虚表 + rebuild 回灌
  contentless (content='')→ dst 空占位 + rowid 重灌 (索引不可复制)
  plain fts5             → 直接行拷贝
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import migrate_temp_layers as mtl  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_src(tmp_path: Path) -> Path:
    """源库: 1 普通 external 场景 (knowledge_chunks + knowledge_chunks_fts)。"""
    db = tmp_path / "hotspot.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE knowledge_chunks (
            id INTEGER PRIMARY KEY,
            item_id TEXT,
            content TEXT,
            summary TEXT,
            created_at TEXT
        );
        CREATE VIRTUAL TABLE knowledge_chunks_fts USING fts5(
            content, summary,
            content=knowledge_chunks,
            tokenize='unicode61'
        );
        CREATE TRIGGER knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
            INSERT INTO knowledge_chunks_fts(rowid, content, summary)
                VALUES (new.rowid, new.content, new.summary);
        END;
        CREATE TABLE plain_notes (
            id INTEGER PRIMARY KEY,
            note TEXT
        );
    """)
    for i in range(1, 8):
        conn.execute(
            "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?)",
            (i, f"item-{i}", f"chunk body {i} about security", f"summary {i}", "2026-01-01"),
        )
    conn.execute("INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO plain_notes VALUES (1, 'hello')")
    conn.commit()
    conn.close()
    return db


def _attach_warm(conn: sqlite3.Connection, warm_path: Path) -> None:
    warm_path.touch(exist_ok=True)
    conn.execute(f"ATTACH DATABASE '{warm_path}' AS warm")


def _warm_names(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0] for r in conn.execute(
            "SELECT name FROM warm.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# 1. 纯函数
# ---------------------------------------------------------------------------
def test_vtab_kind_external():
    kind, content = mtl.vtab_kind(
        "CREATE VIRTUAL TABLE x USING fts5(a, b, content=knowledge_chunks)")
    assert kind == "external" and content == "knowledge_chunks"


def test_vtab_kind_contentless():
    kind, content = mtl.vtab_kind(
        "CREATE VIRTUAL TABLE hotspots_fts USING fts5(id UNINDEXED, title, summary,"
        " content='', tokenize='unicode61')")
    assert kind == "contentless" and content is None


def test_vtab_kind_plain():
    kind, content = mtl.vtab_kind(
        "CREATE VIRTUAL TABLE unified_fts USING fts5(title, summary)")
    assert kind == "plain" and content is None


def test_is_shadow_of_vtab_naming_rule():
    # 无库可查时按命名规则: *_fts* + 影子后缀
    assert mtl._is_shadow_of_vtab("knowledge_chunks_fts_data", set())
    assert mtl._is_shadow_of_vtab("unified_fts_idx", set())
    # 非 fts 家族的同名后缀不误伤 (如 cg_events_data 不存在但防御性验证)
    assert not mtl._is_shadow_of_vtab("cg_events_data", set())
    assert not mtl._is_shadow_of_vtab("knowledge_chunks", set())


def test_load_tables_filters_shadow_entries():
    """retention.json 里登记的 FTS5 影子表条目不应进入迁移清单。"""
    tables = [t["table"] for t in mtl.load_tables()]
    assert "knowledge_chunks_fts" in tables          # 虚表本体保留
    assert "knowledge_chunks_fts_config" not in tables
    assert "knowledge_chunks_fts_cjk_data" not in tables
    assert "hotspots_fts_idx" not in tables
    assert "unified_fts_docsize" not in tables


# ---------------------------------------------------------------------------
# 2. copy_vtab — external / contentless / plain 三形态
# ---------------------------------------------------------------------------
def test_copy_vtab_external_creates_deferred_rebuild(tmp_path: Path):
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    _attach_warm(conn, warm)

    r = mtl.copy_table(conn, "warm", "knowledge_chunks_fts", dry_run=False)
    assert r["ok"] and r.get("defer") == "rebuild"
    assert r.get("content_table") == "knowledge_chunks"

    # 虚表已建在 dst, 但数据等 rebuild
    names = _warm_names(conn)
    assert "knowledge_chunks_fts" in names

    # 模拟 run() 顺序: content 表先迁入 warm, 然后才执行延迟的 rebuild
    # (external vtab 的 rebuild 只能从同库 content 表取数 — 跨库不行)
    mtl.copy_table(conn, "warm", "knowledge_chunks", dry_run=False)
    conn.execute("INSERT INTO warm.knowledge_chunks_fts(knowledge_chunks_fts) VALUES('rebuild')")
    cnt = conn.execute("SELECT COUNT(*) FROM warm.knowledge_chunks_fts").fetchone()[0]
    assert cnt == 7
    hit = conn.execute(
        "SELECT COUNT(*) FROM warm.knowledge_chunks_fts WHERE knowledge_chunks_fts MATCH 'security'"
    ).fetchone()[0]
    assert hit == 7
    conn.close()


def test_copy_table_plain_table_copies_triggers_to_dst(tmp_path: Path):
    """external vtab 的触发器挂在 content 表上 — content 表迁走时触发器必须随迁。"""
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    _attach_warm(conn, warm)

    r = mtl.copy_table(conn, "warm", "knowledge_chunks", dry_run=False)
    assert r["ok"], r
    assert r["copied"] == 7 and r["dropped"]
    # 关键断言: 触发器已在 dst 库重建
    assert "knowledge_chunks_ai" in r.get("triggers_copied", [])
    trg = conn.execute(
        "SELECT COUNT(*) FROM warm.sqlite_master WHERE type='trigger'"
        " AND name='knowledge_chunks_ai'"
    ).fetchone()[0]
    assert trg == 1
    # 主库表已删, 触发器也已从主库清走
    assert conn.execute(
        "SELECT COUNT(*) FROM main.sqlite_master WHERE type='table' AND name='knowledge_chunks'"
    ).fetchone()[0] == 0

    # dst 侧触发器真实工作: 往 warm.knowledge_chunks 写入 → fts 自动同步
    # (表已由上面的 copy_table 迁入 warm; 触发器体内非限定名解析到触发器所在库,
    #  所以无需重写触发器体 — 但虚表必须已建好, 先迁 vtab)
    r_fts = mtl.copy_table(conn, "warm", "knowledge_chunks_fts", dry_run=False)
    assert r_fts["ok"]
    conn.execute(
        "INSERT INTO warm.knowledge_chunks VALUES (100, 'item-x', 'fresh security data', NULL, NULL)"
    )
    cnt = conn.execute("SELECT COUNT(*) FROM warm.knowledge_chunks_fts").fetchone()[0]
    # 触发器已就位: copy_table 迁移 7 行时逐行触发同步 (7) + 手动写入 (1)
    assert cnt == 8
    conn.close()


def test_copy_vtab_contentless_placeholder_only(tmp_path: Path):
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    conn.executescript("""
        CREATE TABLE hotspots (id INTEGER PRIMARY KEY, title TEXT, summary TEXT);
        INSERT INTO hotspots VALUES (1, 'alpha security', 's1'), (2, 'beta', 's2');
        CREATE VIRTUAL TABLE hotspots_fts USING fts5(
            title, summary, content='', tokenize='unicode61');
        CREATE TRIGGER hotspots_ai AFTER INSERT ON hotspots BEGIN
            INSERT INTO hotspots_fts(rowid, title, summary) VALUES (new.rowid, new.title, new.summary);
        END;
        INSERT INTO hotspots_fts(rowid, title, summary)
            SELECT rowid, title, summary FROM hotspots;
    """)
    conn.commit()
    _attach_warm(conn, warm)

    r = mtl.copy_table(conn, "warm", "hotspots_fts", dry_run=False)
    assert r["ok"] and r.get("defer") == "backfill"
    # 触发器必须留守主库 (base 表还在主库写入)
    assert "hotspots_ai" not in r.get("triggers_copied", [])
    assert conn.execute(
        "SELECT COUNT(*) FROM main.sqlite_master WHERE type='trigger' AND name='hotspots_ai'"
    ).fetchone()[0] == 1

    # run() 回灌阶段: 按 _CONTENTLESS_BACKFILL 从主库 base 表 rowid 重灌
    base, cols = mtl._CONTENTLESS_BACKFILL["hotspots_fts"]
    col_csv = ",".join(cols)
    conn.executescript(
        f"INSERT INTO warm.hotspots_fts(rowid, {col_csv}) "
        f"SELECT rowid, {col_csv} FROM main.{base}"
    )
    cnt = conn.execute("SELECT COUNT(*) FROM warm.hotspots_fts").fetchone()[0]
    assert cnt == 2
    # MATCH 可用 (contentless 可 MATCH 不可取原文列)
    hit = conn.execute(
        "SELECT COUNT(*) FROM warm.hotspots_fts WHERE hotspots_fts MATCH 'security'"
    ).fetchone()[0]
    assert hit == 1
    conn.close()


def test_copy_vtab_plain_row_copy_and_drop(tmp_path: Path):
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    conn.executescript("""
        CREATE VIRTUAL TABLE unified_fts USING fts5(title, summary);
        INSERT INTO unified_fts VALUES ('t1', 's1'), ('t2', 's2');
    """)
    conn.commit()
    _attach_warm(conn, warm)

    r = mtl.copy_table(conn, "warm", "unified_fts", dry_run=False)
    assert r["ok"] and r["vtab_kind"] == "plain"
    assert r["copied"] == 2 and r["dropped"]
    assert conn.execute(
        "SELECT COUNT(*) FROM warm.sqlite_master WHERE type='table'"
        " AND sql LIKE 'CREATE VIRTUAL TABLE%' AND name='unified_fts'"
    ).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM warm.unified_fts").fetchone()[0] == 2
    conn.close()


def test_drop_dst_orphan_shadow_tables_before_create(tmp_path: Path):
    """T6.4 孤儿事故形态: dst 有残留影子表 → 建虚表前必须先清掉。"""
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    _attach_warm(conn, warm)
    # 预埋孤儿影子表 (上次 warm 库事故的形态)
    for suf in ("_config", "_data", "_idx", "_docsize"):
        conn.execute(f"CREATE TABLE warm.\"knowledge_chunks_fts{suf}\" (x)")  # type: ignore[arg-type]
    conn.commit()

    r = mtl.copy_table(conn, "warm", "knowledge_chunks_fts", dry_run=False)
    assert r["ok"], r
    # rebuild 应当能直接跑通 (不再报 'shadow table already exists')
    mtl.copy_table(conn, "warm", "knowledge_chunks", dry_run=False)  # content 表先就位
    conn.execute("INSERT INTO warm.knowledge_chunks_fts(knowledge_chunks_fts) VALUES('rebuild')")
    cnt = conn.execute("SELECT COUNT(*) FROM warm.knowledge_chunks_fts").fetchone()[0]
    assert cnt == 7
    conn.close()


# ---------------------------------------------------------------------------
# 3. dry_run 不落库
# ---------------------------------------------------------------------------
def test_dry_run_leaves_everything_alone(tmp_path: Path):
    src = _make_src(tmp_path)
    warm = tmp_path / "warm.db"
    conn = sqlite3.connect(str(src))
    _attach_warm(conn, warm)

    r = mtl.copy_table(conn, "warm", "knowledge_chunks_fts", dry_run=True)
    assert r["ok"] and r.get("dry_run") and r.get("vtab_kind") == "external"
    assert "knowledge_chunks_fts" not in _warm_names(conn)
    # 源库也没动
    assert conn.execute(
        "SELECT COUNT(*) FROM main.sqlite_master WHERE type='table'"
        " AND name='knowledge_chunks_fts'"
    ).fetchone()[0] == 1
    conn.close()


# ---------------------------------------------------------------------------
# 4. CLI 冒烟: --dry-run 在真实 retention.json 上不炸
# ---------------------------------------------------------------------------
def test_cli_dry_run_smoke():
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "migrate_temp_layers.py"),
         "--dry-run", "--layer", "warm", "--json"],
        capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode == 0, proc.stderr[:500]
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    plan = envelope["data"]["plan"]
    # FTS5 影子表已被过滤出计划 (排除非影子家族的普通表: config 后缀有合法业务表)
    fts_family = [t for t in plan["warm_tables"] if "_fts" in t]
    assert all(not t.endswith(("_config", "_data", "_idx", "_docsize", "_content"))
               for t in fts_family), fts_family
    # 虚表本体仍在计划里
    assert "knowledge_chunks_fts" in plan["warm_tables"]
    assert "knowledge_chunks_fts_cjk" in plan["warm_tables"]
