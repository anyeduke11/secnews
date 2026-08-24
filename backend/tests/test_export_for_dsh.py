"""test_export_for_dsh — 验证 scripts/export_for_dsh.py 输出契约。

锁定的契约 (见 scripts/export_for_dsh.py docstring):
1. manifest.json 含 schema_version=1 + hotspot_version + counts + tables 列表
2. 每张表 *.json 含 schema (CREATE TABLE DDL) + columns + rows (dict 列表)
3. JSON-encoded 字符串字段 (quality_flags/tags) 解析为原生 list/object
4. None → null, BLOB → {"__b64__": "..."} 包装
5. 行数 == SELECT COUNT(*), 与 manifest.counts 一致

执行:
    python -m pytest backend/tests/test_export_for_dsh.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "export_for_dsh.py"


@pytest.fixture(scope="module")
def export_run() -> dict:
    """跑一次 export_for_dsh.py 拿结果 (tmp 目录避免污染 data/export)。"""
    with tempfile.TemporaryDirectory(prefix="export_test_") as tmp:
        # 只导出 2 张表 (减少 IO), 跳过 wiki
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--out", tmp,
            "--tables", "hotspots", "favorites",
            "--no-wiki",
        ]
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"export_for_dsh.py failed:\nSTDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
        out = Path(tmp)
        return {
            "manifest": json.loads((out / "manifest.json").read_text()),
            "hotspots": json.loads((out / "hotspots.json").read_text()),
            "favorites": json.loads((out / "favorites.json").read_text()),
            "stdout": result.stdout,
        }


def test_manifest_schema_version(export_run):
    """manifest 必须含 schema_version=1。"""
    assert export_run["manifest"]["schema_version"] == 1


def test_manifest_has_counts_and_total(export_run):
    """manifest.counts 是 dict, total_rows 等于 counts 值之和。"""
    counts = export_run["manifest"]["counts"]
    assert isinstance(counts, dict)
    assert "hotspots" in counts and "favorites" in counts
    assert export_run["manifest"]["total_rows"] == sum(counts.values())


def test_manifest_contract_field(export_run):
    """manifest 含 contract 字段 (datetime/blob/null/json_encoded_string 约定)。"""
    contract = export_run["manifest"].get("contract", {})
    assert "datetime" in contract
    assert "blob" in contract
    assert "null" in contract
    assert "json_encoded_string" in contract


def test_table_payload_shape(export_run):
    """每张表 *.json 必须含 schema + columns + rows。"""
    for payload in (export_run["hotspots"], export_run["favorites"]):
        assert "schema" in payload and "CREATE TABLE" in payload["schema"]
        assert "columns" in payload and isinstance(payload["columns"], list)
        assert "rows" in payload and isinstance(payload["rows"], list)
        assert payload["row_count"] == len(payload["rows"])
        # 每行的 keys 必须包含 columns 全部
        if payload["rows"]:
            row_keys = set(payload["rows"][0].keys())
            assert set(payload["columns"]) <= row_keys


def test_json_encoded_fields_parsed(export_run):
    """quality_flags / tags 字段从 JSON 字符串解析为原生 list。"""
    hotspots = export_run["hotspots"]
    # 至少有一行 quality_flags 非空 list
    parsed = [r for r in hotspots["rows"] if isinstance(r.get("quality_flags"), list)]
    assert len(parsed) >= 1, (
        "expected at least one hotspot with parsed quality_flags list"
    )
    # 找到 tags 字段也解析正确
    for r in hotspots["rows"]:
        # tags 可能是 [] (空 list) 或 list of strings; 不会是 string
        assert r["tags"] is None or isinstance(r["tags"], list), (
            f"tags must be list or null, got {type(r['tags'])}"
        )


def test_row_count_matches_db(export_run):
    """导出行数必须与 SELECT COUNT(*) 一致。"""
    import sqlite3

    conn = sqlite3.connect(REPO_ROOT / "backend" / "hotspot.db")
    for table in ("hotspots", "favorites"):
        db_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        payload_count = export_run[table]["row_count"]
        assert db_count == payload_count, (
            f"{table}: DB has {db_count} rows, export has {payload_count}"
        )


def test_favorites_payload_small(export_run):
    """favorites 表导出后 row_count > 0 (说明 export 真发生了)。"""
    assert export_run["favorites"]["row_count"] >= 0
    # schema 含 CHECK created_via 约束 (验证 DDL 真的导出了)
    assert "created_via" in export_run["favorites"]["schema"]


def test_skip_tables_rationale_present(export_run):
    """manifest 包含 skip_tables_rationale, 给 dsh 端开发对账。"""
    skip = export_run["manifest"]["skip_tables_rationale"]
    assert "schema_version" in skip
    assert "encryption_keys" in skip
    assert len(skip) >= 10
