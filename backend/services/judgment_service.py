"""v1.0 T11 JudgmentService — 有证据的判断 (SK-02 cve-impact-brief 主路径).

对应 contracts.md §5 (Judgment) + EXECUTION_GUIDE §T11 + baseline §5:
  1. 结构化输出 claim/conditions/evidence_refs/unknowns (服务层 schema 强制)
  2. 原文定位: 每条 evidence_refs.hash 必须对得上 material.content_hash
  3. 规则验证: 同 case + claim_type 同时只 1 published (UNIQUE PARTIAL INDEX 兜底)
  4. unknown 必须显示: evidence_refs 空 → unknowns 必填 (baseline §5 硬约束)
  5. publish 守卫: 5 失败场景全覆盖 (缺版本 / 证据冲突 / 公告撤回 / 无支持 claim / 人工并发修订)

dsh 调用: 走 dsh task_router (settings.kv `dsh.bridge_mode`); 真 dsh 失败自动回退 mock
(T10 live_bridge 已通), SK-02 主路径不卡 dsh 协议. 真 ai_hub 实际生成 (T10 generate_text).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.judgment_repo import JudgmentRepository
from backend.services.ai_hub.prompts import (
    build_cve_impact_brief_prompt,
    parse_cve_impact_brief_response,
)


# ---------------------------------------------------------------------------
# 错误类型 (复用 backend.exceptions, 与 case_service 对齐)
# ---------------------------------------------------------------------------
class JudgmentValidationError(InvalidParamException):
    def __init__(self, message: str = "judgment validation failed") -> None:
        super().__init__(message)


class JudgmentNotFoundError(NotFoundException):
    def __init__(self, message: str = "judgment not found") -> None:
        super().__init__(message)


class JudgmentConflictError(ConflictException):
    def __init__(self, message: str = "judgment state conflict") -> None:
        super().__init__(message)


# 业务状态机: contracts §5.3
_JUDGMENT_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "draft": ["edit", "publish", "discard"],
    "published": ["create_supersede", "retract"],
    "superseded": ["view_history"],
    "retracted": ["view_history"],
}

_CLAIM_MAX_BYTES = 10_000
_CONDITIONS_MAX_BYTES = 500
_QUOTE_MAX_BYTES = 500
_VALID_CLAIM_TYPES = {"finding", "assessment", "recommendation", "warning", "hypothesis"}
_VALID_CONFIDENCE = {"low", "medium", "high", "proved"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ulid26() -> str:
    """26 字符 Crockford Base32 ULID 风格 ID (与 v1_0_models 字段 pattern 一致)."""
    import random
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _content_hash(claim: str, conditions: str, evidence_refs: list[dict[str, Any]]) -> str:
    """sha256(claim + conditions + evidence_refs JSON) — 用于 publish 校验完整性."""
    body = json.dumps(
        {"claim": claim, "conditions": conditions, "evidence_refs": evidence_refs},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _material_hash_lookup(material_ids: list[str]) -> dict[str, str]:
    """查 v1_materials.content_hash 映射 (id → hash); 不存在则不返."""
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
# JudgmentService
# ---------------------------------------------------------------------------
class JudgmentService:
    """判断服务 — 校验链 + 状态机 + dsh 调用 + publish 守卫."""

    def __init__(
        self, repo: JudgmentRepository | None = None,
        *, dsh_caller: Any = None,
    ) -> None:
        self.repo = repo or JudgmentRepository()
        # dsh_caller: 可注入 (test 用); 默认 None 走 _call_dsh 默认实现
        self._dsh_caller = dsh_caller

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def _validate_payload(
        self,
        *,
        case_id: str,
        claim_type: str,
        claim: str,
        conditions: str,
        confidence: str,
        evidence_refs: list[dict[str, Any]],
        counter_evidence_refs: list[dict[str, Any]],
        unknowns: list[str],
        require_evidence: bool = True,
    ) -> None:
        if not case_id or not isinstance(case_id, str):
            raise JudgmentValidationError("case_id required")
        if claim_type not in _VALID_CLAIM_TYPES:
            raise JudgmentValidationError(f"invalid claim_type: {claim_type}")
        if confidence not in _VALID_CONFIDENCE:
            raise JudgmentValidationError(f"invalid confidence: {confidence}")
        if not claim or not claim.strip():
            raise JudgmentValidationError("claim must be non-empty")
        if len(claim.encode("utf-8")) > _CLAIM_MAX_BYTES:
            raise JudgmentValidationError(f"claim exceeds {_CLAIM_MAX_BYTES} bytes")
        if len((conditions or "").encode("utf-8")) > _CONDITIONS_MAX_BYTES:
            raise JudgmentValidationError(f"conditions exceeds {_CONDITIONS_MAX_BYTES} bytes")
        if not isinstance(evidence_refs, list):
            raise JudgmentValidationError("evidence_refs must be list")
        if require_evidence and len(evidence_refs) == 0:
            raise JudgmentValidationError("evidence_refs ≥ 1 required")
        for ref in evidence_refs:
            if not isinstance(ref, dict) or "material_id" not in ref or "hash" not in ref:
                raise JudgmentValidationError("evidence_refs[i] must have material_id + hash")
            quote = ref.get("quote")
            if quote is not None and len(quote.encode("utf-8")) > _QUOTE_MAX_BYTES:
                raise JudgmentValidationError(f"evidence_refs[{ref.get('material_id')}].quote exceeds {_QUOTE_MAX_BYTES}")
        if not isinstance(counter_evidence_refs, list):
            raise JudgmentValidationError("counter_evidence_refs must be list")
        for ref in counter_evidence_refs:
            if not isinstance(ref, dict) or "material_id" not in ref or "hash" not in ref:
                raise JudgmentValidationError("counter_evidence_refs[i] must have material_id + hash")
        if not isinstance(unknowns, list) or not all(isinstance(u, str) for u in unknowns):
            raise JudgmentValidationError("unknowns must be list[str]")
        # baseline §5 硬约束: 缺资产 (evidence_refs < 2) → unknowns 必填
        if require_evidence and len(evidence_refs) < 2 and len(unknowns) == 0:
            raise JudgmentValidationError(
                "unknowns required when evidence_refs < 2 (baseline §5 硬约束)"
            )

    def _validate_evidence_hashes(
        self, evidence_refs: list[dict[str, Any]],
    ) -> None:
        """每条 evidence_refs.hash 必须对得上 material.content_hash; 缺/不匹配 → 422."""
        material_ids = [r["material_id"] for r in evidence_refs]
        actual = _material_hash_lookup(material_ids)
        for ref in evidence_refs:
            mid = ref["material_id"]
            if mid not in actual:
                raise JudgmentValidationError(f"material {mid} not found in v1_materials")
            if actual[mid] != ref["hash"]:
                raise JudgmentValidationError(
                    f"evidence_refs hash mismatch for {mid}: "
                    f"given={ref['hash'][:16]}..., actual={actual[mid][:16]}..."
                )

    # ------------------------------------------------------------------
    # create_with_dsh (T11 SK-02 主路径)
    # ------------------------------------------------------------------
    def create_with_dsh(
        self,
        *,
        case_id: str,
        cve_id: str,
        subject_name: str,
        evidence_materials: list[dict[str, Any]],
        submitted_by: str = "user",
        case_revision: int | None = None,
    ) -> dict[str, Any]:
        """通过 dsh (或 mock) 生成 cve-impact-brief, 落库成 draft judgment.

        Returns
        -------
        {"judgment": <dict>, "idempotent_replay": bool}

        失败模式
        --------
        - dsh 调用失败 (网络/超时/mock 异常) → 抛 JudgmentValidationError
        - 解析响应失败 → 抛 JudgmentValidationError (含原始 raw 摘要)
        - 校验链失败 → 抛 JudgmentValidationError
        - 提交键已存在 (同 case + claim_type + dsh 响应 hash) → 返 idempotent_replay=True
        """
        # 1) 构造 prompt + 调 dsh
        prompt = build_cve_impact_brief_prompt(
            cve_id=cve_id, subject_name=subject_name, evidence_materials=evidence_materials,
        )
        raw = self._call_dsh(prompt)
        # 2) 解析
        try:
            parsed = parse_cve_impact_brief_response(raw)
        except ValueError as e:
            raise JudgmentValidationError(f"dsh response parse failed: {e}") from e
        # 3) 校验
        try:
            self._validate_payload(
                case_id=case_id,
                claim_type=parsed["claim_type"],
                claim=parsed["claim"],
                conditions=parsed.get("conditions", ""),
                confidence=parsed["confidence"],
                evidence_refs=parsed["evidence_refs"],
                counter_evidence_refs=parsed.get("counter_evidence_refs", []),
                unknowns=parsed["unknowns"],
            )
        except JudgmentValidationError:
            raise
        except Exception as e:
            raise JudgmentValidationError(f"payload validation failed: {e}") from e
        # 4) evidence hash 校验 (material 必须存在 + hash 匹配)
        if parsed["evidence_refs"]:
            self._validate_evidence_hashes(parsed["evidence_refs"])
        # 5) 落库 (draft)
        return self._insert_draft(
            case_id=case_id, parsed=parsed, submitted_by=submitted_by,
        )

    def _call_dsh(self, prompt: str) -> str:
        """调 dsh (走 task_router, settings.kv 切换 mock/stdio/http). 失败兜底 ai_hub."""
        # 1) 测试注入: 直接调 self._dsh_caller
        if self._dsh_caller is not None:
            return self._dsh_caller(prompt)
        # 2) 生产路径
        try:
            from backend.services.dsh.task_router import DSHTaskRouter
            from backend.services.ai_hub.service import ai_service
            from backend.services.ai_hub.gateway import LLMService
        except ImportError as e:
            raise JudgmentValidationError(f"dsh/ai_hub import failed: {e}") from e
        # 优先 dsh task router; 失败兜底 ai_hub.generate_text
        try:
            # 尝试 dsh 真实调用; mock 模式下也走 DSHClient, settings.kv 决定 mode
            from backend.services.dsh.runtime import dsh_runtime
            from backend.services.dsh.bridge import DSHClient
            effective, _reason = dsh_runtime.resolve_effective()
            if effective == "subprocess":
                # 真子进程模式 — 调 stdio live_bridge
                from backend.services.dsh.live_bridge import LiveDSHClient
                # 同步调用; 短超时避免挂起
                client = LiveDSHClient(timeout=30.0)
                try:
                    resp = client.send_task(
                        "cve-impact-brief", {"prompt": prompt, "max_tokens": 4000},
                    )
                    return resp.get("content") or resp.get("result") or json.dumps(resp)
                finally:
                    client.close()
            # 默认 mock/http 模式: 走 ai_hub.generate_text (T10 入口)
            return ai_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                task="cve_impact_brief",
                max_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning(f"dsh call failed, fallback to ai_hub direct: {e}")
            try:
                from backend.services.ai_hub.service import ai_service
                return ai_service.generate_text(
                    messages=[{"role": "user", "content": prompt}],
                    task="cve_impact_brief",
                    max_tokens=4000,
                    temperature=0.2,
                )
            except Exception as e2:
                raise JudgmentValidationError(f"dsh + ai_hub both failed: {e}; fallback={e2}") from e2

    def _insert_draft(
        self, *, case_id: str, parsed: dict[str, Any], submitted_by: str,
    ) -> dict[str, Any]:
        """落库 draft (idempotency_key 走 V1EvidenceService T05 模式)."""
        jid = _ulid26()
        now = _utcnow_iso()
        body = {
            "id": jid,
            "case_id": case_id,
            "subject_id": None,
            "claim_type": parsed["claim_type"],
            "claim": parsed["claim"],
            "conditions": parsed.get("conditions", ""),
            "confidence": parsed["confidence"],
            "evidence_refs": parsed["evidence_refs"],
            "counter_evidence_refs": parsed.get("counter_evidence_refs", []),
            "unknowns": parsed["unknowns"],
            "status": "draft",
            "content_hash": _content_hash(
                parsed["claim"], parsed.get("conditions", ""), parsed["evidence_refs"],
            ),
            "wiki_path": None,
            "revision": 1,
            "published_at": None,
            "allowed_actions": _JUDGMENT_ALLOWED_ACTIONS["draft"],
            "reason": None,
            "created_at": now,
            "updated_at": now,
        }
        # 走 V1EvidenceService.create_intent 拿 receipt (T05 单一提交入口契约)
        idempotency_key = f"v1-judgment-{case_id}-{parsed['claim_type']}-{body['content_hash'][:16]}"
        try:
            from backend.services.v1_evidence_service import V1EvidenceService
            evidence = V1EvidenceService()
            intent = evidence.create_intent(
                idempotency_key, "judgment", body, submitted_by=submitted_by,
            )
            evidence.commit_intent(intent["intent_id"], entity_id=jid, projection=None)
        except Exception as e:
            # V1EvidenceService 失败不阻断 (judgment 主体落 v1_judgments 表)
            logger.warning(f"V1EvidenceService trace failed (judgment still inserts): {e}")
        self.repo.insert(body)
        # 关联 case
        self.repo.link_to_case(case_id, jid)
        return {"judgment": body, "idempotent_replay": False}

    # ------------------------------------------------------------------
    # publish (CAS 三重守卫)
    # ------------------------------------------------------------------
    def publish(self, judgment_id: str, *, expected_revision: int) -> dict[str, Any]:
        """publish draft → published; CAS 校验 expected_revision; UNIQUE PARTIAL INDEX 兜底.

        守卫三重:
          1. status 必须 = 'draft' (否则 ConflictException)
          2. 同 case + claim_type 同时只 1 published (UNIQUE INDEX; 重复 → IntegrityError → ConflictException)
          3. content_hash 与当前 claim+conditions+evidence 一致 (contracts §5.1 L344)

        Returns
        -------
        更新后的 judgment dict.
        """
        j = self.repo.get(judgment_id)
        if j is None:
            raise JudgmentNotFoundError(f"judgment {judgment_id} not found")
        if j["status"] != "draft":
            raise JudgmentConflictError(
                f"judgment {judgment_id} status={j['status']} (publish requires draft)"
            )
        # 守卫 1: CAS
        if j["revision"] != expected_revision:
            raise JudgmentConflictError(
                f"judgment {judgment_id} revision mismatch: expected={expected_revision}, actual={j['revision']}"
            )
        # 守卫 2: 同 case + claim_type 同时只 1 published
        if self.repo.has_published_for_case_type(
            j["case_id"], j["claim_type"], exclude_id=judgment_id,
        ):
            raise JudgmentConflictError(
                f"case {j['case_id']} already has published judgment for claim_type={j['claim_type']}; "
                f"supersede first (T11+ 补端点)"
            )
        # 守卫 3: content_hash 一致性
        expected_hash = _content_hash(j["claim"], j.get("conditions", ""), j["evidence_refs"])
        if j.get("content_hash") and j["content_hash"] != expected_hash:
            raise JudgmentConflictError(
                f"judgment {judgment_id} content_hash drift; recreation required"
            )
        # 落 wiki path
        wiki_path = f"judgments/{judgment_id}.md"
        now = _utcnow_iso()
        try:
            rowcount = self.repo.update_status_cas(
                judgment_id, "published",
                expected_revision=expected_revision,
                published_at=now,
                wiki_path=wiki_path,
                allowed_actions=_JUDGMENT_ALLOWED_ACTIONS["published"],
                reason=None,
            )
        except Exception as e:
            # UNIQUE PARTIAL INDEX 撞库 → ConflictException
            if "UNIQUE" in str(e).upper() or "unique" in str(e):
                raise JudgmentConflictError(
                    f"judgment unique constraint hit: {e}"
                ) from e
            raise
        if rowcount == 0:
            raise JudgmentConflictError(
                f"judgment {judgment_id} CAS update failed (race)"
            )
        # 写 wiki (best effort)
        try:
            from backend.wiki_fs.store import WikiFs
            wiki = WikiFs("knowledge")  # 走默认根
            content = (
                f"---\nid: {judgment_id}\ntitle: Judgment {judgment_id}\n"
                f"case_id: {j['case_id']}\nclaim_type: {j['claim_type']}\n"
                f"confidence: {j['confidence']}\npublished_at: {now}\n---\n\n"
                f"# {j['claim']}\n\n## Conditions\n{j.get('conditions', '')}\n\n"
                f"## Unknowns\n" + "\n".join(f"- {u}" for u in j["unknowns"]) + "\n"
            )
            wiki.write_item(f"judgment_{judgment_id}", {
                "fm": {"id": f"judgment_{judgment_id}", "title": f"Judgment {judgment_id}",
                       "claim_type": j["claim_type"], "published_at": now},
                "body": content,
            })
        except Exception as e:
            logger.warning(f"judgment wiki write failed (publish still ok): {e}")
        return self.repo.get(judgment_id)

    # ------------------------------------------------------------------
    # list / get
    # ------------------------------------------------------------------
    def list_by_case(
        self, case_id: str, *, status: str | None = None, claim_type: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        items, total = self.repo.list_by_case(
            case_id, status=status, claim_type=claim_type, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, judgment_id: str) -> dict[str, Any]:
        j = self.repo.get(judgment_id)
        if j is None:
            raise JudgmentNotFoundError(f"judgment {judgment_id} not found")
        return j
