"""SecurityGraphEngine — build security knowledge graph + enrich hotspot items.

Design
------
- `build_security_graph(view)` returns {nodes, edges} for a given view.
- `enrich_item(item)` extracts CVE/ATT&CK/compliance IDs from item content.
- All queries hit local SQLite only — no external API calls.
"""
from __future__ import annotations

import json
import logging
import re

from backend.repository.db import get_connection
from backend.repository.security_repo import SecurityRepository

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")
_ATTACK_RE = re.compile(r"T\d{4}(?:\.\d{3})?")
_COMPLIANCE_KEYWORDS = [
    "等保", "等级保护", "关基", "关键信息基础设施",
    "数据安全法", "数安法", "网络安全法", "网安法",
    "个人信息保护法", "个保法", "GDPR",
]

_log = logging.getLogger("hotspot.security.graph")

class SecurityGraphEngine:
    """Build security knowledge graph and enrich hotspot/knowledge items."""

    def __init__(self, repo: SecurityRepository | None = None):
        self._repo = repo or SecurityRepository()

    # ------------------------------------------------------------------
    # Graph building
    # ------------------------------------------------------------------
    def build_security_graph(self, view: str = "full") -> dict:
        """Build security knowledge graph for a given view.

        Args:
            view: 'full' | 'attack' | 'cve' | 'compliance'

        Returns:
            {"nodes": [...], "edges": [...], "stats": {...}}
        """
        nodes: list[dict] = []
        edges: list[dict] = []

        if view in ("full", "attack"):
            nodes.extend(self._load_attack_nodes())
            edges.extend(self._load_attack_edges())

        if view in ("full", "cve"):
            nodes.extend(self._load_cve_nodes())
            edges.extend(self._load_cve_edges())

        if view in ("full", "compliance"):
            nodes.extend(self._load_compliance_nodes())
            edges.extend(self._load_compliance_edges())

        # Associate knowledge items
        knowledge_nodes = self._load_knowledge_item_nodes()
        nodes.extend(knowledge_nodes)
        edges.extend(self._build_knowledge_edges(knowledge_nodes))

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "tactics": len([n for n in nodes if n.get("entity_type") == "tactic"]),
                "techniques": len([n for n in nodes if n.get("entity_type") == "technique"]),
                "cves": len([n for n in nodes if n.get("entity_type") == "cve"]),
                "compliance_items": len([n for n in nodes if n.get("entity_type") == "compliance"]),
                "knowledge_items": len([n for n in nodes if n.get("entity_type") == "knowledge_item"]),
            },
        }

    def _load_attack_nodes(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM security_entities WHERE entity_type IN ('tactic','technique') "
            "ORDER BY entity_type ASC, name ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_attack_edges(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM security_edges WHERE edge_type IN ('uses','subtechnique-of')"
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_cve_nodes(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM security_entities WHERE entity_type = 'cve' "
            "ORDER BY updated_at DESC LIMIT 200"
        ).fetchall()
        nodes = []
        for r in rows:
            d = dict(r)
            # 从 metadata JSON 提取 knowledge_refs
            metadata = d.get("metadata")
            knowledge_refs: list[str] = []
            if metadata:
                try:
                    parsed = json.loads(metadata) if isinstance(metadata, str) else metadata
                    knowledge_refs = parsed.get("knowledge_refs", [])
                except (json.JSONDecodeError, TypeError):
                    knowledge_refs = []
            d["knowledge_refs"] = knowledge_refs
            d["knowledge_count"] = len(knowledge_refs)
            d["linked"] = len(knowledge_refs) > 0
            nodes.append(d)
        return nodes

    def _load_cve_edges(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM security_edges WHERE edge_type IN ('causes','fixes','related-to')"
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_compliance_nodes(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM security_entities WHERE entity_type = 'compliance' "
            "ORDER BY name ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_compliance_edges(self) -> list[dict]:
        return []

    def _load_knowledge_item_nodes(self) -> list[dict]:
        """Load knowledge items that have security entity references."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, source, domain, type, cve_ids, attack_techniques, compliance_refs "
            "FROM knowledge_items "
            "WHERE cve_ids IS NOT NULL OR attack_techniques IS NOT NULL OR compliance_refs IS NOT NULL "
            "LIMIT 200"
        ).fetchall()
        nodes = []
        for r in rows:
            d = dict(r)
            d["entity_type"] = "knowledge_item"
            d["name"] = d.pop("title")
            nodes.append(d)
        return nodes

    def _build_knowledge_edges(self, knowledge_nodes: list[dict]) -> list[dict]:
        """Build edges between knowledge items and security entities.

        Phase 14 扩展:
        - 对每个 knowledge_item 的 cve_ids, 查找 security_entities 中对应 entity
        - 添加 edge: source=knowledge_item_id, target=security_entity_id, edge_type='references'
        """
        edges = []
        conn = get_connection()
        for kn in knowledge_nodes:
            kid = kn["id"]
            for field, edge_type in [
                ("cve_ids", "related-to"),
                ("attack_techniques", "related-to"),
                ("compliance_refs", "related-to"),
            ]:
                raw = kn.get(field)
                if not raw:
                    continue
                try:
                    ids = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(ids, list):
                    continue
                for target_id in ids:
                    # Phase 14: 查找 security_entities 中对应 entity
                    se_row = conn.execute(
                        "SELECT id FROM security_entities WHERE name = ? AND entity_type = 'cve'",
                        (str(target_id),),
                    ).fetchone()
                    if se_row is not None:
                        edges.append({
                            "source_id": kid,
                            "target_id": str(se_row["id"]),
                            "edge_type": "references",
                            "weight": 1.0,
                        })
                    else:
                        edges.append({
                            "source_id": kid,
                            "target_id": str(target_id),
                            "edge_type": edge_type,
                            "weight": 1.0,
                        })
        return edges

    # ------------------------------------------------------------------
    # Item enrichment
    # ------------------------------------------------------------------
    def enrich_item(self, item: dict) -> dict:
        """Extract security entity IDs from a hotspot/knowledge item.

        Args:
            item: dict with at least 'title', 'summary' (optional)

        Returns:
            dict with enriched fields: cve_ids, attack_techniques, compliance_refs
        """
        title = item.get("title", "")
        summary = item.get("summary", "") or item.get("description", "") or ""
        text = f"{title} {summary}"

        cve_ids = list(set(_CVE_RE.findall(text)))
        attack_ids = list(set(_ATTACK_RE.findall(text)))
        compliance_refs = []
        for kw in _COMPLIANCE_KEYWORDS:
            if kw in text and kw not in compliance_refs:
                compliance_refs.append(kw)

        result = {}
        if cve_ids:
            result["cve_ids"] = json.dumps(cve_ids, ensure_ascii=False)
        if attack_ids:
            result["attack_techniques"] = json.dumps(attack_ids, ensure_ascii=False)
        if compliance_refs:
            result["compliance_refs"] = json.dumps(compliance_refs, ensure_ascii=False)

        return result

    def enrich_batch(self, items: list[dict]) -> list[dict]:
        """Enrich a batch of items, returning those with new findings."""
        enriched = []
        for item in items:
            fields = self.enrich_item(item)
            if fields:
                enriched.append({**item, **fields})
        return enriched


__all__ = ["_ATTACK_RE", "_CVE_RE", "SecurityGraphEngine"]
