"""collection_repo 单测 (R2 收缩批 — 采集域四表写路径唯一化).

覆盖四表 repo 方法的关键语义 (业务编排由宿主测试覆盖, 见
test_pipeline_p1_fix.py / test_fingerprint.py / test_liveness_vs_usefulness.py /
test_catchup_watchdog.py — repo 下沉后那些用例逐字保留, 本文件只补
repo 自身的直测):

  1. collection_runs insert_running_run (status='running', 计数字面量 0)
  2. collection_runs update_run_finished (running → 终态五列)
  3. collection_runs insert_run (老路径整行 fallback)
  4. collection_runs DB CHECK status 枚举 (repo 不拦截, 库兜底)
  5. mark_run_failed_watchdog rowcount=1 + 字面量 error_msg
  6. mark_run_failed_watchdog 对已 finished 行 rowcount=0 (IS NULL 守卫)
  7. crawler_runs INSERT 往返 (九列逐字)
  8. raw_items INSERT 往返 + fetched_at DB default datetime('now')
  9. content_fingerprints INSERT OR IGNORE 幂等 (rowcount 1 → 0, UNIQUE hotspot_id)
  10. content_fingerprints signed-64 simhash 往返 (负值不丢符号)
  11. conn 注入生效 (:memory: 注入连接, 不走 get_connection)
  12. repo 不吞 OperationalError (表缺失兜底语义归宿主)
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.repository.collection_repo import CollectionRepository
from backend.repository.db import get_connection

STARTED = "2026-09-13T00:00:00+00:00"
FINISHED = "2026-09-13T00:01:00+00:00"


@pytest.fixture()
def repo(temp_db) -> CollectionRepository:  # temp_db 只为建表 (migration 001/041/043/055)
    return CollectionRepository()


def _hotspot(hotspot_id: str = "hs-r1") -> None:
    """content_fingerprints.hotspot_id FK REFERENCES hotspots(id) — 先落宿主行."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO hotspots (id, title, source, url, category, "
        "published_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (hotspot_id, "R2 收缩批测试条目", "unit-test",
         f"https://example.com/{hotspot_id}", "ai", STARTED, STARTED),
    )


