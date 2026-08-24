"""test_dump_schema — 验证 scripts/dump_schema.py 输出契约。

锁定的契约 (见 scripts/dump_schema.py docstring):
1. dump() 返回 schema_version=1 + totals + tables + fts_groups + fks_flat + ddl_objects
2. totals.business_tables >= 60 (锁定 2026-08-24: 62)
3. totals.fts5_groups == 3 (hotspots_fts / unified_fts / wiki_items_fts)
4. FTS5 shadow 严格按 suffix (_config/_data/_docsize/_idx/_content) 匹配
   (不能用 prefix 匹配, 否则 hotspots_ad/ai/au trigger 会污染)
5. tables.json 每张 business table 含 columns/pk/indexes/fks
6. fks.json 含 from_table/from/to_table/to
7. ddl.sql 含全部 CREATE TABLE/INDEX/VIEW/TRIGGER 语句, 可被 sqlite3.exec() 重建
8. fts_groups.json 含 shadow_tables 数组 (4-5 元素)

执行:
    python -m pytest backend/tests/test_dump_schema.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dump_schema.py"
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"


def _load_module():
    spec = importlib.util.spec_from_file_location("dump_schema", SCRIPT)
    assert spec and spec.loader, f"cannot load {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    mod.REPO_ROOT = REPO_ROOT  # 让 relative_to 工作
    return mod


_MOD = _load_module()


@pytest.fixture(scope="module")
def dump_data() -> dict:
    """跑一次 dump 拿 dict (不写盘)。"""
    return _MOD.dump(DEFAULT_DB)


def test_schema_version_is_one(dump_data):
    assert dump_data["schema_version"] == 1


def test_totals_business_tables_at_least_60(dump_data):
    """business_tables 必须 >= 60 (锁定 2026-08-24: 62)。"""
    totals = dump_data["totals"]
    assert totals["business_tables"] >= 60, (
        f"business_tables dropped to {totals['business_tables']}, "
        f"expected >= 60. schema changed?"
    )


def test_totals_fts5_groups_is_three(dump_data):
    """FTS5 虚表组必须 == 3: hotspots_fts / unified_fts / wiki_items_fts。"""
    assert dump_data["totals"]["fts5_groups"] == 3
    names = [g["name"] for g in dump_data["fts_groups"]]
    assert "hotspots_fts" in names
    assert "unified_fts" in names
    assert "wiki_items_fts" in names


def test_fts5_shadow_no_trigger_leak(dump_data):
    """FTS5 shadow 表**严格**按后缀匹配, 不能含 hotspots_ad/ai/au 等 trigger。"""
    triggers_should_not_leak = {"hotspots_ad", "hotspots_ai", "hotspots_au"}
    for g in dump_data["fts_groups"]:
        for shadow in g["shadow_tables"]:
            assert shadow not in triggers_should_not_leak, (
                f"FTS5 group {g['name']!r} leaked trigger {shadow!r} "
                f"into shadow_tables; prefix matching bug"
            )


def test_fts5_shadow_counts_match_real_db(dump_data):
    """双源校验: FTS5 shadow 表数 == 直接 sqlite 查询。"""
    conn = sqlite3.connect(DEFAULT_DB)
    fts5_suffixes = ("_config", "_data", "_docsize", "_idx", "_content")
    main_tables = [
        "hotspots_fts",
        "unified_fts",
        "wiki_items_fts",
    ]
    for main in main_tables:
        # 直接 DB 查询该 FTS5 组的 shadow
        real_shadow = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE ?",
                (main + "_%",),
            ).fetchall()
            if any(row[0] == main + sfx for sfx in fts5_suffixes)
        }
        dump_shadow = set(
            next(
                g["shadow_tables"]
                for g in dump_data["fts_groups"]
                if g["name"] == main
            )
        )
        assert real_shadow == dump_shadow, (
            f"{main}: DB has {real_shadow}, dump has {dump_shadow}"
        )
    conn.close()


def test_tables_json_every_business_table_has_columns(dump_data):
    """tables.json 每张 business table 必须有 columns (list) + pk (list) + indexes (list) + fks (list)。"""
    for name, detail in dump_data["tables"].items():
        assert "columns" in detail and isinstance(detail["columns"], list)
        assert "pk" in detail and isinstance(detail["pk"], list)
        assert "indexes" in detail and isinstance(detail["indexes"], list)
        assert "fks" in detail and isinstance(detail["fks"], list)
        assert len(detail["columns"]) >= 1, f"{name} has no columns"
        # columns[i] 应是 dict with name/type/notnull/pk_position
        for c in detail["columns"]:
            assert "name" in c and "type" in c
            assert "pk_position" in c


def test_fks_flat_matches_sum_of_per_table_fks(dump_data):
    """fks_flat 总数 == 各表 fks 数之和。"""
    per_table = sum(len(t["fks"]) for t in dump_data["tables"].values())
    flat = len(dump_data["fks_flat"])
    assert per_table == flat
    # 而且每条 fk 都含 from_table + from + to_table + to
    for fk in dump_data["fks_flat"]:
        assert "from_table" in fk
        assert "table" in fk and "from" in fk


def test_ddl_objects_complete(dump_data):
    """ddl_objects 必须含全部 4 类 (table/index/view/trigger) 且 sql 非空。"""
    by_type: dict[str, int] = {}
    for o in dump_data["ddl_objects"]:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
        assert o["sql"], f"{o['name']} has empty sql"
    assert by_type.get("table", 0) >= 60
    assert by_type.get("index", 0) >= 50
    assert by_type.get("trigger", 0) >= 1
    assert by_type.get("view", 0) >= 1


def test_dumped_at_is_iso8601(dump_data):
    """dumped_at 必须是 ISO8601 字符串。"""
    from datetime import datetime

    parsed = datetime.fromisoformat(dump_data["dumped_at"])
    assert parsed.tzinfo is not None, f"no tzinfo: {dump_data['dumped_at']}"


def test_db_path_is_relative(dump_data):
    """db_path 必须是相对路径 (跨机迁移友好)。"""
    assert not Path(dump_data["db_path"]).is_absolute()


def test_hotspot_version_string(dump_data):
    """hotspot_version 是字符串 (从 backend/version.py)。"""
    assert isinstance(dump_data["hotspot_version"], str)
    assert len(dump_data["hotspot_version"]) > 0


def test_ddl_sql_rebuilds_schema(tmp_path):
    """render_ddl 生成的 SQL 必须能被 sqlite3.exec() 重建全部业务表。"""
    # 1. 生成 DDL
    obj = _MOD.dump(DEFAULT_DB)
    ddl_text = _MOD.render_ddl(obj)

    # 2. 在 tmp 空 DB 里执行 DDL
    test_db = tmp_path / "test.db"
    conn = sqlite3.connect(test_db)
    conn.executescript(ddl_text)

    # 3. 验证: 业务表都建出来了
    new_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected_business = set(obj["tables"].keys())
    missing = expected_business - new_tables
    assert not missing, f"DDL failed to create tables: {missing}"
    conn.close()


def test_cli_sql_only(tmp_path):
    """--sql-only 仅写 ddl.sql。"""
    out_dir = tmp_path / "schema_only"
    cmd = [sys.executable, str(SCRIPT), "--out", str(out_dir), "--sql-only"]
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    assert (out_dir / "ddl.sql").exists()
    assert not (out_dir / "tables.json").exists()
    assert not (out_dir / "fks.json").exists()
    assert not (out_dir / "fts_groups.json").exists()


def test_cli_full_creates_all_four_files(tmp_path):
    """完整模式生成 ddl.sql + tables.json + fks.json + fts_groups.json。"""
    out_dir = tmp_path / "schema_full"
    cmd = [sys.executable, str(SCRIPT), "--out", str(out_dir)]
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"

    ddl = (out_dir / "ddl.sql").read_text(encoding="utf-8")
    tables = json.loads((out_dir / "tables.json").read_text(encoding="utf-8"))
    fks = json.loads((out_dir / "fks.json").read_text(encoding="utf-8"))
    fts = json.loads((out_dir / "fts_groups.json").read_text(encoding="utf-8"))

    # ddl.sql 含 PRAGMA foreign_keys + CREATE
    assert "PRAGMA foreign_keys = OFF" in ddl
    # hotspots 表使用双引号包裹 (sqlite 原样 dump): CREATE TABLE "hotspots"
    assert 'CREATE TABLE "hotspots"' in ddl
    # FTS5 用 VIRTUAL TABLE
    assert "CREATE VIRTUAL TABLE hotspots_fts USING fts5" in ddl
    assert "CREATE INDEX" in ddl
    # tables.json totals 一致
    assert tables["totals"]["business_tables"] >= 60
    # fks.json 含 fks 数组
    assert "fks" in fks and len(fks["fks"]) >= 1
    # fts_groups.json 含 groups
    assert "groups" in fts and len(fts["groups"]) == 3
