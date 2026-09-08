"""v1.0 T08 Case 服务层 (contracts §4).

要点
----
- 单一提交入口: create_case 走 V1EvidenceService.create_intent("case", body) → commit_intent
  (与 T05 subject / material / signal 同模式; 提交键 = f"v1-case-{source}-{ulid[:16]}")
- CAS update: PATCH /api/v1/cases/{id} 必传 expected_revision; 不匹配抛 CaseConflictError
- allowed_actions 5 状态机全覆盖 (与 contracts §4.3 一致):
    open           → ["claim", "close", "edit", "archive"]
    in_progress    → ["block", "close", "edit", "add_judgment"]
    blocked        → ["unblock", "edit", "add_judgment"]
    closed         → ["archive", "reopen", "edit_metadata"]
    archived       → ["unarchive"]
  任务台账 §6 简版对齐 contracts (open 加 archive, closed 调整 metadata 为 edit_metadata);
  本批优先级: 协议一致 > 任务台账细节; 评审如需调整, PATCH follow-up 即可。
- close_case: 校验无 active run (active = status in queued/claimed/running); 落 closed_at
- list_cases: 过滤 status / priority / owner_role, 分页 limit/offset
- 不连真实 db: conftest.temp_db 注入 conn, 默认走 get_connection()
"""
from __future__ import annotations

import sqlite3
import string
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.domain.v1_0_models import (
    Case,
    CaseOwnerRole,
    CasePriority,
    CaseStatus,
)
from backend.exceptions import (
    ConflictException,
    InvalidParamException,
    NotFoundException,
)
from backend.logging_config import logger
from backend.repository.case_repo import CaseRecord, CaseRepository
from backend.services.v1_evidence_service import V1EvidenceService


