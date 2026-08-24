#!/usr/bin/env python3
"""generate_meta.py — 从代码 AST 反推架构数字 + core 路径分类 + draft 规划登记校验。

主要职责：

1. **架构数字反推** (CI 校验 docs/ARCHITECTURE.md 与代码 AST 一致)
2. **core 路径分类 (--classify)** (v0.6+): 读取仓库根 core.include / core.exclude
   (gitignore-style glob), 对传入路径逐个判定 core|non-core;
   任一命中即整体为 core (CI 据此走完整门)。core.include 缺失时回退到
   v0.4.3 core/extension 软分层隐式约定的核心目录, 打一次性 WARN。
3. **draft 规划登记校验 (v0.6+)**: 扫描 docs/*.md 顶部 frontmatter,
   对 status: draft 的规划文档校验 docs/ARCHITECTURE.md 是否含
   backticked ``docs/<filename>.md`` 引用; 缺失即 CI reject。
   目的: 让规划文档与代码实现处于同一 review 视野。

用法::

    python scripts/generate_meta.py                          # 架构数字 JSON 到 stdout
    python scripts/generate_meta.py --check                  # 对比 docs/ARCHITECTURE.md, 不一致 exit 1
    python scripts/generate_meta.py --drafts-only            # 仅输出 draft 规划清单 (JSON)
    python scripts/generate_meta.py --classify <path>...     # 单路径分类, 输出 core|non-core
    git diff --name-only origin/main | python scripts/generate_meta.py --classify --batch
                                                             # 批量: 任一 core → exit 0 (core), 否则 exit 1 (non-core)

docs/ARCHITECTURE.md 中的数字由本脚本反推维护, 禁止手改。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULER = ROOT / "backend" / "scheduler" / "scheduler.py"
API_INIT = ROOT / "backend" / "api" / "__init__.py"
COLLECTORS = ROOT / "backend" / "collectors"
SERVICES = ROOT / "backend" / "services"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
DOCS_DIR = ROOT / "docs"

# frontmatter 字段匹配 (key: value 每行一条)。
_FRONTMATTER_FIELD = re.compile(
    r"^\s*(?P<key>[a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(?P<val>.*?)\s*$",
    re.MULTILINE,
)
# ARCHITECTURE.md 中 backticked 的 docs/<filename>.md 引用。
_ARCH_DOC_REF = re.compile(r"`(docs/[^`\s]+\.md)`")

CORE_INCLUDE = ROOT / "core.include"
CORE_EXCLUDE = ROOT / "core.exclude"

# 回退: core.include 缺失时使用的硬编码核心目录
# 这是 v0.4.3 core/extension 软分层的隐式约定, 与 core.include 头部注释一致
_FALLBACK_CORE_DIRS: tuple[str, ...] = (
    "backend/services/",
    "backend/domain/",
    "backend/repository/",
    "backend/collectors/",
    "backend/parsers/",
    "backend/quality/",
    "backend/scheduler/",
    "backend/security/",
    "backend/api/",
    "backend/core/",
    "backend/extensions/",
    "frontend/src/",
)


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
                    name = base.id if isinstance(base, ast.Name) else ""
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


# --------------------------------------------------------------------------- #
# Draft 规划登记校验 (v0.6+ 增量)
# --------------------------------------------------------------------------- #


def parse_frontmatter(path: Path) -> dict:
    """读取文档顶部 YAML frontmatter, 返回 key→value 字典。

    零依赖逐行解析:
      - 第一行必须是 ``---`` (YAML 起始)
      - 直至下一个 ``---`` 之间的 ``key: value`` 行被收集
      - 字段值一律按 ``;`` 拆分为列表 (单值→1 元素列表),
        这样调用方拿到的类型稳定。
      - 无 frontmatter 或解析失败 → 空 dict。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}
    fm: dict = {}
    for raw in lines[1:end]:
        m = _FRONTMATTER_FIELD.match(raw)
        if not m:
            continue
        key = m.group("key").lower()
        val = [v.strip() for v in m.group("val").split(";") if v.strip()]
        fm[key] = val
    return fm


def is_draft_planning_doc(path: Path) -> bool:
    """文档头部 frontmatter 是否声明 status: draft。"""
    fm = parse_frontmatter(path)
    status = fm.get("status", [])
    if isinstance(status, list):
        return "draft" in status
    return status == "draft"


def iter_planning_docs(docs_dir: Path = DOCS_DIR) -> Iterable[Path]:
    """遍历 docs/*.md, 仅返回含 frontmatter 的 .md。"""
    for path in sorted(docs_dir.glob("*.md")):
        if parse_frontmatter(path):
            yield path


def _first_scalar(values: list, default: str = "") -> str:
    """frontmatter 标量字段 (target_version/phase) 取首元素。"""
    return values[0] if isinstance(values, list) and values else default


