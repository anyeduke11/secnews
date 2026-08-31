"""test_snapshot_for_retirement — 锁定 scripts/snapshot_for_retirement.py 输出契约。

锁定的契约 (见 scripts/snapshot_for_retirement.py docstring):
1. snapshot() 返回 schema_version=1 + table_counts 8 张 + wiki_files 4 个子目录
2. table_counts 包含所有 8 张核心表 (hotspots/favorites/todos/sm2_reviews/
   annotations/hotspot_tags/knowledge_concepts/knowledge_graph)
3. wiki_files 包含 items/concepts/inbox/quarantine 4 个子目录
4. total_db_rows == sum(table_counts.values())
5. total_wiki_files == sum(wiki_files.values())
6. db_size_bytes > 0
7. hotspot_version 是字符串
8. --verify 模式: baseline 缺失返回 2, 不一致返回 1, 一致返回 0

执行:
    python -m pytest backend/tests/test_snapshot_for_retirement.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "snapshot_for_retirement.py"
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"
# v0.6.3 P4 双根合并: 旧 knowledge/ 根已删, 唯一真相源 = llm-wiki-2.0
# (优先级与 backend/wiki_fs/root.py::resolve_wiki_root 一致: env 覆盖 > 新根)
DEFAULT_WIKI = Path(os.environ.get("HOTSPOT_WIKI_ROOT") or REPO_ROOT / "llm-wiki-2.0")


def _load_snapshot_module():
    """importlib 加载 scripts/snapshot_for_retirement.py。"""
    spec = importlib.util.spec_from_file_location("snapshot_for_retirement", SCRIPT)
    assert spec and spec.loader, f"cannot load {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


_SNAP_MOD = _load_snapshot_module()  # 模块级缓存, 测试运行期间复用


@pytest.fixture(scope="module")
def snapshot_data() -> dict:
    """跑一次 snapshot 拿 dict (tmp 目录避免污染 data/retirement_baseline.json)。"""
    return _SNAP_MOD.snapshot(DEFAULT_DB, DEFAULT_WIKI)


def test_schema_version_is_one(snapshot_data):
    """schema_version 必须 == 1。"""
    assert snapshot_data["schema_version"] == 1


def test_eight_core_tables(snapshot_data):
    """table_counts 必须含全部 8 张核心表。"""
    expected = {
        "hotspots",
        "favorites",
        "todos",
        "sm2_reviews",
        "annotations",
        "hotspot_tags",
        "knowledge_concepts",
        "knowledge_graph",
    }
    assert set(snapshot_data["table_counts"].keys()) == expected


def test_wiki_subdirs_four(snapshot_data):
    """wiki_files 必须含 items/concepts/inbox/quarantine。"""
    expected = {"items", "concepts", "inbox", "quarantine"}
    assert set(snapshot_data["wiki_files"].keys()) == expected


def test_total_db_rows_sums_table_counts(snapshot_data):
    """total_db_rows == sum(table_counts.values())。"""
    total = snapshot_data["total_db_rows"]
    summed = sum(snapshot_data["table_counts"].values())
    assert total == summed


def test_total_wiki_files_sums_subdirs(snapshot_data):
    """total_wiki_files == sum(wiki_files.values())。"""
    total = snapshot_data["total_wiki_files"]
    summed = sum(snapshot_data["wiki_files"].values())
    assert total == summed


def test_db_size_bytes_positive(snapshot_data):
    """db_size_bytes > 0 (DB 真的存在且非空)。"""
    assert snapshot_data["db_size_bytes"] > 0


def test_hotspot_version_string(snapshot_data):
    """hotspot_version 是字符串 (从 backend/version.py 读)。"""
    assert isinstance(snapshot_data["hotspot_version"], str)
    assert len(snapshot_data["hotspot_version"]) > 0


def test_baseline_2026_08_24_counts(snapshot_data):
    """结构验证: 确认关键表存在且行数 > 0 (活跃系统行数必然持续增长)。

    v0.4.0 修正: 原实现断言精确行数, 但线上采集管线持续入库导致
    hotspots/hotspot_tags 每日增长 → 测试永远失败。改为:
    - 关键表必须存在且 count >= 0
    - 核心知识表 (knowledge_concepts) 必须有数据 (>0)
    - schema 变更仍会被 generate_meta.py --check 和 migration 测试捕获

    v0.6.3 修正 (预存债②): wiki 根已迁 llm-wiki-2.0, items 随采集持续增长,
    精确值断言同样陈旧 → wiki 部分改下限容忍 (基线快照 4149/96 为floor)。
    """
    tc = snapshot_data["table_counts"]
    # 关键表存在性 + 非负数
    for table in ("hotspots", "favorites", "todos", "sm2_reviews",
                  "annotations", "hotspot_tags", "knowledge_concepts",
                  "knowledge_graph"):
        assert table in tc, f"table {table} missing from snapshot"
        assert tc[table] >= 0, f"table {table} has negative count"
    # 知识表必须有真实数据
    assert tc["knowledge_concepts"] > 0, "knowledge_concepts should have data"
    assert tc["hotspots"] > 0, "hotspots should have data"

    wf = snapshot_data["wiki_files"]
    # 新根基线 (2026-08-30 双根合并时点): items>=4149, concepts>=96;
    # inbox/quarantine 必须保持空 (有文件 = 流转异常)。
    assert wf["items"] >= 4149, f"items dropped below baseline: {wf['items']}"
    assert wf["concepts"] >= 96, f"concepts dropped below baseline: {wf['concepts']}"
    assert wf["inbox"] == 0
    assert wf["quarantine"] == 0


def test_table_counts_match_db_direct_query(snapshot_data):
    """双源校验: snapshot() 的行数 == 直接 sqlite3 查询。"""
    conn = sqlite3.connect(DEFAULT_DB)
    for t, n in snapshot_data["table_counts"].items():
        actual = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        assert n == actual, f"{t}: snapshot={n} but DB={actual}"
    conn.close()


def test_wiki_file_counts_match_rglob(snapshot_data):
    """双源校验: wiki 文件数 == 直接 Path.rglob 计数。"""
    for sub in ("items", "concepts", "inbox", "quarantine"):
        d = DEFAULT_WIKI / sub
        actual = sum(1 for _ in d.rglob("*.md")) if d.exists() else 0
        assert snapshot_data["wiki_files"][sub] == actual, (
            f"wiki/{sub}: snapshot={snapshot_data['wiki_files'][sub]} "
            f"but rglob={actual}"
        )


def test_dsh_verify_hint_present(snapshot_data):
    """dsh_verify_hint 字段含 node:sqlite + DatabaseSync + 8 张表名。"""
    hint = snapshot_data["dsh_verify_hint"]
    assert "DatabaseSync" in hint
    for t in ("hotspots", "favorites", "todos", "knowledge_graph"):
        assert t in hint


def test_verify_subcommand_missing_baseline(tmp_path):
    """--verify baseline 缺失时 exit code = 2。"""
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(tmp_path / "absent.json"),
        "--verify",
    ]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 2
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_verify_subcommand_writes_real_baseline_then_verifies(tmp_path):
    """--verify baseline 存在且一致时 exit code = 0。"""
    out = tmp_path / "baseline.json"

    # 1. 真写一次 baseline (非 dry-run)
    write_cmd = [
        sys.executable,
        str(SCRIPT),
        "--out", str(out),
        "--dry-run",  # 不真写盘, 但跑 snapshot
    ]
    r1 = subprocess.run(write_cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert r1.returncode == 0

    # --dry-run 不写盘, 我们手动从 snapshot() 生成 baseline
    baseline = _SNAP_MOD.snapshot(DEFAULT_DB, DEFAULT_WIKI)
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. --verify 比对 (应一致)
    # 显式传 --db/--wiki-src 与 baseline 同源: conftest autouse fixture 会把
    # HOTSPOT_WIKI_ROOT 指到 tmp, 子进程继承 env 后若不传参会读到空 wiki 目录。
    verify_cmd = [
        sys.executable,
        str(SCRIPT),
        "--db", str(DEFAULT_DB),
        "--wiki-src", str(DEFAULT_WIKI),
        "--out", str(out),
        "--verify",
    ]
    r2 = subprocess.run(verify_cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert r2.returncode == 0, f"verify failed:\nSTDOUT:\n{r2.stdout}"
    assert "all counts match" in r2.stdout
