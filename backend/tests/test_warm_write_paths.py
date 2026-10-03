"""warm 写路径回归 — v0.8.6 P0-7 / 审计 E15。

E15 两个生产写失败:
1. ``_write_fingerprints failed: no such table: warm.hotspots`` (439 次) —
   migrate_temp_layers 把 ``REFERENCES hotspots(id)`` 原样拷入 warm, SQLite
   FK 只在子表所在 schema 内解析父表 (跨库 FK 不支持), 连接级
   foreign_keys=ON 下 warm 侧 INSERT 全数失败 → 指纹补写断供、跨轮去重
   静默失效。
2. ``write quality log failed: no such table: quality_check_logs`` —
   裸名路由依赖环境探测, warm 遗失窗口期写失败不留有效痕迹。

锁定:
- ``_fix_warm_dangling_fks`` 自愈: 悬空 FK 剥离 / 数据与 id 保留 /
  索引重建 / AUTOINCREMENT 续号 / 幂等 / warm 内合法 FK 不动
- ``warm_table`` accessor: main 优先 / warm 限定 / 单库裸名
- 两条写路径 (指纹补写 / 门禁日志) 在 warm 模式真实落库
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.repository import db as db_mod
from backend.repository.quality_repo import QualityLogRepository
from backend.services import collection_dedup

# 与生产 warm.content_fingerprints 逐字同构 (migration 043 DDL 原样拷贝态)
_FP_DDL_WITH_DANGLING_FK = """
CREATE TABLE content_fingerprints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id    TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    simhash       BIGINT NOT NULL,
    url_canonical TEXT NOT NULL,
    title_norm    TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(hotspot_id)
)"""

_QCL_DDL = """
CREATE TABLE quality_check_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    gate_name       TEXT NOT NULL,
    passed          INTEGER NOT NULL,
    score_deduction INTEGER NOT NULL DEFAULT 0,
    flags           TEXT NOT NULL DEFAULT '[]',
    reason          TEXT,
    error_msg       TEXT,
    checked_at      TEXT NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'loose'
)"""


@pytest.fixture
def warm_env(tmp_path: Path):
    """隔离环境: main (hotspots) + warm (带悬空 FK 的指纹表 + 门禁日志表)。

    复刻生产形态 — hotspots 在 main, content_fingerprints / quality_check_logs
    在 warm, 前者 DDL 带指向 main 侧表的跨库 FK (E15 根因态)。
    """
    main_db = tmp_path / "hotspot.db"
    warm_db = tmp_path / "hotspot-warm.db"

    m = sqlite3.connect(main_db)
    m.execute(
        "CREATE TABLE hotspots (id TEXT PRIMARY KEY, title TEXT, url TEXT,"
        " source TEXT, category TEXT, published_at TEXT, fetched_at TEXT)"
    )
    m.executemany(
        "INSERT INTO hotspots VALUES (?,?,?,?,?,?,?)",
        [
            ("hs-1", "Existing One", "https://example.com/1", "t", "ai",
             "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z"),
            ("hs-2", "Existing Two", "https://example.com/2", "t", "ai",
             "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z"),
        ],
    )
    m.commit()
    m.close()

    w = sqlite3.connect(warm_db)
    w.execute(_FP_DDL_WITH_DANGLING_FK)
    w.execute(
        "CREATE INDEX idx_fp_simhash ON content_fingerprints(simhash)")
    w.execute(
        "CREATE INDEX idx_fp_url_canonical ON content_fingerprints(url_canonical)")
    w.executemany(
        "INSERT INTO content_fingerprints"
        " (hotspot_id, simhash, url_canonical, title_norm) VALUES (?,?,?,?)",
        [("hs-1", 111, "https://example.com/1", "existing one"),
         ("hs-2", 222, "https://example.com/2", "existing two")],
    )
    w.execute(_QCL_DDL)
    # 对照组: warm 内部合法 FK (父表在 warm) — 自愈不得触碰
    w.execute("CREATE TABLE fake_parent (id INTEGER PRIMARY KEY)")
    w.execute(
        "CREATE TABLE warm_child ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " pid INTEGER NOT NULL REFERENCES fake_parent(id))")
    w.execute("INSERT INTO fake_parent VALUES (1)")
    w.execute("INSERT INTO warm_child (pid) VALUES (1)")
    w.commit()
    w.close()
    return main_db, warm_db


def _attached_conn(main_db: Path, warm_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(main_db, isolation_level=None)
    conn.row_factory = sqlite3.Row  # 与 get_connection 一致 (r["col"] 访问)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"ATTACH DATABASE '{warm_db}' AS warm")
    return conn


def _make_item(id_: str, title: str = "Test Article") -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source="test",
        url=f"https://example.com/{id_}",
        category=Category.AI,
        published_at=now,
        fetched_at=now,
    )


# ---------------------------------------------------------------------------
# _fix_warm_dangling_fks — E15 活跃故障的根治
# ---------------------------------------------------------------------------
class TestFixWarmDanglingFks:
    def test_rebuild_strips_fk_and_unblocks_insert(self, warm_env):
        """自愈后: FK 清零、数据/id/索引保留、新 INSERT 不再抛
        ``no such table: warm.hotspots`` (E15 生产 439 次的直接复现)。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            # 根因态复现: foreign_keys=ON 下 bare INSERT 命中 warm 表,
            # FK 父表 hotspots 只在 main → OperationalError
            with pytest.raises(sqlite3.OperationalError, match=r"warm\.hotspots"):
                conn.execute(
                    "INSERT INTO content_fingerprints"
                    " (hotspot_id, simhash, url_canonical, title_norm)"
                    " VALUES ('hs-1', 333, 'https://x.example/3', 'x')")

            db_mod._fix_warm_dangling_fks(conn)

            # FK 剥离
            assert conn.execute(
                'PRAGMA warm.foreign_key_list("content_fingerprints")'
            ).fetchall() == []
            # 数据与显式 id 保留
            rows = conn.execute(
                "SELECT id, hotspot_id FROM warm.content_fingerprints"
                " ORDER BY id").fetchall()
            assert [r[0] for r in rows] == [1, 2]
            assert rows[0][1] == "hs-1"
            # 索引随表重建
            idx = conn.execute(
                "SELECT name FROM warm.sqlite_master WHERE type='index'"
                " AND tbl_name = 'content_fingerprints' AND sql IS NOT NULL"
            ).fetchall()
            assert {r[0] for r in idx} == {"idx_fp_simhash", "idx_fp_url_canonical"}
            # DDL 不再含 REFERENCES
            ddl = conn.execute(
                "SELECT sql FROM warm.sqlite_master"
                " WHERE name = 'content_fingerprints'").fetchone()[0]
            assert "REFERENCES" not in ddl.upper()

            # E15 验收主断言: 同一连接下写入成功 + AUTOINCREMENT 续号
            cur = conn.execute(
                "INSERT INTO content_fingerprints"
                " (hotspot_id, simhash, url_canonical, title_norm)"
                " VALUES ('hs-new', 333, 'https://x.example/3', 'x')")
            assert cur.lastrowid == 3
        finally:
            conn.close()

    def test_idempotent(self, warm_env):
        """重复自愈 no-op — init_db 每次启动都跑, 不得反复重建。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            db_mod._fix_warm_dangling_fks(conn)
            ddl_after_first = conn.execute(
                "SELECT sql FROM warm.sqlite_master"
                " WHERE name = 'content_fingerprints'").fetchone()[0]
            rows_after_first = conn.execute(
                "SELECT COUNT(*) FROM warm.content_fingerprints").fetchone()[0]

            db_mod._fix_warm_dangling_fks(conn)
            ddl_after_second = conn.execute(
                "SELECT sql FROM warm.sqlite_master"
                " WHERE name = 'content_fingerprints'").fetchone()[0]
            rows_after_second = conn.execute(
                "SELECT COUNT(*) FROM warm.content_fingerprints").fetchone()[0]

            assert ddl_after_first == ddl_after_second
            assert rows_after_first == rows_after_second
        finally:
            conn.close()

    def test_valid_warm_internal_fk_untouched(self, warm_env):
        """父表在 warm 内的合法 FK 不是悬空 FK — 不重建 (语义保留)。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            ddl_before = conn.execute(
                "SELECT sql FROM warm.sqlite_master"
                " WHERE name = 'warm_child'").fetchone()[0]
            db_mod._fix_warm_dangling_fks(conn)
            ddl_after = conn.execute(
                "SELECT sql FROM warm.sqlite_master"
                " WHERE name = 'warm_child'").fetchone()[0]
            assert ddl_after == ddl_before
            assert "REFERENCES" in ddl_after.upper()
            assert conn.execute(
                "SELECT COUNT(*) FROM warm_child").fetchone()[0] == 1
        finally:
            conn.close()

    def test_noop_without_warm(self, tmp_path: Path):
        """单库模式 (无 ATTACH) → no-op 不抛。"""
        conn = sqlite3.connect(tmp_path / "single.db")
        try:
            db_mod._fix_warm_dangling_fks(conn)  # 不应抛
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# warm_table accessor — 声明式路由语义
# ---------------------------------------------------------------------------
class TestWarmTableAccessor:
    def test_warm_only_table_qualified(self, warm_env):
        """main 无此表 + warm 已 ATTACH → warm.<name> (生产落位)。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            assert db_mod.warm_table("quality_check_logs", conn) == \
                "warm.quality_check_logs"
            assert db_mod.warm_table("content_fingerprints", conn) == \
                "warm.content_fingerprints"
        finally:
            conn.close()

    def test_main_first_when_both_exist(self, warm_env):
        """main 也有同名表 → 裸名 (镜像 SQLite 解析序, 读写不分叉)。"""
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            conn.execute(_QCL_DDL)  # main 侧也建 quality_check_logs
            assert db_mod.warm_table("quality_check_logs", conn) == \
                "quality_check_logs"
        finally:
            conn.close()

    def test_bare_without_warm(self, tmp_path: Path):
        """warm 未 ATTACH (单库/测试常态) → 裸名。"""
        conn = sqlite3.connect(tmp_path / "single.db")
        try:
            assert db_mod.warm_table("quality_check_logs", conn) == \
                "quality_check_logs"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 两条生产写路径 — warm 模式端到端
# ---------------------------------------------------------------------------
class _StubLogger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


class TestWritePathsInWarmMode:
    def test_write_fingerprints_fails_then_heals(self, warm_env):
        """E15 叙事闭环: 悬空 FK 下 write_fingerprints 尽力而为返回 0
        (不阻塞采集, 但指纹断供); 自愈后同批写入成功, 且下轮
        dedup_items 按 URL 拒重 — 跨轮去重能力恢复。
        """
        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            log = _StubLogger()
            with patch.object(
                collection_dedup, "get_connection", return_value=conn
            ):
                # 根因态: 补写全军覆没 (生产 439 次的每批形态)
                assert collection_dedup.write_fingerprints(
                    [_make_item("hs-3")], log) == 0

                db_mod._fix_warm_dangling_fks(conn)

                # 自愈后: 写入成功, 指纹落 warm
                assert collection_dedup.write_fingerprints(
                    [_make_item("hs-3")], log) == 1
                assert conn.execute(
                    "SELECT COUNT(*) FROM warm.content_fingerprints"
                    " WHERE hotspot_id = 'hs-3'").fetchone()[0] == 1

                # 跨轮去重恢复: 同 URL 二次采集被拒
                assert collection_dedup.dedup_items([_make_item("hs-3")], log) == []
        finally:
            conn.close()

    def test_quality_log_write_lands_in_warm(self, warm_env):
        """门禁审计日志走 accessor: 生产落位 warm.quality_check_logs,
        写入/回读/24h 汇总全链路在 warm 侧完成 (E15 第二写路径)。"""
        from backend.domain.collection import GateResult

        main_db, warm_db = warm_env
        conn = _attached_conn(main_db, warm_db)
        try:
            with patch(
                "backend.repository.quality_repo.get_connection",
                return_value=conn,
            ):
                repo = QualityLogRepository()
                repo.write_log(
                    "item-9",
                    GateResult(gate_name="schema", passed=True, score_deduction=0),
                )
                # main 侧无此表 — 行必落在 warm (accessor 路由生效)
                assert conn.execute(
                    "SELECT COUNT(*) FROM main.sqlite_master"
                    " WHERE name = 'quality_check_logs'").fetchone()[0] == 0
                assert conn.execute(
                    "SELECT COUNT(*) FROM warm.quality_check_logs"
                    " WHERE item_id = 'item-9'").fetchone()[0] == 1
                assert repo.list_for_item("item-9")[0]["gate_name"] == "schema"
                assert repo.summary_24h()["schema"]["total"] == 1
        finally:
            conn.close()
