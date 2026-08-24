"""kl:structure stage — concept card extraction + graph update.

Extracts new concept candidates from the item and updates the
concept index and graph.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.logging_config import logger


def run_structure(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Extract concepts and update the knowledge graph."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    if fm.get("kl_stage") != "kl:link":
        logger.info(f"structure: skipping {item_id} (stage={fm.get('kl_stage')})")
        return

    # Update graph edges from related items.
    graph_path = Path(wiki_fs.root) / "graph.json"
    graph = _load_graph(graph_path)

    for rid in fm.get("related", []):
        edge_key = f"{item_id}->{rid}"
        if edge_key not in graph.get("edges", {}):
            graph.setdefault("edges", {})[edge_key] = {
                "source": item_id,
                "target": rid,
                "weight": 1.0,
            }

    _save_graph(graph_path, graph)

    fm["kl_stage"] = "kl:structure"
    wiki_fs.write_item(item_id, {"fm": fm, "body": doc.get("body", "")})


def _load_graph(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"nodes": {}, "edges": {}}


def _save_graph(path: Path, graph: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)
