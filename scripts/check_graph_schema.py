#!/usr/bin/env python3
"""CI 校验 llm-wiki-2.0/graph.json schema (v0.5 M3.5 Task13)。

校验内容 (对齐 backend/services/concept_linker.validate_graph_schema):
- nodes / edges 必须是数组
- 边 type ∈ {uses, depends, contradicts, caused, fixed, supersedes}
- 每边带 weight (≥1) + source_observation_count (≥1)
- 边 source/target 必须在 nodes 中
- 无重复边 (source, target, type)

用法::

    python scripts/check_graph_schema.py        # exit 0 = 通过, 1 = 失败
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "llm-wiki-2.0" / "graph.json"

# 轻量 import (concept_linker 顶层只依赖 stdlib, 无后端副作用)
sys.path.insert(0, str(ROOT))
from backend.services.concept_linker import validate_graph_schema


def main() -> int:
    if not GRAPH_PATH.exists():
        print(f"SKIP: {GRAPH_PATH} 不存在 (尚未填充), 通过")
        return 0
    try:
        graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: graph.json 解析失败: {e}", file=sys.stderr)
        return 1

    errors = validate_graph_schema(graph)
    nodes = len(graph.get("nodes", []))
    edges = len(graph.get("edges", []))
    if errors:
        print(f"FAIL: graph.json schema 不合法 ({nodes} nodes / {edges} edges):")
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK: graph.json schema 合法 ({nodes} nodes / {edges} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
