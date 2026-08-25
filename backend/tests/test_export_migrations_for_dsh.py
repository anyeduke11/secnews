"""test_export_migrations_for_dsh — 验证 scripts/export_migrations_for_dsh.py 输出契约。

锁定的契约 (见 scripts/export_migrations_for_dsh.py docstring):
1. collect() 返回 entries 列表, 每个含 filename/size_bytes/line_count/sha256/keywords
2. 排序按文件名升序 (001_init.sql < 002_quality.sql < ...)
3. 文件数 == 源目录 .sql 文件数 (动态推导, 不随新增迁移失效)
4. total_bytes == 源目录总字节
5. manifest.json 含 schema_version=1 + totals + files
6. README.md 含关键词分布表 + 文件清单 + dsh 端消费指引
7. .sql 文件**字节级一致**复制到 out (sha256 校验)

执行:
    python -m pytest backend/tests/test_export_migrations_for_dsh.py -v
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "export_migrations_for_dsh.py"
DEFAULT_SRC = REPO_ROOT / "backend" / "repository" / "migrations"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_migrations_for_dsh", SCRIPT)
    assert spec and spec.loader, f"cannot load {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    mod.REPO_ROOT = REPO_ROOT  # 让 relative_to 工作
    return mod


_MOD = _load_module()


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return _MOD.collect(DEFAULT_SRC)


def test_entries_count_matches_disk(entries):
    """entries 数量 == 源目录 .sql 文件数 (动态推导)。"""
    disk_count = sum(1 for p in DEFAULT_SRC.iterdir() if p.suffix == ".sql")
    assert len(entries) == disk_count
    assert len(entries) >= 65, (
        f"only {len(entries)} migrations found, expected >= 65 (spec line 198)"
    )


def test_entries_sorted_by_filename(entries):
    """entries 必须按文件名升序 (dsh 端按顺序 exec)。"""
    filenames = [e["filename"] for e in entries]
    assert filenames == sorted(filenames)
    # 首尾与源目录实际首尾一致 (新增迁移无需改本测试)
    disk_names = sorted(p.name for p in DEFAULT_SRC.iterdir() if p.suffix == ".sql")
    assert disk_names[0].startswith("001_")
    assert filenames[0] == disk_names[0]
    assert filenames[-1] == disk_names[-1]


def test_each_entry_has_required_keys(entries):
    """每个 entry 必须含 filename/size_bytes/line_count/sha256/keywords。"""
    required = {"filename", "size_bytes", "line_count", "sha256", "keywords"}
    for e in entries:
        missing = required - set(e.keys())
        assert not missing, f"{e['filename']} missing keys: {missing}"
        assert isinstance(e["sha256"], str) and len(e["sha256"]) == 64
        assert e["size_bytes"] > 0
        assert e["line_count"] > 0
        assert isinstance(e["keywords"], dict)


def test_sha256_matches_disk(entries):
    """每个 entry 的 sha256 必须等于磁盘上对应文件的实际 sha256。"""
    for e in entries:
        path = DEFAULT_SRC / e["filename"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == e["sha256"], (
            f"{e['filename']}: manifest sha256={e['sha256']}, disk sha256={actual}"
        )


def test_keywords_distribution_has_creates(entries):
    """关键词统计应含 CREATE TABLE / CREATE INDEX (hotspot 主流 DDL)。"""
    all_kw: dict[str, int] = {}
    for e in entries:
        for kw, cnt in e["keywords"].items():
            all_kw[kw] = all_kw.get(kw, 0) + cnt
    assert all_kw.get("CREATE TABLE", 0) >= 50, f"too few CREATE TABLE: {all_kw}"
    assert all_kw.get("CREATE INDEX", 0) >= 50, f"too few CREATE INDEX: {all_kw}"


def test_manifest_shape(entries):
    """manifest dict 必须含 schema_version=1 + totals + files。"""
    manifest = _MOD.render_manifest(entries, DEFAULT_SRC, "0.5.0")
    assert manifest["schema_version"] == 1
    assert "dumped_at" in manifest and "T" in manifest["dumped_at"]
    assert manifest["totals"]["files"] == len(entries)
    assert manifest["totals"]["total_bytes"] == sum(e["size_bytes"] for e in entries)
    assert manifest["totals"]["total_lines"] == sum(e["line_count"] for e in entries)
    assert manifest["files"] == entries
    assert isinstance(manifest["totals"]["keywords"], dict)


def test_readme_contains_dsh_hints():
    """render_readme 必须含 dsh 端消费指引 + 关键词表。"""
    entries = _MOD.collect(DEFAULT_SRC)
    manifest = _MOD.render_manifest(entries, DEFAULT_SRC, "0.5.0")
    readme = _MOD.render_readme(manifest)
    assert "dsh 端消费指引" in readme or "dsh" in readme
    assert "CREATE TABLE" in readme
    assert "001_init.sql" in readme  # 文件清单头
    assert "cp -r" in readme or "迁移" in readme


def test_cli_dry_run():
    """--dry-run 跑通 + 输出含 totals + 不写盘。"""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    assert "files" in r.stdout
    assert "DRY_RUN" in r.stdout


def test_cli_full_creates_all_outputs(tmp_path):
    """完整模式: 复制 .sql + manifest.json + README.md。"""
    out_dir = tmp_path / "mig_full"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"

    # .sql 复制数量 == 源目录数量 (动态推导, 新增迁移无需改本测试)
    expected_count = sum(1 for p in DEFAULT_SRC.iterdir() if p.suffix == ".sql")
    copied_sql = sorted(p for p in out_dir.iterdir() if p.suffix == ".sql")
    assert len(copied_sql) == expected_count, (
        f"expected {expected_count} .sql, got {len(copied_sql)}"
    )

    # manifest.json 可解析
    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists()
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["totals"]["files"] == expected_count

    # README.md 存在
    assert (out_dir / "README.md").exists()


def test_cli_sql_only_skips_metadata(tmp_path):
    """--sql-only 只复制 .sql, 不写 manifest/README。"""
    out_dir = tmp_path / "mig_sql_only"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir), "--sql-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    assert not (out_dir / "manifest.json").exists()
    assert not (out_dir / "README.md").exists()
    # .sql 仍在 (数量 == 源目录, 动态推导)
    sql_files = [p for p in out_dir.iterdir() if p.suffix == ".sql"]
    expected_count = sum(1 for p in DEFAULT_SRC.iterdir() if p.suffix == ".sql")
    assert len(sql_files) == expected_count


def test_copied_sql_byte_identical_to_source(tmp_path):
    """复制后的 .sql 必须字节级一致 (sha256 == 源 sha256)。"""
    out_dir = tmp_path / "mig_verify"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"failed:\n{r.stderr}"

    for p in out_dir.iterdir():
        if p.suffix != ".sql":
            continue
        src_hash = hashlib.sha256((DEFAULT_SRC / p.name).read_bytes()).hexdigest()
        dst_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        assert src_hash == dst_hash, f"{p.name}: src != dst"
