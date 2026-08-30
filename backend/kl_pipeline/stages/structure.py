"""kl:structure stage — concept card extraction + graph update.

Extracts new concept candidates from the item and updates the
concept index and graph.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.logging_config import logger
from backend.wiki_fs.contract import get_lifecycle


def run_structure(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Extract concepts and update the knowledge graph."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    if get_lifecycle(fm) != "kl:link":
        logger.info(f"structure: skipping {item_id} (stage={get_lifecycle(fm)})")
        return

    # Update graph edges from related items.
    graph_path = Path(wiki_fs.root) / "graph.json"
    graph = _load_graph(graph_path)

    for rid in fm.get("related", []):
        _upsert_edge(graph, item_id, rid)

    _save_graph(graph_path, graph)

    fm["lifecycle"] = "kl:structure"
    wiki_fs.write_item(item_id, {"fm": fm, "body": doc.get("body", "")})


def _upsert_edge(graph: dict, source: str, target: str) -> None:
    """Add a related edge if absent. Tolerates both on-disk shapes.

    生产 ``graph.json`` 的 ``edges`` 是 **list**（实测 96 nodes / 136 edges,
    元素为 ``{source, target, weight, type}``）; 旧实现按 dict 下标写入
    （``graph.setdefault("edges", {})[f"{a}->{b}"] = {...}``）→ 对 list 用字符串
    下标直接抛 ``list indices must be integers or slices, not str``, 而前置的
    ``edge_key not in graph.get("edges", {})`` 在 list 上做字符串成员判断恒
    False, 连去重都没发生。dict 分支保留仅为兼容历史图文件。
    """
    edges = graph.get("edges")
    if isinstance(edges, dict):
        key = f"{source}->{target}"
        if key not in edges:
            edges[key] = {"source": source, "target": target, "weight": 1.0}
        graph["edges"] = edges
        return

    if not isinstance(edges, list):
        edges = []
    for e in edges:
        if (
            isinstance(e, dict)
            and e.get("source") == source
            and e.get("target") == target
        ):
            return  # 已有同向边, 不重复追加也不虚增 weight
    edges.append({"source": source, "target": target, "weight": 1.0, "type": "related"})
    graph["edges"] = edges


def _load_graph(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    # 与生产 schema 对齐: nodes / edges 均为 list
    return {"nodes": [], "edges": []}


def _save_graph(path: Path, graph: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)
