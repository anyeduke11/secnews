#!/usr/bin/env python3
"""router 碎化体检 (只读, 无副作用).

对 ``backend/api/*.py`` 做 AST 扫描, 以「端点密度」衡量路由文件是否被拆得过碎:

1. 总量 — 路由模块数 / 端点数 / 行数中位数
2. 超 150 行 — 与 ``backend/api/AGENTS.md`` 硬约束对账 (存量超标仅 advisory)
3. 碎化候选 — 端点数 <= 2 且行数 <= 40 的模块 (合并候选)
4. 无端点模块 — 区分「聚合模块」(只 include_router) 与「无路由」(helper/命名误置)
5. 同域前缀簇 — 去掉 ``_api`` / ``_ops_api`` 后缀取首段, 模块数 >= 3 的簇

本脚本只报告, 不改代码: 是否合并由 owner 决策 (退出码恒 0)。

用法::

    python scripts/check_router_fragmentation.py
    python scripts/check_router_fragmentation.py --format json
    python scripts/check_router_fragmentation.py --limit 20
"""
from __future__ import annotations

import argparse
import ast
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "backend" / "api"

# APIRouter 上的 HTTP 装饰器名 (`@router.get(...)` / `@router.websocket`)
_ENDPOINT_METHODS = frozenset(
    {"get", "post", "put", "delete", "patch", "options", "head", "api_route", "websocket"}
)
_MAX_LINES = 150  # backend/api/AGENTS.md 硬约束
_FRAG_ENDPOINTS = 2  # 碎化候选: 端点 <= 2
_FRAG_LINES = 40  # 碎化候选: 行数 <= 40
_CLUSTER_MIN = 3  # 同域簇: 模块数 >= 3


def _router_vars(tree: ast.Module) -> set[str]:
    """找出模块内 `x = APIRouter(...)` 的变量名."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "APIRouter"
        ):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _count_endpoints(tree: ast.Module, routers: set[str]) -> int:
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in routers
                and target.attr in _ENDPOINT_METHODS
            ):
                n += 1
    return n


def _aggregates(tree: ast.Module) -> bool:
    """模块是否为聚合壳 (只 include_router 子路由, 自身无端点)."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        for node in ast.walk(tree)
    )


def _cluster_key(stem: str) -> str:
    """`quality_rules_api` → `quality`; `codegarden_ops_api` → `codegarden`."""
    base = stem
    for suffix in ("_ops_api", "_api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.split("_", 1)[0]


def scan() -> dict:
    modules: list[dict] = []
    for path in sorted(API_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        routers = _router_vars(tree)
        modules.append(
            {
                "module": path.stem,
                "lines": len(text.splitlines()),
                "routers": len(routers),
                "endpoints": _count_endpoints(tree, routers) if routers else 0,
                "aggregates": _aggregates(tree),
            }
        )

    routable = [m for m in modules if m["endpoints"] > 0]
    clusters: dict[str, list[str]] = {}
    for m in routable:
        clusters.setdefault(_cluster_key(m["module"]), []).append(m["module"])

    return {
        "modules_scanned": len(modules),
        "router_modules": len(routable),
        "endpoints_total": sum(m["endpoints"] for m in routable),
        "lines_median": int(statistics.median(m["lines"] for m in modules)) if modules else 0,
        "over_limit": sorted(
            (m for m in modules if m["lines"] > _MAX_LINES), key=lambda m: -m["lines"]
        ),
        "no_endpoint": [
            {"module": m["module"], "aggregates": m["aggregates"]}
            for m in modules
            if m["endpoints"] == 0
        ],
        "fragmented": sorted(
            (m for m in routable if m["endpoints"] <= _FRAG_ENDPOINTS and m["lines"] <= _FRAG_LINES),
            key=lambda m: m["lines"],
        ),
        "clusters": sorted(
            (
                {"prefix": k, "modules": sorted(v), "endpoints": sum(
                    m["endpoints"] for m in routable if m["module"] in v
                )}
                for k, v in clusters.items()
                if len(v) >= _CLUSTER_MIN
            ),
            key=lambda c: -len(c["modules"]),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="router 碎化体检 (只读)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--limit", type=int, default=15, help="各分区明细行数上限")
    args = parser.parse_args()

    if not API_DIR.is_dir():
        print(f"目录缺失: {API_DIR}", file=sys.stderr)
        return 2

    r = scan()
    if args.format == "json":
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    lim = args.limit
    print("router 碎化体检  backend/api/")
    print(f"  模块 {r['modules_scanned']} (其中路由模块 {r['router_modules']})"
          f" · 端点 {r['endpoints_total']} · 行数中位数 {r['lines_median']}")
    print("-" * 56)
    print(f"[ADVISORY] 超 {_MAX_LINES} 行 {len(r['over_limit'])} — 存量超标, 拆分决策归 owner")
    for m in r["over_limit"][:lim]:
        print(f"           {m['module']}.py  {m['lines']} 行 / {m['endpoints']} 端点")
    print(f"[INFO] 无端点模块 {len(r['no_endpoint'])}")
    for m in r["no_endpoint"][:lim]:
        kind = "聚合壳(include_router)" if m["aggregates"] else "无路由(helper/命名误置)"
        print(f"           {m['module']}.py  {kind}")
    print(f"[FRAGMENT] 碎化候选 {len(r['fragmented'])} "
          f"(端点<={_FRAG_ENDPOINTS} 且 <={_FRAG_LINES} 行) — 合并候选")
    for m in r["fragmented"][:lim]:
        print(f"           {m['module']}.py  {m['lines']} 行 / {m['endpoints']} 端点")
    print(f"[CLUSTER] 同域前缀簇 {len(r['clusters'])} (模块数>={_CLUSTER_MIN})")
    for c in r["clusters"][:lim]:
        print(f"           {c['prefix']} ({len(c['modules'])} 模块 / {c['endpoints']} 端点): "
              f"{', '.join(c['modules'][:6])}{' …' if len(c['modules']) > 6 else ''}")
    print("-" * 56)
    print("结论: 只读体检, 合并/拆分由 owner 决策")
    return 0


if __name__ == "__main__":
    sys.exit(main())