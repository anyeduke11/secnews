"""SecurityGraphService — business orchestration for security knowledge graph.

This is the service layer that sits between API and SecurityGraphEngine.
"""
from __future__ import annotations

from backend.repository.security_repo import SecurityRepository
from backend.security.enricher import enrich_batch, enrich_item
from backend.security.graph import SecurityGraphEngine


class SecurityGraphService:
    """Business orchestration for security graph + enrichment."""

    def __init__(self):
        self._repo = SecurityRepository()
        self._engine = SecurityGraphEngine(self._repo)

    def get_graph(self, view: str = "full") -> dict:
        return self._engine.build_security_graph(view)

    def list_entities(
        self,
        entity_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        if q:
            items = self._repo.search_entities(q, entity_types=[entity_type] if entity_type else None)
            return items[:limit], len(items)
        return self._repo.list_entities(entity_type=entity_type, limit=limit, offset=offset)

    def get_entity(self, entity_id: str) -> dict | None:
        return self._repo.get_entity(entity_id)

    def get_related(self, entity_id: str, depth: int = 1) -> dict:
        return self._repo.get_related(entity_id, depth=depth)

    def enrich_hotspot_item(self, item: dict) -> dict:
        return enrich_item(item)

    def enrich_batch(self, items: list[dict]) -> list[dict]:
        return enrich_batch(items)


__all__ = ["SecurityGraphService"]
