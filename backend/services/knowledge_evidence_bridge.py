"""Knowledge v1 evidence 桥块 — draft 落库 + V1EvidenceService 追踪 + v1_outbox 事件.

knowledge_service 拆分 (Batch 4 B) 的实现模块之一: import v1_evidence_service
(及 v1 outbox 事件) 的部分归属此处。以 mixin 形式并入 KnowledgeService
(knowledge_service.py facade), 公开 API 逐字不变。
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.repository.knowledge_revision_repo import KnowledgeRefRepository
from backend.repository.v1_knowledge_repo import V1KnowledgeRepository
from backend.services.knowledge_common import (
    _KNOWLEDGE_ALLOWED_ACTIONS,
    _content_hash,
    _ulid26,
    _utcnow_iso,
)


def insert_knowledge_draft(
    *, case_id: str, kind: str, parsed: dict[str, Any],
    submitted_by: str, source_judgment_id: str, source_action_id: str,
    repo: V1KnowledgeRepository | None = None,
    ref_repo: KnowledgeRefRepository | None = None,
) -> dict[str, Any]:
    """draft 落库 (module 级入口).

    供 services 域内其他模块 (如 run_ledger_service 的知识回流) 复用 —— 它们必须
    引本模块而非 knowledge_service facade: facade 反向依赖 run_ledger_service
    (create_with_dsh 起草提案), facade ⇄ run_ledger_service 会构成依赖环
    (见 test_service_cycle_guard)。
    """
    repo = repo or V1KnowledgeRepository()
    ref_repo = ref_repo or KnowledgeRefRepository()
    kid = _ulid26()
    now = _utcnow_iso()
    ch = _content_hash(
        parsed["body"], parsed["prerequisites"], parsed["counter_examples"], parsed["evidence_refs"],
    )
    body = {
        "id": kid, "kind": kind, "title": parsed["title"], "body": parsed["body"],
        "prerequisites": parsed["prerequisites"], "counter_examples": parsed["counter_examples"],
        "evidence_refs": parsed["evidence_refs"],
        "expiry_at": parsed.get("expiry_at"), "review_at": parsed["review_at"],
        "status": "draft", "revision": 1,
        "wiki_path": None, "content_hash": ch, "published_at": None,
        "deprecation_reason": None, "replacement_knowledge_id": None, "retraction_reason": None,
        "allowed_actions": _KNOWLEDGE_ALLOWED_ACTIONS["draft"],
        "reason": None, "created_at": now, "updated_at": now,
    }
    repo.insert(body)
    # 关联 source refs (judgment + action)
    if source_judgment_id:
        ref_repo.add(kid, "judgment", source_judgment_id, role="used")
    if source_action_id:
        ref_repo.add(kid, "action", source_action_id, role="used")
    # 走 V1EvidenceService (best-effort, 同 T11/T12)
    try:
        from backend.services.v1_evidence_service import V1EvidenceService
        evidence = V1EvidenceService()
        intent = evidence.create_intent(
            f"v1-knowledge-{case_id}-{kind}-{ch[:16]}", "knowledge", body,
            submitted_by=submitted_by,
        )
        evidence.commit_intent(intent["intent_id"], entity_id=kid, projection=None)
    except Exception as e:
        logger.warning(f"V1EvidenceService trace failed (knowledge still inserts): {e}")
    return {"knowledge": body, "idempotent_replay": False}


class KnowledgeEvidenceBridgeMixin:
    """_insert_draft (落库 + source refs + evidence intent 追踪) + v1 业务事件."""

    def _insert_draft(
        self, *, case_id: str, kind: str, parsed: dict[str, Any],
        submitted_by: str, source_judgment_id: str, source_action_id: str,
    ) -> dict[str, Any]:
        return insert_knowledge_draft(
            case_id=case_id, kind=kind, parsed=parsed, submitted_by=submitted_by,
            source_judgment_id=source_judgment_id, source_action_id=source_action_id,
            repo=self.repo, ref_repo=self.ref_repo,
        )

    def _publish_v1_knowledge_event(self, k: dict, action: str) -> None:
        """C11 R18: 业务事件写 v1_outbox 行 (enqueue), 取代 T17 fire-and-forget."""
        try:
            from backend.observability import get_trace_id
            from backend.repository.outbox_repo import OutboxRepo
            OutboxRepo().enqueue(
                event_type="v1_knowledge",
                aggregate_type="knowledge",
                aggregate_id=k["id"],
                revision=int(k.get("revision", 0) or 0),
                payload={
                    "id": k["id"], "status": k["status"], "action": action,
                },
                trace_id=get_trace_id() or "no-trace",
            )
        except Exception as e:
            logger.debug(f"v1_knowledge outbox enqueue skipped: {e}")