def collect_planning_drafts(docs_dir: Path = DOCS_DIR) -> list:
    """收集所有 draft 状态的规划文档, 按文件名字母序返回。"""
    drafts = []
    for path in sorted(set(iter_planning_docs(docs_dir))):
        if not is_draft_planning_doc(path):
            continue
        fm = parse_frontmatter(path)
        drafts.append(
            {
                "filename": path.name,
                "relpath": f"docs/{path.name}",
                "target_version": _first_scalar(fm.get("target_version", [])),
                "related_code": fm.get("related_code", []),
                "depends_on": fm.get("depends_on", []),
                "phase": _first_scalar(fm.get("phase", [])),
            }
        )
    return drafts


def parse_architecture_registry(arch_text: str) -> set:
    """从 ARCHITECTURE.md 中提取所有 backticked docs 引用集合。

    不限定特定表格/章节 —— 任何以反引号包围的 docs/<name>.md
    形式均视作已登记。这样 §9.1 表格、行文中的引用均自动覆盖。
    """
    return set(_ARCH_DOC_REF.findall(arch_text))


def check_drafts_registration(arch_text: str, drafts: list) -> list:
    """返回未在 ARCHITECTURE.md 中登记的 draft 文档 relpath 列表。"""
    registry = parse_architecture_registry(arch_text)
    return [d["relpath"] for d in drafts if d["relpath"] not in registry]


def check(actual: dict) -> int:
    if not ARCHITECTURE.exists():
        print(f"ERROR: {ARCHITECTURE} not found", file=sys.stderr)
        return 1
    arch_text = ARCHITECTURE.read_text(encoding="utf-8")

    # 1) 架构数字 vs 文档声明
    doc = parse_doc_numbers(arch_text)
    mismatches = {
        k: (actual[k], doc[k]) for k in actual if doc[k] is not None and doc[k] != actual[k]
    }

    # 2) draft 文档登记校验
    drafts = collect_planning_drafts()
    missing = check_drafts_registration(arch_text, drafts)

    failed = False
    if not mismatches:
        print(f"OK: ARCHITECTURE.md matches code ({json.dumps(actual)})")
    else:
        print(
            "MISMATCH: docs/ARCHITECTURE.md 与代码不一致 (code vs doc):",
            file=sys.stderr,
        )
        for k, (a, d) in sorted(mismatches.items()):
            print(f"  {k}: {a} vs {d}", file=sys.stderr)
        print(
            "请用脚本反推值更新 docs/ARCHITECTURE.md (此文件由 generate_meta.py 自动维护)。",
            file=sys.stderr,
        )
        failed = True

    if missing:
        print(
            f"WARN: {len(missing)} 个 draft 规划文档未在 ARCHITECTURE.md 登记:",
            file=sys.stderr,
        )
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
        print(
            "  修复方式: 在 docs/ARCHITECTURE.md §9.1 表格加一行 backtick 引用,\n"
            "  或在该文档 frontmatter 删除 status: draft。",
            file=sys.stderr,
        )
        failed = True
    elif drafts:
        print(f"OK: draft 规划登记校验通过 ({len(drafts)} 个 draft 文档全部登记)")

    return 1 if failed else 0


# ---------------------------------------------------------------------------
# core 路径分类 (--classify)
#
# 配置源: 仓库根 core.include / core.exclude (gitignore-style glob)
# 回退:   core.include 缺失时使用硬编码核心目录 (_FALLBACK_CORE_DIRS),
#         并向 stderr 打 WARN (一次性, 提醒显式声明)。
# 匹配:   前导 '/' = 锚定仓库根; 末尾 '/' = 目录前缀; '**' = 跨段; '*' = 非 /;
#         不支持 negation '!' (本仓库配置文件未使用)。
# ---------------------------------------------------------------------------

_GLOB_RESERVED = re.compile(r"[\\^$.|+(){}\[\]]")


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """gitignore-style glob → 锚定到段的 regex (path 用 posix 风格, 无前导 /)。

    尾随 '/' 视为"目录前缀"标记: pattern 等于 path 或 path 以 pattern + '/' 起始。
    """
    is_dir = pattern.endswith("/")
    if is_dir:
        pattern = pattern[:-1]
    parts = pattern.split("/")
    out: list[str] = []
    for p in parts:
        if p == "**":
            out.append(".*")
            continue
        # 段内: 转义所有 regex 保留字符后再还原通配符
        sub = _GLOB_RESERVED.sub(lambda m: "\\" + m.group(0), p)
        sub = re.sub(r"\\\*", "[^/]*", sub)
        sub = re.sub(r"\\\?", "[^/]", sub)
        out.append(sub)
    body = "/".join(out)
    # (?:^|/)...(?:$|/) 同时支持: 路径首段 / 段末边界
    return re.compile(r"(?:^|/)" + body + r"(?:$|/)")


def _parse_glob_file(path: Path) -> list[str]:
    """解析 gitignore-style 文件; 跳过 '#' 注释与空行; 不支持 negation '!'。

    保留尾随 '/' 作为"目录前缀"标记 (gitignore 语义), 由 _glob_to_regex 检测。
    """
    if not path.exists():
        return []
    patterns: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        # lstrip 去除行首缩进与 '\r' (保留尾随 '/' 作为目录标记)
        line = raw.lstrip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        # 锚定仓库根 (前导 '/') 时去掉, _glob_to_regex 已隐式锚段
        if line.startswith("/"):
            line = line[1:]
        if line:
            patterns.append(line)
    return patterns


