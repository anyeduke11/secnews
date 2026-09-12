"""Knowledge AI 块 — create 校验 + dsh 适配 + ai 深读/改写 (T13 SK-04 主路径).

knowledge_service 拆分 (Batch 4 B) 的实现模块之一: import dsh_adapter 与
ai_hub.prompts / ai_hub.service 的部分归属此处。以 mixin 形式并入
KnowledgeService (knowledge_service.py facade), 公开 API 逐字不变。
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.services.dsh_adapter import run_dsh_sync
from backend.services.knowledge_common import (
    _BODY_MAX_BYTES,
    _TITLE_MAX_BYTES,
    _VALID_KIND,
    KnowledgeValidationError,
    _material_hash_lookup,
)


class KnowledgeAiMixin:
    """create 校验 + dsh 调用 (mock/stdio/http 切换) + ai_hub 显式降级."""

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
    # AI 生成 + 解析 (create_with_dsh 的 ai 深读/改写段)
    # ------------------------------------------------------------------
    def _generate_parsed_draft(
        self,
        *,
        case_id: str,
        judgment_id: str,
        action_id: str,
        subject_name: str,
        cve_id: str,
        kind: str,
        evidence_materials: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """build_knowledge_prompt → _call_dsh → parse_knowledge_publish_response."""
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
        return parsed

    # ------------------------------------------------------------------
    # dsh 适配
    # ------------------------------------------------------------------
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
