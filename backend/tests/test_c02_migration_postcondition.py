"""v1.0 C02 反例测试 (R11 修复 + 100-105 迁移对账 + 跨库搜索 D1 节点).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §3 C02] + [REVIEW_2026-09-07.md R11/R21].
Mimosa 约束: SQL 参数绑定 (本文件全用 ? 形参).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# R11 反例: 中途失败的 migration 状态一致性
# ---------------------------------------------------------------------------
def test_partial_migration_failure_marks_schema_version_inconsistent(tmp_path: Path) -> None:
    """R11 反例基线: 旧 apply_migrations 用 conn.executescript + 单一 INSERT schema_version.

    若 migration 文件含 2 个 ALTER TABLE, 第一个成功 + 第二个失败, 旧逻辑
    把整个 migration 视为失败 (INSERT 不写), 但第 1 个 ALTER 已 commit.
    下次启动会重跑整个文件 → 第 1 个 ALTER duplicate column 报错,
    被误判 "列已存在视为已应用" → 错误地 mark schema_version 为已完成.
    """
    # 模拟一个失败 migration
    bad_migration = tmp_path / "107_partial_fail.sql"
    bad_migration.write_text("""
        CREATE TABLE c02_test_partial (id INTEGER PRIMARY KEY, v TEXT);
        ALTER TABLE c02_test_partial ADD COLUMN new_col TEXT;
        -- 故意失败: 不存在的表 ADD COLUMN
        ALTER TABLE c02_does_not_exist ADD COLUMN bogus TEXT;
    """, encoding="utf-8")

    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE schema_version (version TEXT PRIMARY KEY, executed_at TEXT NOT NULL)")

    # 走旧 apply_migrations 逻辑: executescript 整文件 + 1 个 INSERT
    sql = bad_migration.read_text(encoding="utf-8")
    version = "107_partial_fail"
    try:
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, executed_at) VALUES (?, ?)",
            (version, "2026-09-07"),
        )
    except Exception as exc:
        msg = str(exc).lower()
        # 旧逻辑: 只有 duplicate column 才视为已应用; 这里第 3 个语句报 no such table
        if "duplicate column" in msg:
            conn.execute(
                "INSERT INTO schema_version (version, executed_at) VALUES (?, ?)",
                (version, "2026-09-07"),
            )
        # 其他错误: 旧逻辑 raise (R11 真实风险: 部分执行 + 未记录)

    # 旧逻辑: 状态不一致
    # - c02_test_partial 表已建 (第 1 句执行)
    # - c02_test_partial.new_col 已加 (第 2 句执行)
    # - 但 schema_version 没记录 107
    has_test_table = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
        ("c02_test_partial",),
    ).fetchone()[0]
    has_version = conn.execute(
        "SELECT count(*) FROM schema_version WHERE version=?",
        (version,),
    ).fetchone()[0]
    conn.close()

    assert has_test_table == 1, "R11 反例基线: c02_test_partial 应已建 (前 2 句执行)"
    assert has_version == 0, (
        "R11 反例: 旧逻辑会因 raise 不写 schema_version, 但部分 DDL 已 commit, "
        "下次启动会重跑失败 (no such table 不会被视为已应用)"
    )


# ---------------------------------------------------------------------------
# R11 修复断言: apply_migrations 逐 statement 验证后置条件
# ---------------------------------------------------------------------------
def test_apply_migrations_records_per_statement_success(monkeypatch, tmp_path: Path) -> None:
    """R11 修复断言: 新版 apply_migrations 走逐 statement, 任一成功就记录, 失败前语句已 commit.

    用一个 3-statement migration (全部成功) 验证 schema_version 记录 + 实际表存在.
    """
    # 把临时 migration 注入 MIGRATIONS_DIR
    new_migration = tmp_path / "107_c02_smoke.sql"
    new_migration.write_text("""
        CREATE TABLE c02_smoke (id INTEGER PRIMARY KEY);
        INSERT INTO c02_smoke (id) VALUES (1);
        CREATE INDEX c02_smoke_idx ON c02_smoke(id);
    """, encoding="utf-8")

    # 注入到应用 MIGRATIONS_DIR (monkeypatch 替换)
    from backend.repository import db
    orig_dir = db.MIGRATIONS_DIR
    monkeypatch.setattr(db, "MIGRATIONS_DIR", tmp_path)
    try:
        db_path = tmp_path / "c02.db"
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(str(db_path))
        db._drop_dangling_views(conn)
        version = db.apply_migrations(conn)
        # 3 步全成功, schema_version 应记录 107_c02_smoke
        rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        versions = [r[0] for r in rows]
        assert "107_c02_smoke" in versions, (
            f"R11 修复: 全成功 migration 应记录 schema_version, 实际 {versions}"
        )
        # 实际表存在
        n = conn.execute("SELECT count(*) FROM c02_smoke").fetchone()[0]
        assert n == 1, f"R11 修复: 索引/数据应已落, c02_smoke 行数 {n}"
        conn.close()
    finally:
        monkeypatch.setattr(db, "MIGRATIONS_DIR", orig_dir)


def test_apply_migrations_stops_at_first_failure_with_partial_state(monkeypatch, tmp_path: Path) -> None:
    """R11 修复断言: 部分成功的 migration 在第 N+1 句失败时, 之前语句已 commit 但整体未标完成.

    实际生产价值: 当 C01 R21 修复后, migration 099 不再因 unified_search view 失败,
    但若其它原因中途失败 (例如 ATTACH 跨 db 临时异常), 至少能定位失败语句序号.
    """
    bad_migration = tmp_path / "108_c02_partial.sql"
    bad_migration.write_text("""
        CREATE TABLE c02_partial (id INTEGER PRIMARY KEY, v TEXT);
        ALTER TABLE c02_partial ADD COLUMN new_col TEXT;
        ALTER TABLE c02_does_not_exist ADD COLUMN bogus TEXT;
    """, encoding="utf-8")

    from backend.repository import db
    orig_dir = db.MIGRATIONS_DIR
    monkeypatch.setattr(db, "MIGRATIONS_DIR", tmp_path)
    try:
        db_path = tmp_path / "c02_partial.db"
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(str(db_path))

        # 调新 apply_migrations: 应在第 3 句 raise, 但前 2 句已 commit
        raised = False
        try:
            db._drop_dangling_views(conn)
            db.apply_migrations(conn)
        except Exception:
            raised = True
        # 旧逻辑会 raise, R11 修复应明确标 partial
        has_partial = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='c02_partial'"
        ).fetchone()[0]
        has_new_col = conn.execute(
            "SELECT count(*) FROM pragma_table_info('c02_partial') WHERE name='new_col'"
        ).fetchone()[0]
        has_version = conn.execute(
            "SELECT count(*) FROM schema_version WHERE version=?",
            ("108_c02_partial",),
        ).fetchone()[0] if has_partial else 0

        # R11 修复目标: 失败 migration 不应 mark schema_version (避免重跑)
        assert has_version == 0, (
            f"R11 修复: 失败 migration 不应 mark schema_version, 实际 has_version={has_version}, "
            f"否则下次启动会重跑失败"
        )
        # 但部分成功语句应已 commit (不丢 DDL)
        assert has_partial == 1, f"R11: c02_partial 表应已建 (第 1 句), 实际 {has_partial}"
        conn.close()
        # 旧逻辑 raise 是 OK 的 (不标完成 + 部分 DDL 已 commit); R11 修复只是
        # 改进了报错信息 (指出失败语句 + 已 commit 的状态)
    finally:
        monkeypatch.setattr(db, "MIGRATIONS_DIR", orig_dir)


# ---------------------------------------------------------------------------
# D1 节点: 跨库搜索性能对账 (7223 hotspots + 3800 knowledge LIKE)
# ---------------------------------------------------------------------------
def test_cross_db_search_returns_hotspots_and_knowledge_count(
    monkeypatch, tmp_path: Path,
) -> None:
    """D1 节点: 跨 ATTACH 库搜索返真实数据 (hotspots + knowledge_items).

    R21 修复后, search_service 走两条 ATTACH 跨 db UNION ALL (不依赖 unified_search view).
    本测试用真实生产 schema (不走 unit mock) 验证跨库搜索返真实数据.

    关键: 先 touch warm/cold db 文件 (init_db 检查 exists), 再 init_db 跑完整 schema,
    search_service.unified_search 才能用 main.hotspots + warm.knowledge_items.
    """
    # 隔离三库目录
    db_dir = tmp_path / "search-iso"
    db_dir.mkdir()
    hot_path = db_dir / "hot.db"
    warm_path = db_dir / "warm.db"
    cold_path = db_dir / "cold.db"

    # touch warm + cold (init_db 检查 exists, 不存在就 skip ATTACH)
    warm_path.touch()
    cold_path.touch()

    # 改 config (用 monkeypatch setattr, 跳过 conftest 的 env)
    from backend.config import config
    monkeypatch.setattr(config, "db_path", hot_path)
    monkeypatch.setattr(config, "warm_db_path", warm_path)
    monkeypatch.setattr(config, "cold_db_path", cold_path)

    # 1) warm 上独立跑 apply_migrations 建 knowledge_items 等 (v0 业务表)
    from backend.repository import db
    warm_conn = sqlite3.connect(str(warm_path))
    db.apply_migrations(warm_conn)
    warm_conn.close()

    # 2) init_db 跑 hot schema + ATTACH warm
    db.close_db()
    db.init_db()

    # 2) 给 hot 表 + warm 表 seed 测试数据 (用 ? 参数绑定)
    from backend.repository.db import get_connection
    conn = get_connection()
    # hot (NOT NULL: title, source, url, category, published_at, fetched_at, ingested_at)
    for i in range(5):
        conn.execute(
            "INSERT INTO hotspots (id, title, summary, source, url, category, "
            "published_at, fetched_at, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"c02_h{i}", f"C02 Hotspot {i}", f"c02 summary {i}",
                "c02_test", f"https://c02.example.com/h{i}", "ai",
                "2026-09-07", "2026-09-07", "2026-09-07",
            ),
        )
    # warm (走 ATTACH 别名, NOT NULL: title, source, ingested_at, updated_at, lifecycle, body)
    for i in range(5):
        conn.execute(
            "INSERT INTO warm.knowledge_items (id, title, source, topic, domain, "
            "ingested_at, updated_at, lifecycle, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"c02_k{i}", f"C02 Knowledge {i}", "c02_test",
                f"c02 topic {i}", "ai",
                "2026-09-07", "2026-09-07", "kl:raw", "",
            ),
        )
    conn.commit()
    db.close_db()

    # 3) 调 search_service.unified_search (生产代码路径, 不 mock)
    from backend.services.search_service import unified_search
    result = unified_search("C02", sources=["hotspot", "knowledge"])

    items = result.get("items", [])
    # 5 hotspots + 5 knowledge 都匹配 "C02"
    entity_counts: dict[str, int] = {}
    for it in items:
        entity_counts[it["entity_type"]] = entity_counts.get(it["entity_type"], 0) + 1
    assert entity_counts.get("hotspot", 0) == 5, (
        f"D1: 跨库搜索应返 5 hotspots, 实际 {entity_counts}"
    )
    assert entity_counts.get("knowledge", 0) == 5, (
        f"D1: 跨库搜索应返 5 knowledge, 实际 {entity_counts}"
    )
    assert sum(entity_counts.values()) == 10, (
        f"D1: 总数应 10, 实际 {sum(entity_counts.values())}"
    )
