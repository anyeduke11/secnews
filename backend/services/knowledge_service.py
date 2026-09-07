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
import random
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


# 状态机 + allowed_actions (contracts §9.3)
_KNOWLEDGE_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "draft": ["edit", "publish", "discard"],
    "published": ["create_revision", "deprecate", "retract"],
    "deprecated": ["revive"],
    "retracted": [],
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
        result = self._require(knowledge_id)
        self._publish_v1_knowledge_event(result, "deprecated")
        return result

    def retract(
        self, knowledge_id: str, *, expected_revision: int, reason: str,
    ) -> dict[str, Any]:
        """published|deprecated → retracted (终态, contracts §10.3 不删 wiki)."""
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
        """§9.4 ReuseReceipt 派生: {total, by_judgment, by_action, recent_30d}."""
        self._require(knowledge_id)
        return self.ref_repo.count_by_knowledge(knowledge_id)

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
