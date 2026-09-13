"""v1 Knowledge API — 共享序列化 helper (R3 拆自 knowledge_api.py).

``_knowledge_to_dict`` 服务于 write (generate/publish/deprecate/retract)
与 query (get) 两族 handler; ``_list_response`` 服务于列表端点。
"""

from __future__ import annotations

from typing import Any

from backend.version import APP_VERSION as API_VERSION


def _knowledge_to_dict(k: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": k["id"],
        "kind": k["kind"],
        "title": k["title"],
        "body": k["body"],
        "prerequisites": k.get("prerequisites", []),
        "counter_examples": k.get("counter_examples", []),
        "evidence_refs": k.get("evidence_refs", []),
        "expiry_at": k.get("expiry_at"),
        "review_at": k.get("review_at"),
        "status": k["status"],
        "revision": k["revision"],
        "wiki_path": k.get("wiki_path"),
        "content_hash": k.get("content_hash"),
        "published_at": k.get("published_at"),
        "deprecation_reason": k.get("deprecation_reason"),
        "replacement_knowledge_id": k.get("replacement_knowledge_id"),
        "retraction_reason": k.get("retraction_reason"),
        "allowed_actions": k.get("allowed_actions", []),
        "reason": k.get("reason"),
        "created_at": k["created_at"],
        "updated_at": k["updated_at"],
    }


def _list_response(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_knowledge_to_dict(k) for k in items],
        "total": total if total is not None else len(items),
    }