# ---------------------------------------------------------------------------
# 业务异常 (映射 HTTP 状态 + code)
# ---------------------------------------------------------------------------
class CaseConflictError(ConflictException):
    """CAS 失败 / 幂等键冲突 → 409 E_CONFLICT (contracts §0.4)."""

    def __init__(
        self,
        message: str = "Case revision conflict",
        *,
        current_revision: int | None = None,
        current_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.current_revision = current_revision
        self.current_status = current_status


class CaseNotFoundError(NotFoundException):
    """id 不存在 → 404 E_NOT_FOUND."""


class CaseValidationError(InvalidParamException):
    """字段校验失败 → 400 E_VALIDATION."""


# ---------------------------------------------------------------------------
# allowed_actions 5 状态机 (contracts §4.3)
# ---------------------------------------------------------------------------
ALLOWED_ACTIONS_BY_STATUS: dict[CaseStatus, list[str]] = {
    CaseStatus.open: ["claim", "close", "edit", "archive"],
    CaseStatus.in_progress: ["block", "close", "edit", "add_judgment"],
    CaseStatus.blocked: ["unblock", "edit", "add_judgment"],
    CaseStatus.closed: ["archive", "reopen", "edit_metadata"],
    CaseStatus.archived: ["unarchive"],
}


# ---------------------------------------------------------------------------
# ULID helper (与 test_v1_0_models 同 — 26 字符 Crockford Base32 subset)
# ---------------------------------------------------------------------------
_ULID_ALPHABET = string.ascii_uppercase + "234567"


def _ulid() -> str:
    """26 字符 ULID (测试与生产同一函数, 服务端生成, 客户端不传)."""
    raw = uuid.uuid4().hex.upper()
    # 26 chars 取自 32 字符 alphabet, 与 ^[A-Z2-7]{26}$ 严格匹配
    return "".join(_ULID_ALPHABET[(ord(c) + i) % 32] for i, c in enumerate(raw[:26])).ljust(26, "A")[:26]


def _submission_key(source: str, ulid: str) -> str:
    """提交键 — 与 T05 evidence 协议一致: v1-case-{source}-{ulid[:16]}."""
    return f"v1-case-{source}-{ulid[:16]}"


# ---------------------------------------------------------------------------
# 主体
# ---------------------------------------------------------------------------
class CaseService:
    """Case 业务逻辑层 — 5 状态机 + CAS + 单一提交入口."""

    def __init__(
        self,
        *,
        repo: CaseRepository | None = None,
        evidence: V1EvidenceService | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self._repo = repo or CaseRepository(conn=conn)
        self._evidence = evidence or V1EvidenceService(conn=conn)

    # ------------------------------------------------------------------
    # 转换 helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _record_to_case(rec: CaseRecord, reason: str | None = None) -> Case:
        """repo 行 → Pydantic Case (附 allowed_actions)."""
        return Case(
            id=rec.id,
            title=rec.title,
            question=rec.question,
            goal=rec.goal,
            scope=rec.scope,
            priority=CasePriority(rec.priority),
            status=CaseStatus(rec.status),
            due_at=datetime.fromisoformat(rec.due_at) if rec.due_at else None,
            subject_id=rec.subject_id,
            related_subject_ids=list(rec.related_subject_ids),
            related_signal_ids=list(rec.related_signal_ids),
            related_case_ids=list(rec.related_case_ids),
            tags=list(rec.tags),
            owner_role=CaseOwnerRole(rec.owner_role),
            revision=rec.revision,
            closed_at=datetime.fromisoformat(rec.closed_at) if rec.closed_at else None,
            created_at=datetime.fromisoformat(rec.created_at),
            updated_at=datetime.fromisoformat(rec.updated_at),
            allowed_actions=list(ALLOWED_ACTIONS_BY_STATUS.get(CaseStatus(rec.status), [])),
            reason=reason,
        )

    @staticmethod
    def _allowed_actions(status: CaseStatus) -> list[str]:
        return list(ALLOWED_ACTIONS_BY_STATUS.get(status, []))

    # ------------------------------------------------------------------
    # create_case — 走 T05 evidence 协议
    # ------------------------------------------------------------------
    def create_case(
        self,
        *,
        title: str,
        question: str,
        goal: str | None = None,
        scope: str | None = None,
        priority: str = "p2",
        due_at: str | None = None,
        subject_id: str | None = None,
        owner_role: str = "user",
        tags: list[str] | None = None,
        related_subject_ids: list[str] | None = None,
        related_signal_ids: list[str] | None = None,
        related_case_ids: list[str] | None = None,
        source: str = "manual",
    ) -> Case:
        """创建 Case — 单一入口.

        流程:
          1. 生成 ULID
          2. V1EvidenceService.create_intent("case", body) — pending receipt
          3. repo.create — 落 v1_cases
          4. evidence.commit_intent — receipt → committed (entity_id = case.id)
        失败回滚: 抛异常时由 caller 走 rollback_intent (本方法不持有 intent_id 跨调用)
        """
        # 字段校验 — 走 Pydantic Case 兜底 (title ≤120, question ≤500)
        ulid = _ulid()
        body = {
            "id": ulid,
            "title": title,
            "question": question,
            "goal": goal,
            "scope": scope,
            "priority": priority,
            "due_at": due_at,
            "subject_id": subject_id,
            "owner_role": owner_role,
            "tags": tags or [],
            "related_subject_ids": related_subject_ids or [],
            "related_signal_ids": related_signal_ids or [],
            "related_case_ids": related_case_ids or [],
        }
        # Pydantic 校验 (失败 → CaseValidationError 400)
        try:
            parsed = Case(
                id=ulid,
                title=title,
                question=question,
                goal=goal,
                scope=scope,
                priority=CasePriority(priority),
                status=CaseStatus.open,
                due_at=datetime.fromisoformat(due_at) if due_at else None,
                subject_id=subject_id,
                related_subject_ids=related_subject_ids or [],
                related_signal_ids=related_signal_ids or [],
                related_case_ids=related_case_ids or [],
                tags=tags or [],
                owner_role=CaseOwnerRole(owner_role),
                revision=1,
                closed_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                allowed_actions=[],
            )
        except (ValueError, Exception) as e:
            raise CaseValidationError(f"case validation failed: {e}") from e
        del parsed  # 仅用作校验

        # 单一提交入口 — evidence 协议
        sub_key = _submission_key(source, ulid)
        intent = self._evidence.create_intent(
            submission_key=sub_key,
            entity_type="case",
            body=body,
            submitted_by=source,
        )
        try:
            self._repo.create(body)
            self._evidence.commit_intent(
                intent["intent_id"], entity_id=ulid, projection=None
            )
        except Exception:
            # 回滚 — 清理已建 case 行 (如果存在)
            try:
                existing = self._repo.get(ulid)
                if existing is not None:
                    from backend.repository.db import get_connection

                    get_connection().execute(
                        "DELETE FROM v1_cases WHERE id = ?", (ulid,)
                    )
                    get_connection().commit()
            except Exception:  # pragma: no cover — best-effort cleanup
                logger.warning(f"rollback cleanup failed for case_id={ulid}")
            try:
                self._evidence.rollback_intent(intent["intent_id"], reason="create failed")
            except Exception:  # pragma: no cover — rollback best-effort
                logger.warning(f"rollback_intent failed for {intent['intent_id']}")
            raise

        rec = self._repo.get(ulid)
        if rec is None:
            raise CaseValidationError("case vanished after create")

        # v0.8.5 D1.2: 立项携带证据 — related_signal_ids → signal.material_id
        # 绑定进 v1_case_materials (best-effort: 关联失败不回滚 case 本体)
        try:
            bound = self._bind_case_materials(ulid, related_signal_ids or [])
            if bound:
                logger.info(f"case {ulid} bound {bound} evidence material(s) from signals")
        except Exception as e:
            logger.warning(f"case {ulid} bind_case_materials failed (best-effort): {e}")

        return self._record_to_case(rec)

    def _bind_case_materials(self, case_id: str, signal_ids: list[str]) -> int:
        """D1.2: 信号立项时把 signal.material_id 写入 v1_case_materials (幂等 OR IGNORE)."""
        if not signal_ids:
            return 0
        from backend.repository.db import get_connection

        conn = get_connection()
        marks = ",".join("?" for _ in signal_ids)
        rows = conn.execute(
            f"SELECT id, material_id FROM v1_signals WHERE id IN ({marks})",
            list(signal_ids),
        ).fetchall()
        bound = 0
        for sid, mid in rows:
            if not mid:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO v1_case_materials "
                "(case_id, material_id, signal_id) VALUES (?, ?, ?)",
                (case_id, mid, sid),
            )
            bound += 1
        conn.commit()
        return bound

    # ------------------------------------------------------------------
    # get / list
    # ------------------------------------------------------------------
    def get_case(self, case_id: str) -> Case:
        rec = self._repo.get(case_id)
        if rec is None:
            raise CaseNotFoundError(f"case {case_id} not found")
        return self._record_to_case(rec)

    def list_cases(
        self,
        *,
        status: list[str] | None = None,
        priority: list[str] | None = None,
        owner_role: str | None = None,
        subject_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Case]:
        """分页查询, 过滤 status / priority / owner_role / subject_id."""
        if subject_id:
            rows = self._repo.list_by_subject(subject_id, limit=limit, offset=offset)
        else:
            rows = self._repo.list_by_status(
                statuses=status,
                priorities=priority,
                owner_role=owner_role,
                limit=limit,
                offset=offset,
            )
        return [self._record_to_case(r) for r in rows]

    # ------------------------------------------------------------------
    # update — CAS (status 走 update_status, 元数据走 update_metadata)
    # ------------------------------------------------------------------
    def update_case(
        self,
        case_id: str,
        *,
        expected_revision: int,
        status: str | None = None,
        title: str | None = None,
        question: str | None = None,
        goal: str | None = None,
        scope: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        tags: list[str] | None = None,
        related_subject_ids: list[str] | None = None,
        related_signal_ids: list[str] | None = None,
        related_case_ids: list[str] | None = None,
        reason: str | None = None,
    ) -> Case:
        """CAS update — 不匹配抛 CaseConflictError (409)."""
        existing = self._repo.get(case_id)
        if existing is None:
            raise CaseNotFoundError(f"case {case_id} not found")
        if existing.revision != expected_revision:
            raise CaseConflictError(
                f"revision mismatch: expected={expected_revision} current={existing.revision}",
                current_revision=existing.revision,
                current_status=existing.status,
            )

        # status 单独路径 (closed_at 自动落)
        if status and CaseStatus(status) != CaseStatus(existing.status):
            closed_at = (
                datetime.now(timezone.utc).isoformat()
                if CaseStatus(status) == CaseStatus.closed
                else None
            )
            updated = self._repo.update_status(
                case_id,
                new_status=status,
                expected_revision=expected_revision,
                closed_at=closed_at,
            )
            if updated is None:
                # race: row 改了 → 再 fetch 拿真实 revision
                cur = self._repo.get(case_id)
                raise CaseConflictError(
                    "concurrent update detected",
                    current_revision=cur.revision if cur else None,
                    current_status=cur.status if cur else None,
                )
            existing = updated

        # metadata update
        meta_updates: dict[str, Any] = {}
        if title is not None:
            meta_updates["title"] = title
        if question is not None:
            meta_updates["question"] = question
        if goal is not None:
            meta_updates["goal"] = goal
        if scope is not None:
            meta_updates["scope"] = scope
        if priority is not None:
            meta_updates["priority"] = priority
        if due_at is not None:
            meta_updates["due_at"] = due_at
        if tags is not None:
            meta_updates["tags"] = tags
        if related_subject_ids is not None:
            meta_updates["related_subject_ids"] = related_subject_ids
        if related_signal_ids is not None:
            meta_updates["related_signal_ids"] = related_signal_ids
        if related_case_ids is not None:
            meta_updates["related_case_ids"] = related_case_ids

        if meta_updates:
            cur_rev = existing.revision
            updated = self._repo.update_metadata(case_id, cur_rev, meta_updates)
            if updated is None:
                cur = self._repo.get(case_id)
                raise CaseConflictError(
                    "concurrent metadata update detected",
                    current_revision=cur.revision if cur else None,
                    current_status=cur.status if cur else None,
                )
            existing = updated

        return self._record_to_case(existing, reason=reason)

    # ------------------------------------------------------------------
    # close_case — 校验无 active run, 落 closed_at
    # ------------------------------------------------------------------
    def close_case(self, case_id: str, *, expected_revision: int) -> Case:
        """关闭 Case: 校验无 active run + 落 closed_at.

        v1.0 C08 R17 修复 — 关闭 4 守卫:
        (a) 所有 v1_actions 全终态 (succeeded/failed/cancelled/rejected)
        (b) 任何 active v1_runs (queued/claimed/running) 不得存在
        (c) 至少 1 个 verified/accepted v1_artifact (经 v1_runs 关联)
        (d) 至少 1 个 published v1_judgment
            (研究型 case 无 action 但有 published judgment 可直接关)
        """
        existing = self._repo.get(case_id)
        if existing is None:
            raise CaseNotFoundError(f"case {case_id} not found")
        if existing.status == CaseStatus.closed.value:
            raise CaseConflictError("case already closed")
        if existing.revision != expected_revision:
            raise CaseConflictError(
                f"revision mismatch: expected={expected_revision} current={existing.revision}",
                current_revision=existing.revision,
                current_status=existing.status,
            )

        from backend.repository.db import get_connection

        conn = get_connection()

        # (a) 所有 action 全终态
        active_actions = conn.execute(
            "SELECT id, status FROM v1_actions WHERE case_id = ? "
            "AND status IN ('planned', 'approved', 'running')",
            (case_id,),
        ).fetchall()
        if active_actions:
            ids = ", ".join(r[0] for r in active_actions)
            raise CaseConflictError(
                f"case has {len(active_actions)} active action(s) [{ids}]; "
                f"resolve all actions to terminal state first (R17: planned/approved/running must end)",
                current_revision=existing.revision,
                current_status=existing.status,
            )

        # (b) 无 active run (queued/claimed/running)
        active_runs = conn.execute(
            "SELECT r.id, r.status FROM v1_runs r "
            "JOIN v1_actions a ON r.action_id = a.id "
            "WHERE a.case_id = ? AND r.status IN ('queued', 'claimed', 'running')",
            (case_id,),
        ).fetchall()
        if active_runs:
            ids = ", ".join(r[0] for r in active_runs)
            raise CaseConflictError(
                f"case has {len(active_runs)} active run(s) [{ids}]; "
                f"wait for all runs to finish (R17: queued/claimed/running must end)",
                current_revision=existing.revision,
                current_status=existing.status,
            )

        # (c) 至少 1 verified/accepted artifact
        # 研究型 case (无 action) → 只要 (d) published judgment 即可, 跳过 (c)
        any_action = conn.execute(
            "SELECT 1 FROM v1_actions WHERE case_id = ? LIMIT 1", (case_id,),
        ).fetchone()
        if any_action:
            # action 全部 cancelled/rejected (无实际 work) → 视为研究型, 不要求 artifact
            any_succeeded_or_running = conn.execute(
                "SELECT 1 FROM v1_actions WHERE case_id = ? "
                "AND status IN ('succeeded', 'approved', 'running', 'planned', 'failed') LIMIT 1",
                (case_id,),
            ).fetchone()
            if any_succeeded_or_running is not None:
                # 至少 1 个真执行过的 action → 必带 verified/accepted artifact
                verified_artifacts = conn.execute(
                    "SELECT COUNT(*) FROM v1_artifacts ar "
                    "JOIN v1_runs r ON ar.run_id = r.id "
                    "JOIN v1_actions a ON r.action_id = a.id "
                    "WHERE a.case_id = ? AND ar.status IN ('verified', 'accepted')",
                    (case_id,),
                ).fetchone()[0]
                if verified_artifacts == 0:
                    raise CaseConflictError(
                        "case has executed actions but no verified/accepted artifact (R17: "
                        "must have ≥1 verified artifact before close)",
                        current_revision=existing.revision,
                        current_status=existing.status,
                    )

        # (d) 至少 1 published judgment
        published_judgments = conn.execute(
            "SELECT COUNT(*) FROM v1_judgments WHERE case_id = ? AND status = 'published'",
            (case_id,),
        ).fetchone()[0]
        if published_judgments == 0:
            raise CaseConflictError(
                "case has no published judgment (R17: "
                "must publish ≥1 judgment before close)",
                current_revision=existing.revision,
                current_status=existing.status,
            )

        closed_at = datetime.now(timezone.utc).isoformat()
        updated = self._repo.update_status(
            case_id,
            new_status=CaseStatus.closed.value,
            expected_revision=expected_revision,
            closed_at=closed_at,
        )
        if updated is None:
            cur = self._repo.get(case_id)
            raise CaseConflictError(
                "concurrent update detected",
                current_revision=cur.revision if cur else None,
                current_status=cur.status if cur else None,
            )
        return self._record_to_case(updated, reason="closed")