def _matches_any(patterns: Sequence[str], path: str) -> bool:
    """path 是否命中任一 glob。path 用 posix 风格, 无前导 '/'。"""
    if not path:
        return False
    norm = path.lstrip("/")
    for pat in patterns:
        if _glob_to_regex(pat).search(norm):
            return True
    return False


def load_core_patterns() -> tuple[list[str], list[str], bool]:
    """读取 core.include / core.exclude; 返回 (includes, excludes, fell_back)。

    fell_back=True 表示 core.include 缺失, 调用方按需打 WARN。
    """
    if CORE_INCLUDE.exists():
        return _parse_glob_file(CORE_INCLUDE), _parse_glob_file(CORE_EXCLUDE), False
    return list(_FALLBACK_CORE_DIRS), _parse_glob_file(CORE_EXCLUDE), True


def classify_paths(
    paths: Iterable[str],
) -> tuple[bool, list[tuple[str, str]], bool]:
    """对 paths 中每个 posix 路径判定 core|non-core。

    返回:
      has_core   - 任一命中 include (且未被 exclude) 即 True
      per_path   - [(path, 'core'|'non-core'), ...] (保持输入顺序, 去空行)
      fell_back  - 是否因 core.include 缺失而走了回退
    """
    includes, excludes, fell_back = load_core_patterns()
    per_path: list[tuple[str, str]] = []
    has_core = False
    for raw in paths:
        norm = raw.strip().lstrip("/")
        if not norm:
            continue
        is_core = _matches_any(includes, norm) and not _matches_any(excludes, norm)
        if is_core:
            has_core = True
            per_path.append((norm, "core"))
        else:
            per_path.append((norm, "non-core"))
    return has_core, per_path, fell_back


def cmd_classify(args: argparse.Namespace) -> int:
    """--classify 子命令入口; 输出与退出码按 args 决定。"""
    if args.batch:
        paths = [line for line in sys.stdin.read().splitlines() if line.strip()]
    else:
        paths = list(args.paths)
        if not paths:
            print(
                "ERROR: --classify 需要至少一个 path, 或与 --batch 配合从 stdin 读",
                file=sys.stderr,
            )
            return 2

    has_core, per_path, fell_back = classify_paths(paths)

    if fell_back:
        if args.strict_config:
            print(
                "ERROR: core.include 缺失, --strict-config 拒绝回退命名推断; "
                "请在仓库根新增 core.include 显式声明核心路径。",
                file=sys.stderr,
            )
            return 2
        print(
            "WARN: core.include 缺失, 已回退到硬编码核心目录 (v0.4.3 core/extension 隐式约定). "
            "建议在仓库根新增 core.include 显式声明, 一次性提示, 后续不再 WARN。",
            file=sys.stderr,
        )

    if args.json:
        print(
            json.dumps(
                {
                    "has_core": has_core,
                    "fell_back": fell_back,
                    "items": [{"path": p, "kind": k} for p, k in per_path],
                },
                ensure_ascii=False,
            )
        )
    else:
        for p, k in per_path:
            print(f"{p}\t{k}")
        if has_core:
            print(
                f"# overall: core ({sum(1 for _, k in per_path if k == 'core')} of {len(per_path)})",
                file=sys.stderr,
            )
        else:
            print(f"# overall: non-core ({len(per_path)} paths)", file=sys.stderr)

    # 退出码约定:
    #   0 = 至少一个 core (CI 据此走完整门)
    #   1 = 全 non-core (CI 据此走轻量门)
    #   2 = 配置错误 (strict + 缺文件 / 参数缺失)
    return 0 if has_core else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从代码 AST 反推架构数字 + core 路径分类 + draft 规划登记校验"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="对比 docs/ARCHITECTURE.md, 不一致时 exit 1",
    )
    parser.add_argument(
        "--drafts-only",
        action="store_true",
        help="仅输出 draft 规划清单 (JSON) 到 stdout",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="对给定路径判定 core|non-core (与 --batch 配合从 stdin 读路径)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量模式: 从 stdin 读路径列表, 任一命中即整体为 core (exit 0); 全 non-core exit 1",
    )
    parser.add_argument(
        "--strict-config",
        action="store_true",
        help="配合 --classify 使用: core.include / core.exclude 缺失时 exit 2 而非回退命名推断",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="--classify 输出 JSON 而非逐行 path<TAB>core|non-core",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="--classify 模式下的待分类路径",
    )
    args = parser.parse_args()

    if args.classify:
        return cmd_classify(args)

    if args.drafts_only:
        print(json.dumps(collect_planning_drafts(), ensure_ascii=False, indent=2))
        return 0

    meta = collect()
    if args.check:
        return check(meta)
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
