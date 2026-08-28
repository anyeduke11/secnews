"""DeepRead 持久化仓库 (Phase 4 S4-2)。

按 (entity_type, entity_id) UPSERT — force=True 覆盖旧 sections,
force=False 时 read-then-decide (service 层做 cache 命中短路)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeepReadItem:
    entity_type: str
    entity_id: str
    content_md: str = ""
    sections_json: str = "{}"
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    created_at: str = ""
    updated_at: str = ""
    # 派生: 4 节 markdown 字典 (从 sections_json 反序列化, 失败时返回空 dict)
    sections: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "content_md": self.content_md,
            "sections": self.sections,
            "sections_json": self.sections_json,
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _row(item: DeepReadItem) -> dict:
    """dict 风格 row 字段快照。"""
    return {
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "content_md": item.content_md,
        "sections_json": item.sections_json,
        "provider": item.provider,
        "model": item.model,
        "tokens_in": item.tokens_in,
        "tokens_out": item.tokens_out,
        "cost_usd": item.cost_usd,
        "latency_ms": item.latency_ms,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class DeepReadRepository:
    TABLE = "deep_reads"

    def get(self, entity_type: str, entity_id: str) -> DeepReadItem | None:
        from backend.repository.db import get_connection

        conn = get_connection()
        row = conn.execute(
            f"SELECT * FROM {self.TABLE} WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def upsert(
        self,
        entity_type: str,
        entity_id: str,
        content_md: str,
        sections_json: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
    ) -> DeepReadItem:
        from backend.repository.db import get_connection

        now = _now_iso()
        conn = get_connection()
        conn.execute(
            f"""INSERT INTO {self.TABLE}
                (entity_type, entity_id, content_md, sections_json,
                 provider, model, tokens_in, tokens_out, cost_usd, latency_ms,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    content_md = excluded.content_md,
                    sections_json = excluded.sections_json,
                    provider = excluded.provider,
                    model = excluded.model,
                    tokens_in = excluded.tokens_in,
                    tokens_out = excluded.tokens_out,
                    cost_usd = excluded.cost_usd,
                    latency_ms = excluded.latency_ms,
                    updated_at = excluded.updated_at""",
            (
                entity_type, entity_id, content_md, sections_json,
                provider, model, tokens_in, tokens_out, cost_usd, latency_ms,
                now, now,
            ),
        )
        item = self.get(entity_type, entity_id)
        assert item is not None  # upsert 必返回
        return item

    def list_recent(self, limit: int = 20) -> list[DeepReadItem]:
        from backend.repository.db import get_connection

        conn = get_connection()
        rows = conn.execute(
            f"SELECT * FROM {self.TABLE} ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def _row_to_item(self, row) -> DeepReadItem:
        import json as _json
        sections_raw = str(row["sections_json"] or "{}")
        try:
            sections = _json.loads(sections_raw)
            if not isinstance(sections, dict):
                sections = {}
        except _json.JSONDecodeError:
            sections = {}
        return DeepReadItem(
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
            content_md=str(row["content_md"] or ""),
            sections_json=sections_raw,
            provider=str(row["provider"] or ""),
            model=str(row["model"] or ""),
            tokens_in=int(row["tokens_in"] or 0),
            tokens_out=int(row["tokens_out"] or 0),
            cost_usd=float(row["cost_usd"] or 0.0),
            latency_ms=int(row["latency_ms"] or 0),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
            sections=sections,
        )


__all__ = ["DeepReadItem", "DeepReadRepository"]