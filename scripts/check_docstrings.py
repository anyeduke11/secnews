"""v0.7 Batch ⑧ D7: 模块级 docstring 强制检查 (CI 可用).

扫描 backend/services / backend/api / backend/repository 下所有非 __init__.py
非 _ 开头文件, 验证首行是 docstring. 缺失或不合规 → 退出 1.

注意:
- 排除 tests/ (测试文件无强制)
- 排除 _ 开头的私有模块
- 排除 __init__.py (包初始化通常不需要)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("backend/services", "backend/api", "backend/repository")
EXCLUDE_SUFFIXES = ("__init__.py",)
EXCLUDE_PREFIXES = ("_",)

DD = chr(34) * 3   # """
SS = chr(39) * 3   # '''


def _has_docstring(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        return False
    for prefix in (DD, SS, "r" + DD, "r" + SS):
        if first.startswith(prefix):
            return True
    return False


def main() -> int:
    total = 0
    missing: list[Path] = []
    for target in TARGETS:
        for path in (ROOT / target).rglob("*.py"):
            if path.name in EXCLUDE_SUFFIXES:
                continue
            if path.name.startswith(EXCLUDE_PREFIXES):
                continue
            total += 1
            if not _has_docstring(path):
                missing.append(path.relative_to(ROOT))

    if missing:
        print(f"ERROR: {len(missing)}/{total} 模块缺 docstring (CI 红线):")
        for p in missing:
            print(f"  - {p}")
        return 1
    print(f"OK: 全部 {total} 模块均有 docstring")
    return 0


if __name__ == "__main__":
    sys.exit(main())
