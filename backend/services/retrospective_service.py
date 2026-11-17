"""RetrospectiveService — C6-2 知识回流 glue: 案件关闭 → 复盘提案 (人主律只起草).

D8 裁决 = 事件直连: ``close_case`` 落 ``v1_outbox(v1_case_closed)`` →
``OutboxDispatcher`` 广播成功后回调本服务 → ``RunLedgerService.copilot_draft
(kind='report')`` 落 ``v1_proposals(draft, source='copilot')``。

本服务**只起草**: 不批准、不发布知识、不触 wiki。人批准后 Run 产物落盘, 再由
``RunLedgerService._materialize_knowledge_draft`` 补 ``v1_knowledge`` draft →
既有 publish / review / adoption 链 (知识发布 CAS + wiki-first 不变)。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.logging_config import logger
from backend.repository.proposal_repo import ProposalRepository

EVENT_TYPE = "v1_case_closed"
PROPOSAL_KIND = "report"  # 与 SK-04 复盘草案同 kind


class RetrospectiveService:
    def __init__(
        self,
        proposal_repo: ProposalRepository | None = None,
        drafter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._proposals = proposal_repo or ProposalRepository()
        # drafter 可注入 (演练/测试桩); None → copilot_draft 默认 ai_hub 起草
        self._drafter = drafter

    def handle_case_closed(self, row: dict[str, Any]) -> None:
        """outbox 行 → 复盘提案。幂等: 同 case 已有 report 提案即跳过 (重放安全)."""
        payload = row.get("payload") or {}
        case_id = payload.get("id") or row.get("aggregate_id") or ""
        if not case_id:
            logger.warning(f"v1_case_closed row without case id (outbox_id={row.get('id')})")
            return
        if payload.get("status") and payload["status"] != "closed":
            return
        if self._proposals.exists_for_case(case_id, kind=PROPOSAL_KIND):
            logger.debug(f"retrospective proposal already exists for case={case_id}")
            return

        from backend.services.run_ledger_service import RunLedgerService

        try:
            proposal = RunLedgerService().copilot_draft(
                PROPOSAL_KIND, case_id=case_id, drafter=self._drafter,
            )
        except Exception as e:
            # 无绑定证据等前置不满足 → 复盘不成立, 留痕跳过 (不伪造提案)
            logger.info(
                f"retrospective draft skipped case={case_id}: {type(e).__name__}: {e}"
            )
            return
        if proposal.get("status") == "failed":
            logger.warning(
                f"retrospective draft failed (收件箱可重试) case={case_id} "
                f"proposal={proposal.get('id')}"
            )
            return
        logger.info(
            f"retrospective proposal drafted case={case_id} proposal={proposal.get('id')}"
        )


def register(
    dispatcher: Any,
    drafter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    """main.py lifespan: 把本服务挂到 outbox dispatcher (事件直连)."""
    dispatcher.add_handler(
        EVENT_TYPE, RetrospectiveService(drafter=drafter).handle_case_closed,
    )


__all__ = ["EVENT_TYPE", "PROPOSAL_KIND", "RetrospectiveService", "register"]