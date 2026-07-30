"""Security domain models for v1.5+ security knowledge graph."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SecurityEntity:
    id: str
    entity_type: str
    name: str
    description: Optional[str] = None
    external_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "SecurityEntity":
        import json
        return cls(
            id=str(row["id"]),
            entity_type=str(row["entity_type"]),
            name=str(row["name"]),
            description=row.get("description"),
            external_ref=row.get("external_ref"),
            metadata=_parse_json(row.get("metadata"), {}),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "description": self.description,
            "external_ref": self.external_ref,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SecurityEdge:
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "SecurityEdge":
        import json
        return cls(
            source_id=str(row["source_id"]),
            target_id=str(row["target_id"]),
            edge_type=str(row["edge_type"]),
            weight=float(row["weight"] or 1.0),
            metadata=_parse_json(row.get("metadata"), {}),
            created_at=str(row["created_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class SecurityTerm:
    id: int = 0
    canonical: str = ""
    term_type: str = ""
    category: Optional[str] = None
    definition: Optional[str] = None
    external_id: Optional[str] = None
    external_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "SecurityTerm":
        return cls(
            id=int(row["id"]),
            canonical=str(row["canonical"]),
            term_type=str(row["term_type"]),
            category=row.get("category"),
            definition=row.get("definition"),
            external_id=row.get("external_id"),
            external_ref=row.get("external_ref"),
            metadata=_parse_json(row.get("metadata"), {}),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "canonical": self.canonical,
            "term_type": self.term_type,
            "category": self.category,
            "definition": self.definition,
            "external_id": self.external_id,
            "external_ref": self.external_ref,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _parse_json(raw: Optional[str], default):
    if not raw:
        return default
    try:
        import json
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


__all__ = ["SecurityEntity", "SecurityEdge", "SecurityTerm", "_now_iso"]
