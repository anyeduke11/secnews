#!/usr/bin/env python3
"""DEV_LOG ↔ git 提交差集核对 (只读, 无副作用).

以 ``DEV-xxxx`` 为唯一键做三向核对:

1. 已对账 — DEV_LOG 有条目, git log 有提交引用同一编号
2. documented_only — DEV_LOG 有条目, git log 无提交引用 → 未提交(会话进行中) 或提交信息漏写编号
3. unlogged_commit — git 提交引用了编号, DEV_LOG 无对应条目 → 台账漏记 (真实漂移)

用法::

    python scripts/check_devlog_coverage.py               # 人类可读
    python scripts/check_devlog_coverage.py --format json # 机器消费
    python scripts/check_devlog_coverage.py --limit 20    # 明细行数上限

退出码: 0 = 无 unlogged_commit; 1 = 存在 unlogged_commit; 2 = DEV_LOG / git 不可用。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_LOG = ROOT / "DEV_LOG.md"

# DEV_LOG 条目标题: `## [DEV-0383] fix: ...`
_ENTRY = re.compile(r"^##\s+\[DEV-(\d+)\]", re.MULTILINE)
# 提交信息内引用: `(DEV-0383)` / `DEV-0383`
_REF = re.compile(r"DEV-(\d+)")


def _devlog_ids() -> tuple[list[str], list[str]]:
    """返回 (按出现顺序的编号列表, 重复出现的编号)."""
    text = DEV_LOG.read_text(encoding="utf-8")
    ids = [f"DEV-{m}" for m in _ENTRY.findall(text)]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return ids, dupes


def _commits() -> list[tuple[str, str]]:
    """返回 [(短 hash, 提交标题)]; 非 git 仓库 / git 缺失时抛 RuntimeError."""
    out = subprocess.run(
        ["git", "log", "--format=%h\x1f%s", "--no-color"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            rows.append((sha, subject))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="DEV_LOG 与 git 提交差集核对 (只读)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--limit", type=int, default=10, help="各分区明细行数上限")
    args = parser.parse_args()

    if not DEV_LOG.exists():
        print(f"DEV_LOG 缺失: {DEV_LOG}", file=sys.stderr)
        return 2
    try:
        commits = _commits()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"git log 不可用: {exc}", file=sys.stderr)
        return 2

    logged, dupes = _devlog_ids()
    logged_set = set(logged)

    commit_ids: dict[str, list[str]] = {}
    for sha, subject in commits:
        for num in set(_REF.findall(subject)):
            commit_ids.setdefault(f"DEV-{num}", []).append(sha)

    reconciled = [i for i in logged if i in commit_ids]
    documented_only = [i for i in logged if i not in commit_ids]
    unlogged = [i for i in commit_ids if i not in logged_set]
    unlogged_rows = [{"dev_id": i, "commits": commit_ids[i][:5]} for i in sorted(unlogged)]

    payload = {
        "devlog_entries": len(logged),
        "devlog_range": [min(logged), max(logged)] if logged else [],
        "commits_scanned": len(commits),
        "reconciled": len(reconciled),
        "documented_only": documented_only,
        "unlogged_commits": unlogged_rows,
        "duplicate_entries": dupes,
        "exit_code": 1 if unlogged else 0,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return int(payload["exit_code"])

    print("DEV_LOG ↔ git 差集核对")
    print(f"  DEV_LOG 条目 {len(logged)}  (范围 {payload['devlog_range'][0]} ~ "
          f"{payload['devlog_range'][1]})" if logged else "  DEV_LOG 无条目")
    print(f"  git 提交扫描 {len(commits)} 条, 命中编号 {len(commit_ids)} 个")
    print("-" * 52)
    print(f"[OK]   已对账 {len(reconciled)}")
    print(f"[WARN] 仅台账未提交 {len(documented_only)}"
          + (f" → {', '.join(documented_only[:args.limit])}" if documented_only else ""))
    print(f"[FAIL] 提交未落台账 {len(unlogged)}")
    for row in unlogged_rows[:args.limit]:
        print(f"       {row['dev_id']}: {', '.join(row['commits'])}")
    if dupes:
        print(f"[WARN] DEV_LOG 重复编号 {len(dupes)} → {', '.join(dupes[:args.limit])}")
    print("-" * 52)
    print("结论: " + ("存在提交未落台账, 补 DEV_LOG 条目" if unlogged else "无台账漏记"))
    return 0 if not unlogged else 1


if __name__ == "__main__":
    sys.exit(main())