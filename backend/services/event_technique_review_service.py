"""MP-2 EventTechniqueReviewService — owner 人审 CRUD + 批量便利 + 进度指标.

职责
----
- ``approve_candidate(candidate_id, owner, note=None)``: approve → 写 event_technique_map + audit_log
- ``reject_candidate(candidate_id, owner, reject_reason)``: reject → 改 status + audit_log
- ``edit_candidate(candidate_id, owner, edits)``: edit → 改 status='edited' + 落 map + audit
- ``batch_approve_for_event_type(event_type_id, owner, min_confidence=0.7)``: 批量便利
- ``get_progress()``: 进度指标 (按 event_type 分组: pending/approved/rejected/total/avg_confidence)

审计
----
- 所有 owner 动作写 audit_log_mp2_review (与 audit_log 隔离)
- 每条 candidate approve/edit 都生成一条 event_technique_map 行, 保留 candidate_id/source_report_id
  作追溯链; owner_audit_chain 记录变更历史 (JSON array)
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.event_technique_repo import (
    EventTechniqueCandidateRepo,
    EventTechniqueMapRepo,
    Mp2AuditRepo,
    new_ulid,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_map_id() -> str:
    return new_ulid("etm")


class EventTechniqueReviewService:
    """owner 人审 CRUD + 批量便利 + 进度."""

    def __init__(self) -> None:
        self.candidate_repo = EventTechniqueCandidateRepo()
        self.map_repo = EventTechniqueMapRepo()
        self.audit_repo = Mp2AuditRepo()

    # ------------------------------------------------------------------
    # approve
    # ------------------------------------------------------------------
    def approve_candidate(
        self,
        candidate_id: str,
        owner: str = "owner",
        note: str | None = None,
    ) -> dict:
        """Approve 一条 candidate → 写 event_technique_map + audit_log.

        Returns:
            {"candidate_id": ..., "map_id": ..., "event_type_id": ..., "technique_id": ..., "stage": ...}
        """
        cand = self.candidate_repo.get(candidate_id)
        if not cand:
            raise NotFoundException(f"candidate {candidate_id} not found")
        if cand["owner_status"] in ("approved",):
            raise ConflictException(f"candidate {candidate_id} already approved")

        map_id = _new_map_id()
        audit_chain = [
            {
                "ts": _now_iso(),
                "action": "approve",
                "by": owner,
                "prev_status": cand["owner_status"],
                "note": note or "",
            }
        ]
        try:
            self.map_repo.insert(
                map_id=map_id,
                event_type_id=cand["event_type_id"],
                technique_id=cand["technique_id"],
                stage=cand["stage"],
                note=note,
                candidate_id=candidate_id,
                source_report_id=cand["source_report_id"],
                approved_by=owner,
                agent_owner=cand.get("agent_owner", "A"),
                audit_chain=audit_chain,
            )
        except Exception as e:
            # UNIQUE (event_type_id, technique_id, stage) — 同一 stage 已有 technique
            if "UNIQUE" in str(e).upper():
                raise ConflictException(
                    f"event_type={cand['event_type_id']} technique={cand['technique_id']} "
                    f"stage={cand['stage']} 已存在 event_technique_map 行, 不能重复 approve"
                ) from e
            raise

        # 更新 candidate 状态
        self.candidate_repo.update_owner_status(candidate_id, "approved", owner_action_by=owner)

        # 写审计
        self.audit_repo.write(
            actor=owner,
            action="approve",
            target_type="event_technique_candidate",
            target_id=candidate_id,
            event_type_id=cand["event_type_id"],
            detail={
                "status": "approved",
                "map_id": map_id,
                "technique_id": cand["technique_id"],
                "stage": cand["stage"],
                "note": note or "",
            },
        )
        logger.info(
            "candidate approved",
            extra={"trace_id": "", "candidate_id": candidate_id, "map_id": map_id},
        )
        return {
            "candidate_id": candidate_id,
            "map_id": map_id,
            "event_type_id": cand["event_type_id"],
            "technique_id": cand["technique_id"],
            "stage": cand["stage"],
        }

    # ------------------------------------------------------------------
    # reject
    # ------------------------------------------------------------------
    def reject_candidate(
        self,
        candidate_id: str,
        owner: str = "owner",
        reject_reason: str = "",
    ) -> dict:
        cand = self.candidate_repo.get(candidate_id)
        if not cand:
            raise NotFoundException(f"candidate {candidate_id} not found")
        if cand["owner_status"] == "rejected":
            raise ConflictException(f"candidate {candidate_id} already rejected")
        if cand["owner_status"] == "approved":
            raise ConflictException(
                f"candidate {candidate_id} already approved (先撤 map 行再 reject, 防审计链断裂)"
            )
        if not reject_reason:
            raise InvalidParamException("reject_reason 不能为空 (审计要求)")

        self.candidate_repo.update_owner_status(
            candidate_id, "rejected", owner_action_by=owner, reject_reason=reject_reason
        )
        self.audit_repo.write(
            actor=owner,
            action="reject",
            target_type="event_technique_candidate",
            target_id=candidate_id,
            event_type_id=cand["event_type_id"],
            detail={
                "technique_id": cand["technique_id"],
                "stage": cand["stage"],
                "reject_reason": reject_reason,
            },
        )
        logger.info(
            "candidate rejected",
            extra={"trace_id": "", "candidate_id": candidate_id, "reason": reject_reason},
        )
        return {"candidate_id": candidate_id, "status": "rejected", "reject_reason": reject_reason}

    # ------------------------------------------------------------------
    # batch approve (按 event_type 批量)
    # ------------------------------------------------------------------
    def batch_approve_for_event_type(
        self,
        event_type_id: str,
        owner: str = "owner",
        min_confidence: float = 0.7,
        note: str | None = None,
    ) -> dict:
        """批量 approve 一个 event_type 下所有 confidence ≥ min_confidence 的 pending candidates.

        Returns:
            {"event_type_id": ..., "approved_count": N, "skipped_count": M, "errors": [...]}
        """
        candidates = self.candidate_repo.list_by_event_type(
            event_type_id, owner_status="pending", limit=500
        )
        approved = 0
        skipped = 0
        errors: list[dict] = []

        for cand in candidates:
            if cand["confidence"] < min_confidence:
                skipped += 1
                continue
            try:
                self.approve_candidate(cand["id"], owner=owner, note=note)
                approved += 1
            except Exception as e:
                # Conflict (UNIQUE map) — 跳过
                if "UNIQUE" in str(e).upper() or "已存在" in str(e):
                    skipped += 1
                else:
                    errors.append({"candidate_id": cand["id"], "error": str(e)})

        self.audit_repo.write(
            actor=owner,
            action="batch_approve",
            target_type="event_type",
            target_id=event_type_id,
            event_type_id=event_type_id,
            detail={
                "min_confidence": min_confidence,
                "approved_count": approved,
                "skipped_count": skipped,
                "errors_count": len(errors),
            },
        )
        return {
            "event_type_id": event_type_id,
            "approved_count": approved,
            "skipped_count": skipped,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # progress
    # ------------------------------------------------------------------
    def get_progress(self) -> dict:
        """进度指标: 按 event_type 分组, pending/approved/rejected/total/avg_confidence."""
        grouped = self.candidate_repo.list_pending_grouped_by_event_type()
        # 加上已审定 map 的统计
        # map 表的统计 — 直接 SQL 查
        from backend.repository.db import get_connection
        conn = get_connection()
        map_rows = conn.execute(
            "SELECT event_type_id, COUNT(*) AS approved_map FROM event_technique_map GROUP BY event_type_id"
        ).fetchall()
        map_counts = {str(r["event_type_id"]): int(r["approved_map"]) for r in map_rows}

        for g in grouped:
            g["approved_map"] = map_counts.get(g["event_type_id"], 0)
        return {"by_event_type": grouped, "total_event_types": len(grouped)}

    # ------------------------------------------------------------------
    # review queue (供前端)
    # ------------------------------------------------------------------
    def get_review_queue(self, event_type_id: str | None = None) -> list[dict]:
        """owner 待审队列 — 按 event_type 分组, 每条 candidate 完整信息."""
        if event_type_id:
            return self.candidate_repo.list_by_event_type(event_type_id, owner_status="pending", limit=200)
        # 全量: 按 event_type 分组
        from backend.repository.event_technique_repo import EventTypeRepo
        et_repo = EventTypeRepo()
        all_types = et_repo.list_all()
        result = []
        for et in all_types:
            pending = self.candidate_repo.list_by_event_type(et["id"], owner_status="pending", limit=200)
            if pending:
                result.append({
                    "event_type_id": et["id"],
                    "name_zh": et["name_zh"],
                    "name_en": et["name_en"],
                    "candidates": pending,
                })
        return result

    # ------------------------------------------------------------------
    # trace chain (供前端溯源)
    # ------------------------------------------------------------------
    def trace_map(self, map_id: str) -> dict:
        return self.map_repo.trace_chain(map_id) or {}


__all__ = ["EventTechniqueReviewService"]
