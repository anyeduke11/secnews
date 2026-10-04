#!/usr/bin/env python3
"""check_warm_refs.py — warm.X 裸引用 CI 门禁 (v0.8.6 P1-8, 审计 F2-4 提前)。

§4.3 规则③ 落地: warm 库表名必须经 ``warm_table()`` / ``knowledge_items_table()``
accessor 解析 (声明式路由, 单一真相源), 仓内不得出现裸 ``warm.<table>``
SQL 字面量引用 — 单库测试模式下裸名解析失败即静默断供 (E15 历史教训:
``no such table: warm.hotspots`` 439 次)。

扫描规则 (面向"真 SQL 引用", 误报最小化):
- 扫描对象: backend/ 与 scripts/ 下 *.py (排除 tests/ 与本文件);
- 命中形态: SQL 关键词 (FROM/JOIN/INTO/UPDATE) 后跟 ``warm.<ident>``,
  含跨行拼接字符串的行 (按行扫描, 不做完整 SQL 解析 — 与 CI grep 同级);
- 白名单 (合法消费方, 见 WARM_SCHEMA_GOVERNORS):
  * ``backend/repository/db.py`` — accessor 本体 + warm 域治理 (self-heal/
    悬空 FK 重建/索引点火), 这类代码的职责就是按 schema 操作 warm 库;
  * 测试文件 (tests/) — warm 语义测试断言表真实存在, 裸名是测试意图;
  * docstring/注释行 (strip 后以 # 开头) — 文档提及不构成运行时引用。

用法:
    python scripts/check_warm_refs.py           # 违规非零退出
    python scripts/check_warm_refs.py --format json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# accessor 本体 + warm 域治理代码 (合法按 schema 操作 warm 库的唯一文件)
WARM_SCHEMA_GOVERNORS = {"backend/repository/db.py"}

# 一次性运维/迁移脚本: 直连 warm.db 文件 (sqlite3.connect 路径) 而非运行时
# ATTACH 路径 — 裸 warm. 是脚本意图 (工具失效不构成运行时静默断供面)。
# 新增运行时消费方时不得加入此表。
_ONEOFF_MAINTENANCE_SCRIPTS = {
    "scripts/audit_dead_source_triage.py",
    "scripts/migrate_temp_layers.py",
}

SCAN_ROOTS = ("backend", "scripts")
SQL_REF_RE = re.compile(
    r"(?:FROM|JOIN|INTO|UPDATE)\s+[\`'\"]?warm\.[A-Za-z_][A-Za-z0-9_]*",
    re.IGNORECASE,
)


def _strip_docstring_lines(source: str) -> list[str]:
    """抹掉模块/类/函数 docstring 字面量 — 文档提及不构成运行时引用。

    轻量方案: 用 ast 解析提取 docstring 行号集合 (准确且无正则边界坑);
    ast 解析失败 (语法错) 则退化为原文行 (让门禁在坏文件上保守报错)。
    """
    try:
        import ast

        tree = ast.parse(source)
    except SyntaxError:
        return source.splitlines()
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is None:
                continue
            seg = ast.get_source_segment(source, node.body[0])
            if seg is None:
                continue
            start = node.body[0].lineno
            doc_lines.update(range(start, start + seg.count("\n") + 1))
    lines = source.splitlines()
    return ["" if (i + 1) in doc_lines else ln
            for i, ln in enumerate(lines)]
# docstring/纯注释行不构成运行时引用
_COMMENT_RE = re.compile(r"^\s*#")


def _is_exempt(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if rel in WARM_SCHEMA_GOVERNORS or rel in _ONEOFF_MAINTENANCE_SCRIPTS:
        return True
    parts = rel.split("/")
    return "tests" in parts or path.name == "check_warm_refs.py"


def scan() -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if _is_exempt(path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            lines = _strip_docstring_lines(source)
            for lineno, line in enumerate(lines, 1):
                if _COMMENT_RE.match(line):
                    continue
                m = SQL_REF_RE.search(line)
                if m:
                    violations.append({
                        "file": path.relative_to(REPO_ROOT).as_posix(),
                        "line": str(lineno),
                        "match": m.group(0),
                        "text": line.strip()[:160],
                    })
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    violations = scan()
    if args.format == "json":
        print(json.dumps({
            "violations": violations,
            "count": len(violations),
            "allowlist": sorted(WARM_SCHEMA_GOVERNORS),
        }, ensure_ascii=False, indent=2))
    else:
        if violations:
            print(f"FAIL: {len(violations)} 个 warm.X 裸 SQL 引用 "
                  f"(须经 warm_table()/knowledge_items_table() accessor):\n")
            for v in violations:
                print(f"  {v['file']}:{v['line']}  {v['match']}")
                print(f"      {v['text']}")
            print("\n修法: 表名改走 warm_table(name) / knowledge_items_table() "
                  "(backend/repository/db.py); 测试文件与 db.py 治理代码豁免。")
        else:
            print("OK: warm.X 裸 SQL 引用 = 0 (accessor 白名单除外)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
