"""v0.6 Phase 6 commit 1 — scripts/migrate_wiki.py CLI 单测.

锁定三件事:
  1. fresh 路径: src 有 N 个新条目, dest 为空 → migrate=N, skipped=0
  2. 幂等路径: 重复 apply → migrate=0, skipped=N (现有条目不覆盖)
  3. dry-run 路径: 0 写盘, 报告 would_migrate + would_skip 与 apply 一致

每个测试都把 src/dest 切到 tmp_path 临时目录, 不污染真实 llm-wiki-2.0/.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.wiki_fs.store import WikiFs


def _make_src(src: Path, n: int = 5) -> None:
    """Build a fake source wiki root with `n` items under src/items/."""
    items = src / "items"
    items.mkdir(parents=True, exist_ok=True)
    fs = WikiFs(str(src))
    for i in range(1, n + 1):
        fs.write_item(
            f"src-{i:03d}",
            {
                "fm": {"id": f"src-{i:03d}", "title": f"Source Item {i}", "lifecycle": "kl:raw"},
                "body": f"Body of source item {i}.",
            },
        )


def _make_dest(dest: Path) -> None:
    """Init dest dir structure (CLI requires --dest to exist; subdirs lazy)."""
    dest.mkdir(parents=True, exist_ok=True)


def test_fresh_migrate(tmp_path: Path) -> None:
    """Fresh destination: src 全量 migrate 进来."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _make_src(src, n=5)
    _make_dest(dest)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/migrate_wiki.py",
            "--src",
            str(src),
            "--dest",
            str(dest),
            "--report",
            str(tmp_path / "report.json"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "migrate=5" in result.stdout
    assert "skip=0" in result.stdout

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "apply"
    assert report["result"]["migrated"] == 5
    assert report["result"]["skipped"] == 0
    assert report["result"]["errors"] == 0

    # All items landed in dest.
    fs = WikiFs(str(dest))
    for i in range(1, 6):
        doc = fs.read_item(f"src-{i:03d}")
        assert doc is not None, f"src-{i:03d} not migrated"
        assert doc["fm"]["title"] == f"Source Item {i}"


def test_idempotent_migrate(tmp_path: Path) -> None:
    """Second run with same src/dest: 0 migrate, all skipped."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _make_src(src, n=5)
    _make_dest(dest)

    cwd = Path(__file__).resolve().parents[2]
    cli = [".venv/bin/python", "scripts/migrate_wiki.py", "--src", str(src), "--dest", str(dest)]

    # First run: migrate all.
    r1 = subprocess.run(cli + ["--report", str(tmp_path / "r1.json")], cwd=cwd, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert "migrate=5" in r1.stdout

    # Second run: 0 migrate, 5 skip.
    r2 = subprocess.run(cli + ["--report", str(tmp_path / "r2.json")], cwd=cwd, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "migrate=0" in r2.stdout
    assert "skip=5" in r2.stdout

    r2_report = json.loads((tmp_path / "r2.json").read_text(encoding="utf-8"))
    assert r2_report["result"]["migrated"] == 0
    assert r2_report["result"]["skipped"] == 5


def test_dry_run_no_writes(tmp_path: Path) -> None:
    """--dry-run 不写盘: dest 应保持空, 报告含 would_* 字段."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _make_src(src, n=5)
    _make_dest(dest)

    cwd = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            ".venv/bin/python",
            "scripts/migrate_wiki.py",
            "--src",
            str(src),
            "--dest",
            str(dest),
            "--dry-run",
            "--report",
            str(tmp_path / "report.json"),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "migrate=5" in result.stdout
    assert "skip=0" in result.stdout

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "dry-run"
    assert report["result"]["would_migrate"] == 5
    assert report["result"]["would_skip"] == 0

    # 关键断言: dest items/ 应保持空 (0 写盘).
    fs = WikiFs(str(dest))
    assert fs.list_ids() == [], f"dry-run wrote to dest: {fs.list_ids()}"