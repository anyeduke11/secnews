"""v1.0 T13 KnowledgeService — 4 态机 + 复用派生 + 复查 + wiki 不可变写.

对应 contracts.md §9 (Knowledge) + §9.4 (ReuseReceipt 派生) + EXECUTION_GUIDE §T13.

状态机 (4 态, §9.2):
  draft → publish → published → deprecate → deprecated
                     │  ↑                │
                     │  retract           ▼
                     ▼                (review_at 触发复审, 不改 status)
                  retracted (终态, allowed_actions=[])

§9.3 allowed_actions:
  draft       → [edit, publish, discard]
  published   → [create_revision, deprecate, retract]
  deprecated  → [revive]
  retracted   → []  (终态)

SK-05 复用记录 (ReuseReceipt, §9.4): 派生自 v1_knowledge_refs 关联表; 不存新表.
SK-06 复查: 每日 review_due job 扫 review_at ≤ now + published → 挂 case blocker.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.knowledge_revision_repo import (
    KnowledgeRefRepository,
    KnowledgeRevisionRepository,
)
from backend.repository.v1_knowledge_repo import V1KnowledgeRepository as KnowledgeRepository
from backend.services.dsh_adapter import run_dsh_sync


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------
class KnowledgeValidationError(InvalidParamException):
    def __init__(self, message: str = "knowledge validation failed") -> None:
        super().__init__(message)


class KnowledgeNotFoundError(NotFoundException):
    def __init__(self, message: str = "knowledge not found") -> None:
        super().__init__(message)


class KnowledgeConflictError(ConflictException):
    def __init__(self, message: str = "knowledge state conflict") -> None:
        super().__init__(message)


# 状态机 + allowed_actions (contracts §9.3 + C13 第 5 态 'legacy')
# legacy 状态 (C13): 旧数据迁移入 v1_knowledge 的初始态, 业务禁止
# publish→legacy 或 legacy→published 业务直接跳; 只能由后台 promote job
# (LegacyMigrateServiceV1._promote_legacy) 走专用守卫, allowed_actions 限定 promote/retract.
_KNOWLEDGE_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "draft": ["edit", "publish", "discard"],
    "published": ["create_revision", "deprecate", "retract"],
    "deprecated": ["revive"],
    "retracted": [],
    "legacy": ["promote", "retract"],   # C13: 仅 promote (走后台 job) / retract
}

_VALID_KIND = {"principle", "pattern", "anti_pattern", "reference", "playbook", "checklist"}
_VALID_STATUS = set(_KNOWLEDGE_ALLOWED_ACTIONS.keys())

_TITLE_MAX_BYTES = 200
_BODY_MAX_BYTES = 100_000


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ulid26() -> str:
    """26 字符 ULID (random.choice, 不用确定性避免 UNIQUE 撞库 — T11 fix)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _content_hash(
    body: str, prerequisites: list[str], counter_examples: list[str], evidence_refs: list[dict[str, Any]],
) -> str:
    import json
    return hashlib.sha256(
        json.dumps(
            {"body": body, "prerequisites": sorted(prerequisites),
             "counter_examples": sorted(counter_examples), "evidence_refs": evidence_refs},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _material_hash_lookup(material_ids: list[str]) -> dict[str, str]:
    if not material_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" for _ in material_ids)
    rows = conn.execute(
        f"SELECT id, content_hash FROM v1_materials WHERE id IN ({placeholders})",
        material_ids,
    ).fetchall()
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------------------
# KnowledgeService
# ---------------------------------------------------------------------------
class KnowledgeService:
    """Knowledge 服务 — 4 态机 + 复用派生 + 复查."""

    def __init__(
        self,
        repo: KnowledgeRepository | None = None,
        revision_repo: KnowledgeRevisionRepository | None = None,
        ref_repo: KnowledgeRefRepository | None = None,
        *, dsh_caller: Callable[[str], str] | None = None,
    ) -> None:
        self.repo = repo or KnowledgeRepository()
        self.revision_repo = revision_repo or KnowledgeRevisionRepository()
        self.ref_repo = ref_repo or KnowledgeRefRepository()
        self._dsh_caller = dsh_caller

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def _validate_create_payload(
        self, *, kind: str, title: str, body: str,
        prerequisites: list[str], counter_examples: list[str],
        evidence_refs: list[dict[str, Any]], review_at: str | None,
        expiry_at: str | None,
    ) -> None:
        if kind not in _VALID_KIND:
            raise KnowledgeValidationError(f"invalid kind: {kind}")
        if not title or not title.strip():
            raise KnowledgeValidationError("title must be non-empty")
        if len(title.encode("utf-8")) > _TITLE_MAX_BYTES:
            raise KnowledgeValidationError(f"title exceeds {_TITLE_MAX_BYTES} bytes")
        if not body or not body.strip():
            raise KnowledgeValidationError("body must be non-empty")
        if len(body.encode("utf-8")) > _BODY_MAX_BYTES:
            raise KnowledgeValidationError(f"body exceeds {_BODY_MAX_BYTES} bytes")
        if not isinstance(prerequisites, list) or len(prerequisites) == 0:
            raise KnowledgeValidationError("prerequisites must be non-empty list (SK-04 硬约束)")
        if not isinstance(counter_examples, list):
            raise KnowledgeValidationError("counter_examples must be list")
        if not isinstance(evidence_refs, list) or len(evidence_refs) == 0:
            raise KnowledgeValidationError("evidence_refs must be non-empty list")
        for ref in evidence_refs:
            if not isinstance(ref, dict) or "material_id" not in ref or "hash" not in ref:
                raise KnowledgeValidationError("evidence_refs[i] must have material_id + hash")
        if not review_at:
            raise KnowledgeValidationError("review_at required (SK-06 触发)")

    def _validate_evidence_hashes(self, evidence_refs: list[dict[str, Any]]) -> None:
        material_ids = [r["material_id"] for r in evidence_refs]
        actual = _material_hash_lookup(material_ids)
        for ref in evidence_refs:
            mid = ref["material_id"]
            if mid not in actual:
                raise KnowledgeValidationError(f"material {mid} not found in v1_materials")
            if actual[mid] != ref["hash"]:
                raise KnowledgeValidationError(
                    f"evidence_refs hash mismatch for {mid}: given={ref['hash'][:16]}... actual={actual[mid][:16]}..."
                )

    # ------------------------------------------------------------------
    # create_with_dsh (T13 SK-04 主路径)
    # ------------------------------------------------------------------
    def create_with_dsh(
        self,
        *,
        case_id: str,
        judgment_id: str,
        action_id: str,
        subject_name: str,
        cve_id: str,
        kind: str,
        evidence_materials: list[dict[str, Any]],
        submitted_by: str = "user",
    ) -> dict[str, Any]:
        """通过 dsh (或 mock) 生成 knowledge 经验, 落库成 draft.

        Returns
        -------
        {"knowledge": <dict>, "idempotent_replay": bool}
        """
        from backend.services.ai_hub.prompts import (
            build_knowledge_prompt,
            parse_knowledge_publish_response,
        )
        prompt = build_knowledge_prompt(
            case_id=case_id, judgment_id=judgment_id, action_id=action_id,
            subject_name=subject_name, cve_id=cve_id, kind=kind,
            evidence_materials=evidence_materials,
        )
        raw = self._call_dsh(prompt)
        try:
            parsed = parse_knowledge_publish_response(raw)
        except ValueError as e:
            raise KnowledgeValidationError(f"dsh response parse failed: {e}") from e
        # 校验
        self._validate_create_payload(
            kind=kind, title=parsed["title"], body=parsed["body"],
            prerequisites=parsed["prerequisites"], counter_examples=parsed["counter_examples"],
            evidence_refs=parsed["evidence_refs"], review_at=parsed["review_at"],
            expiry_at=parsed.get("expiry_at"),
        )
        # evidence hash 校验
        self._validate_evidence_hashes(parsed["evidence_refs"])
        # 落库
        return self._insert_draft(
            case_id=case_id, kind=kind, parsed=parsed, submitted_by=submitted_by,
            source_judgment_id=judgment_id, source_action_id=action_id,
        )

    def _call_dsh(self, prompt: str) -> str:
        """调 dsh (settings.kv 切换 mock/stdio/http). 失败兜底 ai_hub (显式).

        C06 R07 fix + D3 节点降级: 同 judgment/action.
        """
        if self._dsh_caller is not None:
            return self._dsh_caller(prompt)
        from backend.services.dsh_adapter import DSHVendorUnavailableError
        try:
            return run_dsh_sync(
                prompt, task="knowledge_publish", timeout_s=30.0,
                caller_service="knowledge", dsh_caller=None,
            )
        except DSHVendorUnavailableError as e:
            logger.warning(
                "knowledge._call_dsh D3 exit_criteria: 真 vendor 不可用, "
                "fallback 到 ai_hub (确定性协调器); commit_sha=%s; err=%s",
                e.commit_sha, e,
            )
        try:
            import asyncio

            from backend.services.ai_hub.service import ai_service
            return asyncio.run(ai_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                task="knowledge_publish", max_tokens=8000, temperature=0.2,
            ))
        except Exception as e2:
            raise KnowledgeValidationError(
                f"dsh (D3 exit_criteria triggered) + ai_hub both failed: {e2}"
            ) from e2

    def _insert_draft(
        self, *, case_id: str, kind: str, parsed: dict[str, Any],
        submitted_by: str, source_judgment_id: str, source_action_id: str,
    ) -> dict[str, Any]:
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
        self.repo.insert(body)
        # 关联 source refs (judgment + action)
        if source_judgment_id:
            self.ref_repo.add(kid, "judgment", source_judgment_id, role="used")
        if source_action_id:
            self.ref_repo.add(kid, "action", source_action_id, role="used")
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

    # ------------------------------------------------------------------
    # publish (CAS 守卫, §9.2)
    # ------------------------------------------------------------------
    def publish(self, knowledge_id: str, *, expected_revision: int) -> dict[str, Any]:
        """publish draft → published; 落 wiki_path + content_hash + revision; append revision.

        v1.0 C08 R10 修复:
        1. wiki_path 改为 `items/knowledge_{id}.md` 走 WikiFs items 目录
           (而非字面 `knowledge/{id}.md` 相对 cwd 路径污染生产仓库)
        2. wiki 写失败必须 raise (RuntimeError), 不吞 — 失败即 publish 失败,
           DB 状态不会变 published (写前无 update_status_cas, 失败不影响一致性)
        """
        k = self._require(knowledge_id)
        if k["status"] != "draft":
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} (publish requires draft)"
            )
        if k["revision"] != expected_revision:
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} revision mismatch: expected={expected_revision}, actual={k['revision']}"
            )
        # R10 canonical path: WikiFs 写 items/knowledge_{id}.md (env-rooted, 不字面)
        wiki_path = f"items/knowledge_{knowledge_id}.md"
        now = _utcnow_iso()
        # R10 fix: wiki 写失败必须 raise, 不吞. _write_wiki 内部已 RuntimeError.
        self._write_wiki(wiki_path, k, now)
        rowcount = self.repo.update_status_cas(
            knowledge_id, "published", expected_revision=expected_revision,
            published_at=now, wiki_path=wiki_path,
            allowed_actions=_KNOWLEDGE_ALLOWED_ACTIONS["published"], reason=None,
        )
        if rowcount == 0:
            raise KnowledgeConflictError(f"knowledge {knowledge_id} CAS race")
        # append revision
        self.revision_repo.append({
            "knowledge_id": knowledge_id, "revision": expected_revision + 1,
            "status": "published", "reason": None, "wiki_path": wiki_path,
            "content_hash": k.get("content_hash"),
            "recorded_at": now, "recorded_by": "user",
        })
        result = self._require(knowledge_id)
        self._publish_v1_knowledge_event(result, "published")
        return result

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

    def deprecate(
        self, knowledge_id: str, *, expected_revision: int, reason: str,
        replacement_knowledge_id: str | None = None,
    ) -> dict[str, Any]:
        """published → deprecated (必填 reason + 替代 knowledge_id)."""
        k = self._require(knowledge_id)
        if k["status"] != "published":
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} (deprecate requires published)"
            )
        if k["revision"] != expected_revision:
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} revision mismatch: expected={expected_revision}, actual={k['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            knowledge_id, "deprecated", expected_revision=expected_revision,
            deprecation_reason=reason,
            replacement_knowledge_id=replacement_knowledge_id,
            allowed_actions=_KNOWLEDGE_ALLOWED_ACTIONS["deprecated"], reason=reason,
        )
        if rowcount == 0:
            raise KnowledgeConflictError(f"knowledge {knowledge_id} CAS race")
        self.revision_repo.append({
            "knowledge_id": knowledge_id, "revision": expected_revision + 1,
            "status": "deprecated", "reason": reason, "wiki_path": k.get("wiki_path"),
            "content_hash": k.get("content_hash"), "recorded_at": _utcnow_iso(), "recorded_by": "user",
        })
        # C12 R16.4: 弃用后挂 blocker 到所有 adopted 该知识的活跃 case
        self._attach_blocker_to_adopted_cases(
            knowledge_id, f"knowledge_deprecated:{knowledge_id}",
        )
        result = self._require(knowledge_id)
        self._publish_v1_knowledge_event(result, "deprecated")
        return result

    def retract(
        self, knowledge_id: str, *, expected_revision: int, reason: str,
    ) -> dict[str, Any]:
        """published|deprecated → retracted (终态, contracts §10.3 不删 wiki).

        C12 R16.4: 撤回后, 扫 v1_knowledge_adoptions 决策=adopted 的活跃 case,
        挂 'knowledge_retracted:{kid}' blocker tag; 提示用户该知识已失效.
        append-only: 不写 adoption 历史 (保留以备审计).
        """
        k = self._require(knowledge_id)
        if k["status"] not in ("published", "deprecated"):
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} (retract requires published/deprecated)"
            )
        if k["revision"] != expected_revision:
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} revision mismatch: expected={expected_revision}, actual={k['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            knowledge_id, "retracted", expected_revision=expected_revision,
            retraction_reason=reason,
            allowed_actions=_KNOWLEDGE_ALLOWED_ACTIONS["retracted"], reason=reason,
        )
        if rowcount == 0:
            raise KnowledgeConflictError(f"knowledge {knowledge_id} CAS race")
        self.revision_repo.append({
            "knowledge_id": knowledge_id, "revision": expected_revision + 1,
            "status": "retracted", "reason": reason, "wiki_path": k.get("wiki_path"),
            "content_hash": k.get("content_hash"), "recorded_at": _utcnow_iso(), "recorded_by": "user",
        })
        # C12 R16.4: 挂 blocker 到所有 adopted 该知识的活跃 case
        self._attach_blocker_to_adopted_cases(
            knowledge_id, f"knowledge_retracted:{knowledge_id}",
        )
        result = self._require(knowledge_id)
        self._publish_v1_knowledge_event(result, "retracted")
        return result

    def revive(
        self, knowledge_id: str, *, expected_revision: int,
    ) -> dict[str, Any]:
        """deprecated → published (revision + 1)."""
        k = self._require(knowledge_id)
        if k["status"] != "deprecated":
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} (revive requires deprecated)"
            )
        if k["revision"] != expected_revision:
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} revision mismatch: expected={expected_revision}, actual={k['revision']}"
            )
        rowcount = self.repo.update_status_cas(
            knowledge_id, "published", expected_revision=expected_revision,
            allowed_actions=_KNOWLEDGE_ALLOWED_ACTIONS["published"], reason="revived from deprecated",
        )
        if rowcount == 0:
            raise KnowledgeConflictError(f"knowledge {knowledge_id} CAS race")
        self.revision_repo.append({
            "knowledge_id": knowledge_id, "revision": expected_revision + 1,
            "status": "published", "reason": "revived", "wiki_path": k.get("wiki_path"),
            "content_hash": k.get("content_hash"), "recorded_at": _utcnow_iso(), "recorded_by": "user",
        })
        return self._require(knowledge_id)

    # ------------------------------------------------------------------
    # C13 第 5 态 'legacy' 守卫 (仅后台 promote job / admin 可跳, 业务 publish/deprecate 不允许)
    # ------------------------------------------------------------------
    def promote_legacy(
        self, knowledge_id: str, *, reason: str, promoted_by: str = "system",
    ) -> dict[str, Any]:
        """legacy → published (C13 专用, 业务调用会被 5 态机守卫拒绝).

        走 CAS + revision+1 + 写 revision_repo. 不允许业务 publish 路径调用
        (publish() 走 _require 守卫 'draft' 起点, 不会从 legacy 进入).
        复用 LegacyMigrateServiceV1._promote_legacy (含 v1_legacy_promote_log 持久).
        """
        from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
        migrate_svc = LegacyMigrateServiceV1()
        migrate_svc._promote_legacy(knowledge_id, reason=reason)
        k = self._require(knowledge_id)
        self.revision_repo.append({
            "knowledge_id": knowledge_id, "revision": k.get("revision", 1),
            "status": "published", "reason": f"C13 legacy→published by {promoted_by}: {reason}",
            "wiki_path": k.get("wiki_path"),
            "content_hash": k.get("content_hash"),
            "recorded_at": _utcnow_iso(), "recorded_by": promoted_by,
        })
        self._publish_v1_knowledge_event(k, "published")
        return k

    # ------------------------------------------------------------------
    # list / get / reuse (SK-05 派生)
    # ------------------------------------------------------------------
    def list_by_case(
        self, case_id: str, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in _VALID_STATUS:
            raise KnowledgeValidationError(f"invalid status: {status}")
        if kind and kind not in _VALID_KIND:
            raise KnowledgeValidationError(f"invalid kind: {kind}")
        items, total = self.repo.list_by_case(
            case_id, status=status, kind=kind, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def list_all(
        self, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        """T15.5 全局 list (KnowledgeView 走真实 listAll 替换 placeholder)."""
        if status and status not in _VALID_STATUS:
            raise KnowledgeValidationError(f"invalid status: {status}")
        if kind and kind not in _VALID_KIND:
            raise KnowledgeValidationError(f"invalid kind: {kind}")
        items, total = self.repo.list_all(
            status=status, kind=kind, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, knowledge_id: str) -> dict[str, Any]:
        return self._require(knowledge_id)

    def get_reuse_receipt(self, knowledge_id: str) -> dict[str, Any]:
        """C12 R16.5: ReuseReceipt 只数 adoptions, 弃用 by_judgment/by_action.

        Returns
        -------
        {
            "total": int,                       # 决策=adopted 计数
            "by_decision": {adopted, skipped, rejected},
            "by_outcome": {success, partial, failure, unknown},
            "recent_30d": int,                  # 30 天内 adoptions 数
        }
        """
        self._require(knowledge_id)
        conn = get_connection()
        # 决策分布
        decision_rows = conn.execute(
            "SELECT decision, COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? GROUP BY decision",
            (knowledge_id,),
        ).fetchall()
        by_decision: dict[str, int] = {}
        total = 0
        for dec, cnt in decision_rows:
            by_decision[dec] = cnt
            if dec == "adopted":
                total = cnt
        # 结果分布
        outcome_rows = conn.execute(
            "SELECT COALESCE(outcome,'unknown'), COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted' GROUP BY outcome",
            (knowledge_id,),
        ).fetchall()
        by_outcome: dict[str, int] = {}
        for out, cnt in outcome_rows:
            by_outcome[out] = cnt
        # 30 天内
        recent_30d_row = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted' "
            "AND adopted_at >= datetime('now', '-30 days')",
            (knowledge_id,),
        ).fetchone()
        recent_30d = int(recent_30d_row[0]) if recent_30d_row else 0
        return {
            "total": total,
            "by_decision": by_decision,
            "by_outcome": by_outcome,
            "recent_30d": recent_30d,
        }

    # ------------------------------------------------------------------
    # C12 R16 — knowledge adoption (derived_from vs adopted_by 物理分离)
    # ------------------------------------------------------------------
    def record_adoption(
        self,
        *,
        knowledge_id: str,
        case_id: str,
        condition_diff: list[dict[str, Any]],
        decision: str,
        decided_by: str,
        adopted_by: str | None = None,
    ) -> dict[str, Any]:
        """C12 R16.2: 记录一次知识采用 → 物理写 v1_knowledge_adoptions (新表).

        Parameters
        ----------
        knowledge_id :  采用的知识 id
        case_id      :  采用方 case (与原创建 case 可不同, 跨 case 复用)
        condition_diff: 与原 conditions/counter_examples 的差异 list
                       [{field, expected, actual, severity}, ...]
        decision     :  adopted|skipped|rejected
        decided_by   :  决策人 (who)
        adopted_by   :  默认 decided_by (保留双字段, audit 区分)

        Returns
        -------
        {id, knowledge_id, knowledge_revision, case_id, decision, ...}
        """
        if decision not in ("adopted", "skipped", "rejected"):
            raise KnowledgeValidationError(
                f"decision must be adopted|skipped|rejected, got {decision!r}"
            )
        k = self._require(knowledge_id)
        if k["status"] not in ("published", "deprecated"):
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} "
                f"(adoption requires published/deprecated)"
            )
        # case 必存
        conn = get_connection()
        row = conn.execute("SELECT 1 FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KnowledgeValidationError(f"case {case_id} not found")
        now = _utcnow_iso()
        cur = conn.execute(
            "SELECT id, decision, condition_diff_json, outcome, outcome_note, "
            "adopted_at, adopted_by, decided_by FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND knowledge_revision = ? AND case_id = ?",
            (knowledge_id, k["revision"], case_id),
        ).fetchone()
        if cur is not None:
            # 幂等: 已有 adoption 行, update decision + diff
            conn.execute(
                "UPDATE v1_knowledge_adoptions SET decision = ?, "
                "condition_diff_json = ?, decided_by = ?, adopted_by = ?, "
                "adopted_at = ? WHERE id = ?",
                (
                    decision,
                    json.dumps(condition_diff, ensure_ascii=False),
                    decided_by,
                    adopted_by or decided_by,
                    now,
                    cur[0],
                ),
            )
            conn.commit()
            return {
                "id": cur[0], "knowledge_id": knowledge_id,
                "knowledge_revision": k["revision"], "case_id": case_id,
                "decision": decision, "outcome": cur[3],
                "outcome_note": cur[4], "adopted_at": now,
                "adopted_by": adopted_by or decided_by, "decided_by": decided_by,
            }
        # 全新 adoption 行
        cur = conn.execute(
            "INSERT INTO v1_knowledge_adoptions (knowledge_id, knowledge_revision, "
            "case_id, decision, condition_diff_json, outcome, outcome_note, "
            "adopted_at, adopted_by, decided_by) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
            (
                knowledge_id, k["revision"], case_id, decision,
                json.dumps(condition_diff, ensure_ascii=False),
                now, adopted_by or decided_by, decided_by,
            ),
        )
        conn.commit()
        return {
            "id": cur.lastrowid, "knowledge_id": knowledge_id,
            "knowledge_revision": k["revision"], "case_id": case_id,
            "decision": decision, "outcome": None, "outcome_note": None,
            "adopted_at": now,
            "adopted_by": adopted_by or decided_by, "decided_by": decided_by,
        }

    def record_outcome(
        self,
        *,
        knowledge_id: str,
        case_id: str,
        outcome: str,
        outcome_note: str | None = None,
    ) -> dict[str, Any]:
        """C12 R16.6: 记录采用结果 (success|partial|failure).

        同一 case 多次 outcome 以最后一条为准 (append-only-ish: 走 UPDATE).
        outcome 不影响 total 计数 (只改 by_outcome 分布).
        """
        if outcome not in ("success", "partial", "failure"):
            raise KnowledgeValidationError(
                f"outcome must be success|partial|failure, got {outcome!r}"
            )
        self._require(knowledge_id)
        conn = get_connection()
        row = conn.execute(
            "SELECT id, knowledge_revision FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND case_id = ? AND decision = 'adopted'",
            (knowledge_id, case_id),
        ).fetchone()
        if row is None:
            raise KnowledgeValidationError(
                f"no adopted row for knowledge {knowledge_id} case {case_id} "
                f"(record_adoption first)"
            )
        conn.execute(
            "UPDATE v1_knowledge_adoptions SET outcome = ?, outcome_note = ? "
            "WHERE id = ?",
            (outcome, outcome_note, row[0]),
        )
        conn.commit()
        return {
            "id": row[0], "knowledge_id": knowledge_id,
            "knowledge_revision": row[1], "case_id": case_id,
            "outcome": outcome, "outcome_note": outcome_note,
        }

    # ------------------------------------------------------------------
    # 只读查询 (Batch 2 D: api 层 SQL 下沉落点 — case_api / knowledge_api)
    # ------------------------------------------------------------------
    def case_reuse_summary(self, case_id: str) -> dict[str, Any]:
        """v0.8.5 D4: 复利卡 (诚实计数) — 本 case 的知识采用/回执汇总.

        只报真实记录数 (v1_knowledge_adoptions), 不做「节省 X 小时」类
        无基线估算。表缺失等异常显零值不阻断聚合 (与原 api 行为一致)。
        """
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT COUNT(*), "
                "COALESCE(SUM(CASE WHEN adopted_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END), 0), "
                "COUNT(DISTINCT knowledge_id) "
                "FROM v1_knowledge_adoptions WHERE case_id = ? AND decision = 'adopted'",
                (case_id,),
            ).fetchone()
            return {
                "adoptions_total": row[0] or 0,
                "adoptions_30d": row[1] or 0,
                "distinct_knowledge": row[2] or 0,
            }
        except Exception:
            return {"adoptions_total": 0, "adoptions_30d": 0, "distinct_knowledge": 0}

    def list_adoptions(self, knowledge_id: str) -> list[dict[str, Any]]:
        """C12 R16: 列出该 knowledge 的所有 adoptions (按 adopted_at 倒序).

        condition_diff JSON 反序列化在 service 内完成, api 只包装 version。
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, case_id, knowledge_revision, decision, condition_diff_json, "
            "outcome, outcome_note, adopted_at, adopted_by, decided_by "
            "FROM v1_knowledge_adoptions WHERE knowledge_id = ? "
            "ORDER BY adopted_at DESC",
            (knowledge_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            try:
                diff = json.loads(r[4]) if r[4] else []
            except (json.JSONDecodeError, TypeError):
                diff = []
            items.append({
                "id": r[0], "case_id": r[1], "knowledge_revision": r[2],
                "decision": r[3], "condition_diff": diff,
                "outcome": r[5], "outcome_note": r[6],
                "adopted_at": r[7], "adopted_by": r[8], "decided_by": r[9],
            })
        return items

    def recall_for_case(
        self, case_id: str, *, knowledge_id: str,
    ) -> dict[str, Any]:
        """C12 R16.3: 召回 — 返回 {applicable, prerequisite_match,
        counter_example_conflict, adoption_history}.

        applicable  = knowledge.status in (published, deprecated) AND case 存在
        prerequisite_match: 本次 case 是否满足知识 prerequisites
        counter_example_conflict: 本次 case 是否撞到 counter_examples
        adoption_history: 同 knowledge + 其他 case 的 adoption 历史
                          [{case_id, condition_diff, outcome, adopted_at}, ...]
        """
        k = self._require(knowledge_id)
        conn = get_connection()
        # 拿 knowledge 静态条件
        prereqs = list(k.get("prerequisites") or [])
        counters = list(k.get("counter_examples") or [])
        # 拿 case 的 (T08 暂未存 prerequisites 字段, 用 tags_json 弱匹配)
        row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        case_tags = json.loads(row[0]) if row and row[0] else []
        # 弱匹配: 知识 prereq 在 case tags 出现 → 满足
        prereq_match = all(p in case_tags for p in prereqs) if prereqs else True
        counter_conflict = any(c in case_tags for c in counters) if counters else False
        # 召回其他 case 的 adoption 历史 (排除当前 case 本身)
        history_rows = conn.execute(
            "SELECT case_id, condition_diff_json, outcome, adopted_at, decision "
            "FROM v1_knowledge_adoptions WHERE knowledge_id = ? "
            "AND case_id != ? ORDER BY adopted_at DESC",
            (knowledge_id, case_id),
        ).fetchall()
        adoption_history: list[dict[str, Any]] = []
        for cr, cdf, out, at, dec in history_rows:
            try:
                cdf_parsed = json.loads(cdf) if cdf else []
            except (json.JSONDecodeError, TypeError):
                cdf_parsed = []
            adoption_history.append({
                "case_id": cr, "condition_diff": cdf_parsed,
                "outcome": out, "adopted_at": at, "decision": dec,
            })
        return {
            "knowledge_id": knowledge_id,
            "case_id": case_id,
            "applicable": k["status"] in ("published", "deprecated"),
            "knowledge_status": k["status"],
            "prerequisite_match": prereq_match,
            "counter_example_conflict": counter_conflict,
            "prerequisites": prereqs,
            "counter_examples": counters,
            "adoption_history": adoption_history,
        }

    def _attach_blocker_to_adopted_cases(
        self, knowledge_id: str, marker: str,
    ) -> int:
        """C12 R16.4 辅助: 扫 v1_knowledge_adoptions WHERE decision=adopted,
        给每个 case 挂 marker tag (无重复). 返受影响 case 数.

        append-only: 不写 adoption 历史 (旧行不动).
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT case_id FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted'",
            (knowledge_id,),
        ).fetchall()
        affected = 0
        for (case_id,) in rows:
            row = conn.execute(
                "SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,),
            ).fetchone()
            if row is None:
                continue
            tags = json.loads(row[0] or "[]")
            if marker in tags:
                continue
            tags.append(marker)
            conn.execute(
                "UPDATE v1_cases SET tags_json = ?, "
                "updated_at = datetime('now', 'localtime') WHERE id = ?",
                (json.dumps(tags, ensure_ascii=False), case_id),
            )
            affected += 1
        if affected:
            conn.commit()
        return affected

    # ------------------------------------------------------------------
    # SK-06 复查扫描 (供 scheduler job 调用)
    # ------------------------------------------------------------------
    def scan_review_due(self, now_iso: str | None = None) -> list[dict[str, Any]]:
        """扫 review_at <= now AND status=published; 返回待复查 knowledge 列表."""
        now = now_iso or _utcnow_iso()
        return self.repo.list_published_due_for_review(now)

    def mark_case_blocker(self, case_id: str, knowledge_id: str) -> bool:
        """SK-06: 挂 blocker 到 case (v1_cases.tags_json 加 'knowledge_review_due:{knowledge_id}')."""
        conn = get_connection()
        row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            return False
        import json
        tags = json.loads(row[0] or "[]")
        marker = f"knowledge_review_due:{knowledge_id}"
        if marker not in tags:
            tags.append(marker)
            conn.execute(
                "UPDATE v1_cases SET tags_json = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (json.dumps(tags, ensure_ascii=False), case_id),
            )
            conn.commit()
        return True

    def _write_wiki(self, wiki_path: str, k: dict[str, Any], now: str) -> None:
        """wiki 不可变写 (T11/T12 同款路径, T13 knowledge 专属).

        v1.0 C01 R10 修复: WikiFs 根由 env HOTSPOT_WIKI_ROOT 决定, 不写字面
        "knowledge" (相对 cwd 写 <repo>/knowledge/items/... 污染生产仓库).
        与 backend/kl_pipeline/runtime.py:34 一致走 resolve_wiki_root().
        """
        try:
            from backend.wiki_fs.root import resolve_wiki_root
            from backend.wiki_fs.store import WikiFs
            wiki = WikiFs(resolve_wiki_root())
            content = (
                f"---\nid: {k['id']}\ntitle: {k['title']}\n"
                f"kind: {k['kind']}\nstatus: published\n"
                f"published_at: {now}\nreview_at: {k.get('review_at','')}\n---\n\n"
                f"# {k['title']}\n\n{k['body']}\n\n"
                f"## 前提\n" + "\n".join(f"- {p}" for p in k.get("prerequisites", [])) + "\n\n"
                "## 反例\n" + "\n".join(f"- {e}" for e in k.get("counter_examples", [])) + "\n"
            )
            wiki.write_item(f"knowledge_{k['id']}", {
                "fm": {"id": f"knowledge_{k['id']}", "title": k["title"],
                       "kind": k["kind"], "status": "published", "published_at": now},
                "body": content,
            })
        except Exception as e:
            raise RuntimeError(f"wiki write failed: {e}") from e

    def _require(self, knowledge_id: str) -> dict[str, Any]:
        k = self.repo.get(knowledge_id)
        if k is None:
            raise KnowledgeNotFoundError(f"knowledge {knowledge_id} not found")
        return k


