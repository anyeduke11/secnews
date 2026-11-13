"""v0.8.8 R-17 C2.6-P0a: ``hotspots_fts`` 碎片回收 (``scripts/rebuild_fts_index.py``)。

测试意图 (WHY, 而非 WHAT):
- **大批量删行后索引必须可回收**: contentless FTS5 的 DELETE 只打墓碑不回收页,
  C2.3b 删 37,317 行后索引残留 35 MB 死页 (生产实测)。回收不是「顺便清理」,
  是**沉降管道的必需维护动作**, 否则每次沉降都让索引单调膨胀。
- **召回绝不能降级**: 重建是全量重灌, 若列定义 / 分词器 / rowid 映射任一漂移,
  检索会**静默**变差 (没有报错, 只是结果少了) —— 所以断言具体命中集与排序,
  不只断言行数相等。
- **触发器必须活下来**: 触发器在 hotspots 表上, 重建 FTS 时会短暂移除;
  漏建回 → 后续新增热点永远不进索引, 且**无任何报错**。
- **空间回收是两阶段的**: dbstat 口径的索引体积下降 != 文件变小
  (auto_vacuum=0 时释放的页只进 freelist)。脚本必须如实报告这一点,
  否则运维会误以为空间已回收。
- **check 模式物理不可写**: 缺省路径若误写库, 一次只读巡检就会改数据。

注: 小样本库无法可靠复现生产的碎片模式 (实测 30k 行小库 dbstat 仅报 16KB),
故本文件**不测碎片判据阈值**, 只测行为正确性; 阈值与真实收益由生产实测标定。
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_fts_index.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from rebuild_fts_index import _db_file_bytes, defrag, fragmentation

_HOTSPOT_COLS = (
    "id, title, summary, source, url, category, published_at, score, fetched_at, "
    "is_fallback, quality_score, quality_flags, quality_checked_at, url_check_status, "
    "ingested_at, tags, last_read_at, lifecycle, is_hidden, pick_score"
)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """建带真实 FTS + 触发器结构的库 (复刻 migrations/124 定义)。"""
    from backend.config import config
    from backend.repository import db as db_mod

    p = tmp_path / "fts.db"
    monkeypatch.setattr(config, "db_path", p)
    db_mod.close_db()
    db_mod.init_db()
    conn = sqlite3.connect(str(p))
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS hotspots_fts USING fts5("
        "id UNINDEXED, title, summary, content='', tokenize='unicode61')"
    )
    for ddl in (
        "CREATE TRIGGER IF NOT EXISTS hotspots_ai AFTER INSERT ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(rowid, title, summary) "
        "VALUES (new.rowid, new.title, IFNULL(new.summary, '')); END",
        "CREATE TRIGGER IF NOT EXISTS hotspots_ad AFTER DELETE ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary) "
        "VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, '')); END",
        "CREATE TRIGGER IF NOT EXISTS hotspots_au AFTER UPDATE ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary) "
        "VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, '')); "
        "INSERT INTO hotspots_fts(rowid, title, summary) "
        "VALUES (new.rowid, new.title, IFNULL(new.summary, '')); END",
    ):
        conn.execute(ddl)
    conn.commit()
    conn.close()
    db_mod.close_db()
    return p


def _insert(conn: sqlite3.Connection, hid: str, title: str, summary: str) -> None:
    conn.execute(
        f"INSERT INTO hotspots ({_HOTSPOT_COLS}) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (hid, title, summary, "t", f"https://x/{hid}", "security", "2026-11-01T00:00:00",
         1.0, "2026-11-01T00:00:00", 0, 90.0, '["ok"]', None, "ok",
         "2026-11-01T00:00:00", "[]", None, "active", 0, 0.0),
    )


def _query_ids(db: Path, word: str) -> list[str]:
    """走 FTS 检索路径 (含 JOIN 回查), 用于召回对比。"""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [
            r[0] for r in c.execute(
                "SELECT h.id FROM hotspots_fts f JOIN hotspots h ON h.rowid = f.rowid "
                "WHERE hotspots_fts MATCH ? ORDER BY rank LIMIT 20",
                (f'"{word}"',),
            ).fetchall()
        ]
    finally:
        c.close()


def test_defrag_preserves_rows_and_reports_both_metrics(db: Path) -> None:
    """defrag 后行数一致, 且同时报告索引体积与文件体积两个口径。

    WHY: 只报索引体积会让运维误判空间已回收 —— 实测 auto_vacuum=0 时
    索引从 35 MB 降到 3.9 MB, 但**文件纹丝不动** (要等 VACUUM)。
    """
    conn = sqlite3.connect(str(db))
    for i in range(200):
        _insert(conn, f"h{i}", f"标题{i} 安全漏洞分析", f"摘要内容 {i} 关键词 alpha")
    conn.commit()
    n_before = fragmentation(db)["hotspots_rows"]

    stats = defrag(db)

    assert stats["ok"] is True
    assert stats["after"]["counts"][0] == n_before, "hotspots 行数不得变化"
    assert stats["after"]["counts"][1] == n_before, "FTS 行数必须等于 hotspots"
    # 两个口径都要报告
    assert stats["before"]["fts_bytes"] >= stats["after"]["fts_bytes"]
    assert stats["file_bytes_before"] > 0 and stats["file_bytes_after"] > 0
    # auto_vacuum=0 时必须提示需要 VACUUM (本 fixture 建的库默认 NONE)
    if stats["before"]["auto_vacuum"] == 0:
        assert stats["needs_vacuum"] is True, "auto_vacuum=0 时应如实提示"


def test_recall_is_identical_before_and_after(db: Path) -> None:
    """召回绝不降级 —— 断言具体命中集与排序, 不只断言行数。

    WHY: 重建可能因列定义漂移 / 分词器变化 / rowid 错位而**静默**降低召回,
    没有任何报错。只断言行数相等拦不住这种退化。
    """
    conn = sqlite3.connect(str(db))
    for i in range(300):
        _insert(conn, f"r{i}", f"标题{i} 数据泄露事件", f"正文 {i} 涉及关键词 beta 与 gamma")
    conn.commit()

    words = ["beta", "gamma", "数据泄露事件"]
    before = {w: _query_ids(db, w) for w in words}
    assert all(before[w] for w in words), "种子数据应能被检索命中"

    defrag(db)

    after = {w: _query_ids(db, w) for w in words}
    assert after == before, (
        f"召回发生漂移: {[(w, len(before[w]), len(after[w])) for w in words]}"
    )


def test_triggers_survive_rebuild(db: Path) -> None:
    """触发器必须活下来 —— 漏建回则新增热点永远不进索引且无报错。"""
    conn = sqlite3.connect(str(db))
    _insert(conn, "keep1", "保留项 关键词 delta", "初始摘要")
    conn.commit()
    conn.close()

    defrag(db)

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA busy_timeout=5000")
    _insert(conn, "new1", "新增项 关键词 epsilon", "新增摘要")
    conn.commit()
    assert "new1" in _query_ids(db, "epsilon"), "INSERT 触发器未恢复 (新行不进索引)"

    conn.execute("DELETE FROM hotspots WHERE id='new1'")
    conn.commit()
    assert "new1" not in _query_ids(db, "epsilon"), "DELETE 触发器未恢复 (墓碑未生效)"

    conn.execute("UPDATE hotspots SET summary='改后摘要 zeta' WHERE id='keep1'")
    conn.commit()
    assert "keep1" in _query_ids(db, "zeta"), "UPDATE 触发器未恢复"
    conn.close()


def test_check_mode_writes_nothing(db: Path) -> None:
    """check 是只读路径 —— 缺省误写库会让一次巡检变成数据变更。

    断言用「数据不变」而非「文件字节不变」: SQLite 即使只读打开也可能
    触碰 -shm/WAL 头部元数据, 字节级比较会假阳性; 数据层面才是语义真值。
    """
    conn = sqlite3.connect(str(db))
    for i in range(30):
        _insert(conn, f"c{i}", f"标题{i}", f"摘要{i}")
    conn.commit()
    before_rows = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
    before_fts = conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0]
    before_sample = conn.execute(
        "SELECT id, title FROM hotspots ORDER BY id LIMIT 5"
    ).fetchall()
    triggers_before = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'hotspots_%'"
        )
    }
    conn.close()

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "建议回收" in proc.stdout or "无需回收" in proc.stdout

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    assert conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0] == before_rows
    assert conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0] == before_fts
    assert conn.execute(
        "SELECT id, title FROM hotspots ORDER BY id LIMIT 5"
    ).fetchall() == before_sample
    triggers_after = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'hotspots_%'"
        )
    }
    conn.close()
    assert triggers_after == triggers_before, "check 不得增删触发器"


def test_second_defrag_is_stable(db: Path) -> None:
    """二次 defrag 结果稳定: 行数不变、召回不变、不抛错。

    WHY: 若不幂等 (例如 rowid 漂移或触发器重复), 定期执行的维护任务会逐步损坏索引。
    """
    conn = sqlite3.connect(str(db))
    for i in range(120):
        _insert(conn, f"p{i}", f"标题{i} 内容", f"摘要{i} 关键词 eta")
    conn.commit()
    conn.close()

    recall_before = _query_ids(db, "eta")
    defrag(db)
    mid = _query_ids(db, "eta")
    assert mid == recall_before, "第一次 defrag 不应改变召回"

    stats2 = defrag(db)
    assert stats2["ok"] is True
    assert stats2["after"]["counts"][0] == 120
    assert stats2["after"]["counts"][1] == 120
    assert _query_ids(db, "eta") == recall_before, "第二次 defrag 不应改变召回"


def test_reclaim_skipped_when_auto_vacuum_disabled(db: Path) -> None:
    """auto_vacuum=0 时不得假装已回收文件空间。

    WHY: 这是最容易被糊弄过去的地方 —— 索引整理了但 freelist 还占着,
    若脚本报「回收 XX MB」而文件没变, 会误导容量规划。
    """
    conn = sqlite3.connect(str(db))
    for i in range(100):
        _insert(conn, f"v{i}", f"标题{i}", f"摘要{i}")
    conn.commit()
    av = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    conn.close()
    assert av == 0, "fixture 库应为 auto_vacuum=NONE"

    file_before = _db_file_bytes(db)
    stats = defrag(db, reclaim_space=True)
    file_after = _db_file_bytes(db)

    assert stats["needs_vacuum"] is True
    assert stats["reclaimed_pages"] == 0, "auto_vacuum=0 时不应声称已在线回收"
    assert file_after <= file_before, "文件不应变大"
