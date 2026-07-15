"""Knowledge domain models for v1.4 knowledge dashboard."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class KnowledgeItem:
    """Mirrors knowledge/items/{hash}.md frontmatter."""
    id: str
    title: str
    source: str  # cubox | bookmark | secnews | secnews_archive
    source_url: Optional[str] = None
    domain: Optional[str] = None
    topic: Optional[str] = None
    type: Optional[str] = None  # news | analysis | paper | tutorial | tool | opinion
    difficulty: Optional[str] = None  # beginner | intermediate | advanced | expert
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    mastered: int = 0
    compiled: bool = False
    ingested_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeItem":
        import json
        return cls(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            source_url=row.get("source_url"),
            domain=row.get("domain"),
            topic=row.get("topic"),
            type=row.get("type"),
            difficulty=row.get("difficulty"),
            tags=json.loads(row["tags"]) if row.get("tags") else [],
            concepts=json.loads(row["concepts"]) if row.get("concepts") else [],
            mastered=row.get("mastery", 0),
            compiled=bool(row.get("compiled", 0)),
            ingested_at=row["ingested_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "domain": self.domain,
            "topic": self.topic,
            "type": self.type,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "concepts": self.concepts,
            "mastered": self.mastered,
            "compiled": self.compiled,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeConcept:
    """Mirrors knowledge/concepts/{slug}.md frontmatter."""
    slug: str
    title: str
    domain: Optional[str] = None
    source_items: list[str] = field(default_factory=list)
    local_wiki_ref: Optional[str] = None
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeConcept":
        import json
        return cls(
            slug=row["slug"],
            title=row["title"],
            domain=row.get("domain"),
            source_items=json.loads(row["source_items"]) if row.get("source_items") else [],
            local_wiki_ref=row.get("local_wiki_ref"),
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "domain": self.domain,
            "source_items": self.source_items,
            "local_wiki_ref": self.local_wiki_ref,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeTask:
    """Task queue item."""
    id: int
    task_type: str
    status: str = "pending"
    params: Optional[dict] = None
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeTask":
        import json
        return cls(
            id=row["id"],
            task_type=row["task_type"],
            status=row["status"],
            params=json.loads(row["params"]) if row.get("params") else None,
            result_path=row.get("result_path"),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status,
            "params": self.params,
            "result_path": self.result_path,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