# ---------------------------------------------------------------------------
# v0.8.5 D3 (SK-05 升级): Case 创建时自动召回 — 复利飞轮的「传动」
# ---------------------------------------------------------------------------
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def auto_recall_for_case(case: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    """已发布知识 × Case 文本 自动匹配 (读时召回, 无写入).

    匹配语义 (诚实可解释 — 每条候选带 reasons, 不做黑盒打分):
      - CVE 编号命中 (标题/正文) → +5, 单独即可入选
      - 关键词 (case 标题+问题切词, ≥2 字) 命中 → +1/词 (上限 5), 需 ≥2 分入选
    仅 published 参与召回; deprecated/retracted/draft 不出现 (失效知识不作依据).

    Returns
    -------
    [{id, title, kind, revision, score, reasons}] — 按 score DESC, top limit.
    """
    text = f"{case.get('title', '')} {case.get('question', '')}"
    cves = {c.upper() for c in _CVE_RE.findall(text)}
    words = {w.lower() for w in _WORD_RE.findall(text)}
    if not cves and not words:
        return []
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, body, kind, revision FROM v1_knowledge WHERE status = 'published'"
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"auto_recall: v1_knowledge unavailable: {e}")
        return []
    scored: list[dict[str, Any]] = []
    for kid, title, body, kind, revision in rows:
        blob = f"{title or ''} {body or ''}".lower()
        score = 0
        reasons: list[str] = []
        for c in cves:
            if c.lower() in blob:
                score += 5
                reasons.append(f"CVE {c} 命中")
        hits = sorted(w for w in words if w in blob)
        if hits:
            score += min(len(hits), 5)
            shown = "、".join(hits[:4]) + ("…" if len(hits) > 4 else "")
            reasons.append(f"关键词 {len(hits)} 命中 ({shown})")
        if score >= (5 if cves else 2):
            scored.append({
                "id": kid, "title": title, "kind": kind,
                "revision": revision, "score": score, "reasons": reasons,
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def add_agent_link(
    from_id: str, to_id: str, link_type: str, confidence: float,
) -> int:
    """MCP tool link_items 写路径 — agent 持久化 item 间关系 (knowledge_links).

    Batch 2 D: 自 mcp_agent_tools 下沉; created_by 固定 'agent',
    返回新行 link_id。连接为 autocommit (isolation_level=None),
    与原 api 直写行为逐字一致。
    """
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO knowledge_links "
        "(from_item_id, to_item_id, link_type, confidence, created_by) "
        "VALUES (?, ?, ?, ?, 'agent')",
        (from_id, to_id, link_type, confidence),
    )
    return cur.lastrowid
