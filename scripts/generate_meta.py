#!/usr/bin/env python3
"""generate_meta.py — 从代码 AST 反推架构数字，供 CI 校验文档一致性。

只从代码反推，不从注释/文档读数字：

- jobs       : backend/scheduler/scheduler.py 中 add_job() 调用数
- collectors : backend/collectors/*.py 中 BaseCollector 子类数
- routers    : backend/api/__init__.py 中 include_router() 调用数
- services   : backend/services/*.py 文件数

用法::

    python scripts/generate_meta.py            # 输出 JSON 到 stdout
    python scripts/generate_meta.py --check    # 对比 docs/ARCHITECTURE.md, 不一致 exit 1

docs/ARCHITECTURE.md 中的数字由本脚本反推维护，禁止手改。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULER = ROOT / "backend" / "scheduler" / "scheduler.py"
API_INIT = ROOT / "backend" / "api" / "__init__.py"
COLLECTORS = ROOT / "backend" / "collectors"
SERVICES = ROOT / "backend" / "services"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"


def count_jobs() -> int:
    tree = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    n = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_job"
        ):
            n += 1
    return n


def count_collectors() -> int:
    n = 0
    for py in sorted(COLLECTORS.glob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = (
                        base.id if isinstance(base, ast.Name) else ""
                    )
                    if name == "BaseCollector":
                        n += 1
    return n


def count_routers() -> int:
    tree = ast.parse(API_INIT.read_text(encoding="utf-8"))
    n = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ):
            n += 1
    return n


def count_services() -> int:
    return len(list(SERVICES.glob("*.py"))) - 1  # 减去 __init__.py


def collect() -> dict:
    return {
        "jobs": count_jobs(),
        "collectors": count_collectors(),
        "routers": count_routers(),
        "services": count_services(),
    }


def parse_doc_numbers(text: str) -> dict:
    """从 ARCHITECTURE.md 提取数字（与 collect() 的 key 对应）。"""
    jobs = re.search(r"scheduler/\s*(\d+)\s*job", text)
    collectors = re.search(r"(\d+)\s*个\s*BaseCollector", text)
    routers = re.search(r"api/\s*(\d+)\s*router", text)
    services = re.search(r"services/\s*(\d+)\s*", text)
    return {
        "jobs": int(jobs.group(1)) if jobs else None,
        "collectors": int(collectors.group(1)) if collectors else None,
        "routers": int(routers.group(1)) if routers else None,
        "services": int(services.group(1)) if services else None,
    }


def check(actual: dict) -> int:
    if not ARCHITECTURE.exists():
        print(f"ERROR: {ARCHITECTURE} not found", file=sys.stderr)
        return 1
    doc = parse_doc_numbers(ARCHITECTURE.read_text(encoding="utf-8"))
    mismatches = {
        k: (actual[k], doc[k])
        for k in actual
        if doc[k] is not None and doc[k] != actual[k]
    }
    if not mismatches:
        print(f"OK: ARCHITECTURE.md matches code ({json.dumps(actual)})")
        return 0
    print("MISMATCH: docs/ARCHITECTURE.md 与代码不一致 (code vs doc):", file=sys.stderr)
    for k, (a, d) in sorted(mismatches.items()):
        print(f"  {k}: {a} vs {d}", file=sys.stderr)
    print(
        "请用脚本反推值更新 docs/ARCHITECTURE.md "
        "(此文件由 generate_meta.py 自动维护)。",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="从代码 AST 反推架构数字")
    parser.add_argument(
        "--check",
        action="store_true",
        help="对比 docs/ARCHITECTURE.md，不一致时 exit 1",
    )
    args = parser.parse_args()
    meta = collect()
    if args.check:
        return check(meta)
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