# ---------------------------------------------------------------------------
# collection_runs
# ---------------------------------------------------------------------------
def test_insert_running_run_roundtrip(repo) -> None:
    conn = get_connection()
    run_id = repo.insert_running_run("ai", STARTED)
    assert run_id > 0
    row = conn.execute(
        "SELECT category, started_at, finished_at, status, item_count, "
        "fallback_count, error_msg FROM collection_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert tuple(row) == ("ai", STARTED, None, "running", 0, 0, None)


def test_update_run_finished_terminal_state(repo) -> None:
    """Phase 8 主路径: 起始 'running' 行 → 终态 (finished_at/status/计数/error)."""
    conn = get_connection()
    run_id = repo.insert_running_run("security", STARTED)
    repo.update_run_finished(
        run_id, FINISHED, "partial", item_count=7, fallback_count=2,
        error_msg=None,
    )
    row = conn.execute(
        "SELECT finished_at, status, item_count, fallback_count, error_msg "
        "FROM collection_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert tuple(row) == (FINISHED, "partial", 7, 2, None)


def test_update_run_finished_error_msg_and_failed(repo) -> None:
    conn = get_connection()
    run_id = repo.insert_running_run("tech", STARTED)
    repo.update_run_finished(
        run_id, FINISHED, "failed", 0, 0, error_msg="HTTPError: 503",
    )
    row = conn.execute(
        "SELECT status, error_msg FROM collection_runs WHERE id = ?", (run_id,),
    ).fetchone()
    assert tuple(row) == ("failed", "HTTPError: 503")


def test_insert_run_fallback_full_row(repo) -> None:
    """老路径: 起始行 INSERT 失败时一次性整行 INSERT (七列)."""
    conn = get_connection()
    run_id = repo.insert_run(
        "finance", STARTED, FINISHED, "success",
        item_count=12, fallback_count=0, error_msg=None,
    )
    assert run_id > 0
    row = conn.execute(
        "SELECT category, started_at, finished_at, status, item_count, "
        "fallback_count, error_msg FROM collection_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert tuple(row) == ("finance", STARTED, FINISHED, "success", 12, 0, None)


def test_collection_run_status_check_enforced_by_db(repo) -> None:
    """DB CHECK (status 枚举) — repo 不拦截, 由库兜底."""
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_run("ai", STARTED, FINISHED, "bogus", 0, 0, None)


def test_mark_run_failed_watchdog_sets_literal_error(repo) -> None:
    """watchdog 标孤儿: rowcount=1 + status/error_msg 字面量逐字落库."""
    conn = get_connection()
    run_id = repo.insert_running_run("ai", STARTED)
    assert repo.mark_run_failed_watchdog(run_id, FINISHED) == 1
    row = conn.execute(
        "SELECT finished_at, status, error_msg FROM collection_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    assert tuple(row) == (FINISHED, "failed", "watchdog: timeout after 600s")


def test_mark_run_failed_watchdog_skips_finished_run(repo) -> None:
    """``AND finished_at IS NULL`` 守卫: 已终态行不再被覆写, rowcount=0."""
    run_id = repo.insert_run(
        "ai", STARTED, FINISHED, "success", 5, 0, None,
    )
    assert repo.mark_run_failed_watchdog(run_id, FINISHED) == 0
    row = get_connection().execute(
        "SELECT status FROM collection_runs WHERE id = ?", (run_id,),
    ).fetchone()
    assert row[0] == "success"  # 终态未被 watchdog 覆写


# ---------------------------------------------------------------------------
# crawler_runs
# ---------------------------------------------------------------------------
def test_insert_crawler_run_roundtrip(repo) -> None:
    conn = get_connection()
    repo.insert_crawler_run(
        source_id="tech:rss_demo", category="tech",
        started_at=STARTED, finished_at=FINISHED, status="partial",
        fetched_count=40, accepted_count=0, error_msg="", duration_ms=1500,
    )
    row = conn.execute(
        "SELECT source_id, category, started_at, finished_at, status, "
        "fetched_count, accepted_count, error_msg, duration_ms "
        "FROM crawler_runs WHERE source_id = 'tech:rss_demo'",
    ).fetchone()
    assert tuple(row) == (
        "tech:rss_demo", "tech", STARTED, FINISHED, "partial",
        40, 0, "", 1500,
    )


# ---------------------------------------------------------------------------
# raw_items
# ---------------------------------------------------------------------------
def test_insert_raw_item_roundtrip_with_db_default_fetched_at(repo) -> None:
    conn = get_connection()
    repo.insert_raw_item(
        item_id="hs-raw-1", source_id="sec:rss_ok",
        title="t", url="https://example.com/x", summary="s",
        content_hash="0123456789abcdef", published_at=STARTED,
    )
    row = conn.execute(
        "SELECT item_id, source_id, title, url, summary, content_hash, "
        "published_at, fetched_at FROM raw_items WHERE item_id = 'hs-raw-1'",
    ).fetchone()
    assert tuple(row)[:7] == (
        "hs-raw-1", "sec:rss_ok", "t", "https://example.com/x",
        "s", "0123456789abcdef", STARTED,
    )
    # fetched_at 由语句内 datetime('now') 兜底 — 非空即语句生效
    assert row[7] is not None and str(row[7]) != ""


# ---------------------------------------------------------------------------
# content_fingerprints
# ---------------------------------------------------------------------------
def test_insert_fingerprint_idempotent_ignore(repo) -> None:
    """UNIQUE(hotspot_id) 冲突 → INSERT OR IGNORE 幂等命中, rowcount 1 → 0."""
    _hotspot("hs-fp-1")
    conn = get_connection()
    assert repo.insert_fingerprint("hs-fp-1", 12345, "https://e.com/1", "标题") == 1
    assert repo.insert_fingerprint("hs-fp-1", 99999, "https://e.com/1", "标题") == 0
    count = conn.execute(
        "SELECT COUNT(*) FROM content_fingerprints WHERE hotspot_id = 'hs-fp-1'",
    ).fetchone()[0]
    assert count == 1


def test_insert_fingerprint_signed_64_roundtrip(repo) -> None:
    """signed-64 simhash (负值) 原样落库 — _to_signed_64 的存储契约."""
    _hotspot("hs-fp-2")
    repo.insert_fingerprint("hs-fp-2", -(1 << 62), "https://e.com/2", "负值指纹")
    row = get_connection().execute(
        "SELECT simhash FROM content_fingerprints WHERE hotspot_id = 'hs-fp-2'",
    ).fetchone()
    assert row[0] == -(1 << 62)


# ---------------------------------------------------------------------------
# 注入 / 边界
# ---------------------------------------------------------------------------
def test_injected_conn_is_used_over_fallback() -> None:
    """注入 :memory: 连接 → 写入落在注入连接, 不触碰 get_connection."""
    mem = sqlite3.connect(":memory:")
    try:
        mem.execute(
            "CREATE TABLE collection_runs ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " category TEXT NOT NULL, started_at TEXT NOT NULL,"
            " finished_at TEXT, status TEXT NOT NULL,"
            " item_count INTEGER NOT NULL DEFAULT 0,"
            " fallback_count INTEGER NOT NULL DEFAULT 0, error_msg TEXT)"
        )
        bare = CollectionRepository(mem)
        run_id = bare.insert_running_run("github", STARTED)
        assert run_id > 0
        # 写入在注入连接上可见 (同连接读, 无需 commit — 语句已执行)
        assert mem.execute(
            "SELECT COUNT(*) FROM collection_runs"
        ).fetchone()[0] == 1
    finally:
        mem.close()


def test_missing_table_raises_operational_error() -> None:
    """注入无表的 :memory: 连接 → OperationalError 原样上抛, 不静默返 0."""
    mem = sqlite3.connect(":memory:")
    try:
        bare = CollectionRepository(mem)
        with pytest.raises(sqlite3.OperationalError):
            bare.insert_running_run("ai", STARTED)
        with pytest.raises(sqlite3.OperationalError):
            bare.insert_fingerprint("hs-x", 1, "https://e.com", "t")
    finally:
        mem.close()
