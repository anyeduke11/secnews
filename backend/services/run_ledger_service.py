"""RunLedgerService — M1 提案审批循环 + Run 账本终判 (v0.8.6 P1-1)。

PRD §5.1 主干: AI 建议 → proposal 待审 → 人批准 → Run (双签) → outcome。
人主律: 未经审批的提案不得成为事实; LLM 超时/拒绝落显式失败, 不回落默认值
(用例 A②)。

切片 2 范围 (AI 起草 + 产物登记):
- draft_judgment: Case 证据 → ai_hub HEAVY 草案 → proposal(draft);
  LLM 超时/拒绝/不可解析 → proposal(failed) 显式可重试 (用例 A②);
- approve judgment_draft: 双签 Run 先 running → md 产物落盘 + sha256 登记
  (ArtifactService R08 读盘比对) → succeeded/done; 落盘或哈希失败 →
  status=failed + outcome=failed (禁止成功但无产物, PRD §5.1)。
不在切片 2: 审批收件箱前端 (切片 3)、failed Run 重试端点、command_log (P1-4)。
"""
from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.proposal_repo import ProposalRepository
from backend.repository.run_repo import RunRepository
from backend.repository.v1_evidence_repo import V1EvidenceRepository
from backend.services.copilot_drafter import (
    COPILOT_DRAFT_KINDS,
    COPILOT_DRAFT_PROMPT_VERSION,
    ai_copilot_draft,
    render_copilot_markdown,
)
from backend.services.judgment_drafter import (
    JUDGMENT_DRAFT_PROMPT_VERSION,
    ai_draft_judgment,
    render_judgment_markdown,
)
from backend.version import APP_VERSION

PROPOSAL_SOURCES = {"agent", "command", "copilot"}
PROPOSAL_KINDS = {"judgment_draft", "case_suggestion", "knowledge_draft", "report"}
# §8.1 四态 + failed (用例 A②: LLM 超时/拒绝必须在收件箱显式失败可重试)。
PROPOSAL_STATUSES = {"draft", "approved", "rejected", "expired", "failed"}
LEDGER_OUTCOMES = {"done", "failed", "cancelled", "timeout", "needs_human"}
MAX_PAYLOAD_CHARS = 65536  # §8.1 CHECK(length(payload_json) <= 65536)
MAX_REJECT_REASON_CHARS = 200  # §6: 驳回原因必填 ≤200
# P1-3: 非研判 kind 的产物标题前缀 (artifact kind 恒 report/md, title 区分)
_ARTIFACT_TITLES = {
    "case_suggestion": "建案建议产物",
    "knowledge_draft": "知识摘要产物",
    "report": "复盘草案产物",
}

_ULID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


class ProposalValidationError(InvalidParamException):
    def __init__(self, message: str = "proposal validation failed") -> None:
        super().__init__(message)


class ProposalNotFoundError(NotFoundException):
    def __init__(self, message: str = "proposal not found") -> None:
        super().__init__(message)


class ProposalConflictError(ConflictException):
    def __init__(self, message: str = "proposal state conflict") -> None:
        super().__init__(message)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ulid(prefix: str) -> str:
    return prefix + "".join(random.choice(_ULID_ALPHABET) for _ in range(26))


def _serialize_payload(payload: dict[str, Any]) -> str:
    """序列化 + 64KB 上限校验 (与 DDL CHECK 同源口径: 字符数)。"""
    text = json.dumps(payload or {}, ensure_ascii=False)
    if len(text) > MAX_PAYLOAD_CHARS:
        raise ProposalValidationError(
            f"payload_json too large: {len(text)} > {MAX_PAYLOAD_CHARS} chars"
        )
    return text


class RunLedgerService:
    def __init__(
        self,
        proposal_repo: ProposalRepository | None = None,
        run_repo: RunRepository | None = None,
        evidence_repo: V1EvidenceRepository | None = None,
        artifact_service: Any | None = None,
    ) -> None:
        self.proposals = proposal_repo or ProposalRepository()
        self.runs = run_repo or RunRepository()
        self.evidence = evidence_repo or V1EvidenceRepository()
        # ArtifactService 只在 judgment_draft 批准时消费; 惰性导入避免循环边。
        self._artifact_service = artifact_service

    # ── 创建 ─────────────────────────────────────────────────────────
    def create_proposal(
        self, *, source: str, kind: str, payload: dict[str, Any],
        evidence_ids: list[str] | None = None,
        prompt_version: str | None = None, case_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_enum("source", source, PROPOSAL_SOURCES)
        self._validate_enum("kind", kind, PROPOSAL_KINDS)
        _serialize_payload(payload)  # 过大直接拒绝, 不触库 (CHECK 是第二道)
        pid = _ulid("prop_")
        self.proposals.insert({
            "id": pid, "case_id": case_id, "source": source, "kind": kind,
            "payload": payload, "evidence_ids": evidence_ids or [],
            "prompt_version": prompt_version, "status": "draft",
        })
        return self._get_or_raise(pid)

    def record_failed_proposal(
        self, *, source: str, kind: str, error: str,
        case_id: str | None = None, prompt_version: str | None = None,
    ) -> dict[str, Any]:
        """用例 A②: LLM 超时/拒绝 → 显式失败提案, 收件箱可重试。

        刻意只存错误元信息 + 空 payload — **不回落默认值、不缓存伪内容**。
        """
        self._validate_enum("source", source, PROPOSAL_SOURCES)
        self._validate_enum("kind", kind, PROPOSAL_KINDS)
        if not error or not str(error).strip():
            raise ProposalValidationError("error is required for failed proposal")
        pid = _ulid("prop_")
        self.proposals.insert({
            "id": pid, "case_id": case_id, "source": source, "kind": kind,
            "payload": {}, "evidence_ids": [], "prompt_version": prompt_version,
            "status": "failed", "error_msg": str(error)[:500],
        })
        return self._get_or_raise(pid)

    def draft_judgment(
        self, case_id: str, *,
        source: str = "agent",
        drafter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """用例 A①: Case 页"AI 起草研判"。证据 → HEAVY 草案 → proposal(draft)。

        drafter 可注入 (测试桩); 默认 ai_draft_judgment (ai_hub task=report,
        HEAVY 档)。无绑定证据直接 400 — 研判必须带证据引用, 不允许凭空起草。
        drafter 抛错/返回空壳 → record_failed_proposal (用例 A②),
        返回的提案 status=failed, 供收件箱展示原因与重试。
        source: agent (Case 页入口) | copilot (M3A 副驾研判建议卡, P1-3)。
        """
        if not case_id or not str(case_id).strip():
            raise ProposalValidationError("case_id is required")
        evidence = self.evidence.case_evidence_materials(case_id)
        if not evidence:
            raise ProposalValidationError(
                f"case {case_id} has no bound evidence materials; "
                "judgment draft requires evidence references"
            )
        evidence_ids = [str(m["id"]) for m in evidence]
        drafter = drafter or ai_draft_judgment
        try:
            payload = drafter({"case_id": case_id, "evidence": evidence})
        except Exception as e:
            logger.warning(
                "judgment draft failed for case=%s: %s: %s",
                case_id, type(e).__name__, e,
            )
            return self.record_failed_proposal(
                source=source, kind="judgment_draft",
                error=f"{type(e).__name__}: {e}",
                case_id=case_id, prompt_version=JUDGMENT_DRAFT_PROMPT_VERSION,
            )
        return self.create_proposal(
            source=source, kind="judgment_draft", payload=payload,
            evidence_ids=evidence_ids, case_id=case_id,
            prompt_version=JUDGMENT_DRAFT_PROMPT_VERSION,
        )

    def copilot_draft(
        self, kind: str, *,
        case_id: str | None = None, knowledge_id: str | None = None,
        drafter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """P1-3 M3 副驾三卡起草: 上下文 → STANDARD 草案 → proposal(draft, copilot)。

        - case_suggestion (证据召回卡) / report (SK-04 复盘草案卡): 锚 case,
          必须有绑定证据 (与 judgment 同纪律: 不允许凭空起草);
        - knowledge_draft (知识摘要卡): 锚 knowledge item (kl-* stub)。
        模型失败 → failed 提案 (case 锚定时 case_id 留痕供收件箱重试,
        knowledge 锚暂无重试锚点 — error_msg 内含条目标识)。
        """
        if kind not in COPILOT_DRAFT_KINDS:
            raise ProposalValidationError(
                f"invalid copilot kind: {kind!r}; allowed={sorted(COPILOT_DRAFT_KINDS)}"
            )
        drafter = drafter or ai_copilot_draft
        if kind == "knowledge_draft":
            if not knowledge_id or not str(knowledge_id).strip():
                raise ProposalValidationError("knowledge_id is required")
            from backend.repository.knowledge_repo import knowledge_repo
            item = knowledge_repo.get_item(knowledge_id)
            if item is None:
                raise ProposalValidationError(
                    f"knowledge item {knowledge_id} not found"
                )
            context: dict[str, Any] = {
                "kind": kind, "knowledge_id": knowledge_id,
                "item": {"id": knowledge_id,
                         "title": getattr(item, "title", "") or "",
                         "topic": getattr(item, "topic", "") or ""},
            }
            anchor_case = None
            evidence_ids: list[str] = []
        else:
            if not case_id or not str(case_id).strip():
                raise ProposalValidationError("case_id is required")
            evidence = self.evidence.case_evidence_materials(case_id)
            if not evidence:
                raise ProposalValidationError(
                    f"case {case_id} has no bound evidence materials; "
                    "copilot draft requires evidence references"
                )
            context = {"kind": kind, "case_id": case_id, "evidence": evidence}
            anchor_case = case_id
            evidence_ids = [str(m["id"]) for m in evidence]
        try:
            payload = drafter(context)
        except Exception as e:
            logger.warning(
                "copilot draft failed kind=%s case=%s: %s: %s",
                kind, anchor_case, type(e).__name__, e,
            )
            return self.record_failed_proposal(
                source="copilot", kind=kind,
                error=f"{type(e).__name__}: {e}",
                case_id=anchor_case, prompt_version=COPILOT_DRAFT_PROMPT_VERSION,
            )
        return self.create_proposal(
            source="copilot", kind=kind, payload=payload,
            evidence_ids=evidence_ids, case_id=anchor_case,
            prompt_version=COPILOT_DRAFT_PROMPT_VERSION,
        )

    # ── 查询 ─────────────────────────────────────────────────────────
    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        return self._get_or_raise(proposal_id)

    def list_proposals(
        self, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if status:
            self._validate_enum("status", status, PROPOSAL_STATUSES)
        if kind:
            self._validate_enum("kind", kind, PROPOSAL_KINDS)
        return self.proposals.list_proposals(
            status=status, kind=kind, limit=limit, offset=offset,
        )

    # ── 人审 ─────────────────────────────────────────────────────────
    def approve_proposal(
        self, proposal_id: str, *, reviewed_by: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """批准提案 → 双签 Run。内容类提案的"执行"即人采纳, outcome=done。

        payload 非空 = 人修订后批准 (§6: 修订=展开原文编辑后批准)。
        policy_version 在此刻冻结为应用版本。
        """
        proposal = self._get_or_raise(proposal_id)
        if proposal["status"] != "draft":
            raise ProposalConflictError(
                f"only draft proposal can be approved (current={proposal['status']})"
            )
        if not reviewed_by or not reviewed_by.strip():
            raise ProposalValidationError("reviewed_by is required")

        final_payload = payload if payload is not None else proposal["payload"]
        _serialize_payload(final_payload)
        now = _utcnow_iso()
        run_id = _ulid("run_")
        # P1-3 (DEV-0271): 四 kind 全产物化 — 批准的"执行"= md 产物落盘 +
        # sha256 登记: 先 running, 产物登记成功才 succeeded/done; 落盘或哈希
        # 失败 → failed/failed (用例 A 异常流; 禁止成功但无产物)。
        # 验收 "副驾四卡各产出 ≥1 artifact" 依赖全 kind 走此路径 (切片1 的
        # "其余 kind 采纳即 done" 占位语义由此退役)。
        materialize = True
        initial_status = "running" if materialize else "succeeded"
        initial_outcome = None if materialize else "done"
        # v1_runs.action_id NOT NULL: 账本 Run 无 v1_actions 归属, 用
        # proposal:<id> 作确定性锚点 (SQLite FK 全局 off, 见迁移 126)。
        self.runs.insert({
            "id": run_id,
            "action_id": f"proposal:{proposal_id}",
            "protocol": "direct",
            "trigger_source": "user",
            "idempotency_key": f"proposal:{proposal_id}",
            "status": initial_status,
            "inputs": final_payload,
            "plan": {"proposal_id": proposal_id, "kind": proposal["kind"],
                     "dual_sign": ["human", proposal["source"]]},
            "policy_version": APP_VERSION,
            "outcome": initial_outcome,
            "started_at": now,
            "finished_at": None if materialize else now,
            "duration_ms": None if materialize else 0,
            "created_at": now, "updated_at": now,
        })
        self.proposals.update_decision(
            proposal_id, "approved",
            reviewed_by=reviewed_by, reviewed_at=now, run_id=run_id,
        )
        if materialize:
            self._materialize_artifact(
                run_id=run_id, proposal=proposal, payload=final_payload,
            )
        return self._get_or_raise(proposal_id)

    def reject_proposal(
        self, proposal_id: str, *, reviewed_by: str, reason: str,
    ) -> dict[str, Any]:
        proposal = self._get_or_raise(proposal_id)
        if proposal["status"] != "draft":
            raise ProposalConflictError(
                f"only draft proposal can be rejected (current={proposal['status']})"
            )
        if not reason or not reason.strip():
            raise ProposalValidationError("reject reason is required")
        if len(reason) > MAX_REJECT_REASON_CHARS:
            raise ProposalValidationError(
                f"reject reason too long: {len(reason)} > {MAX_REJECT_REASON_CHARS}"
            )
        if not reviewed_by or not reviewed_by.strip():
            raise ProposalValidationError("reviewed_by is required")
        self.proposals.update_decision(
            proposal_id, "rejected",
            reviewed_by=reviewed_by, reviewed_at=_utcnow_iso(),
            reject_reason=reason,
        )
        return self._get_or_raise(proposal_id)

    # ── Run 终判 (后续 pi 执行体 / 哈希校验消费) ─────────────────────
    def finish_run(
        self, run_id: str, outcome: str, *, reason: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        self._validate_enum("outcome", outcome, LEDGER_OUTCOMES)
        run = self.runs.get(run_id)
        if run is None:
            raise NotFoundException("run not found")
        self.runs.update_outcome(
            run_id, outcome, reason=reason, duration_ms=duration_ms,
        )
        result = self.runs.get(run_id)
        assert result is not None
        return result

    def retry_run(self, run_id: str) -> dict[str, Any]:
        """P1-1 收尾: failed Run 原地重试 (产物化失败场景, 凭 run_id 定位)。

        仅账本域 Run (action_id=proposal:<id>) 且 status=failed 且底层提案
        approved 可重试 — 人的双签已成立, 重试只重走 md 产物化 + sha256 登记。
        同一 Run 行复位 (outcome/error 清空) 后重跑: 保持"一提案一 Run"不变量、
        proposal.run_id 回指与 artifact 文件名稳定; 失败史留应用日志 (G1 失败
        面板批次再接 outbox 告警)。重试再失败 → failed/failed + 原异常上抛。
        """
        run = self.runs.get(run_id)
        if run is None:
            raise NotFoundException("run not found")
        if run["status"] != "failed":
            raise ProposalConflictError(
                f"only failed run can be retried (current={run['status']})"
            )
        anchor = run.get("action_id") or ""
        if not anchor.startswith("proposal:"):
            raise ProposalValidationError("run is not a ledger proposal run")
        proposal = self._get_or_raise(anchor.split(":", 1)[1])
        if proposal["status"] != "approved":
            raise ProposalConflictError(
                f"underlying proposal not approved (current={proposal['status']})"
            )
        self.runs.reset_for_retry(run_id, started_at=_utcnow_iso())
        self._materialize_artifact(
            run_id=run_id, proposal=proposal, payload=proposal["payload"],
        )
        result = self.runs.get(run_id)
        assert result is not None
        return result

    # ── 提案产物物化 (切片 2 judgment / P1-3 全 kind) ────────────────
    def _artifact_svc(self) -> Any:
        if self._artifact_service is None:
            from backend.services.artifact_service import ArtifactService
            self._artifact_service = ArtifactService()
        return self._artifact_service

    def _materialize_artifact(
        self, *, run_id: str, proposal: dict[str, Any], payload: dict[str, Any],
    ) -> None:
        """批准 → md 落盘 + Artifact(sha256 R08 读盘比对) → Run succeeded/done。

        judgment_draft 走研判渲染 (证据 Source url 内嵌); 其余三 kind 走
        copilot 通用渲染。任何失败 (渲染/落盘/哈希不一致): Run status=failed +
        outcome=failed, proposal 保持 approved (人的采纳决定成立, 执行失败可凭
        run_id 重试), 错误 logger.error 留痕 (G1 告警面板批次再接 outbox)。
        原异常上抛 API。
        """
        from backend.config import config

        kind = proposal["kind"]
        case_id = proposal.get("case_id") or ""
        now = _utcnow_iso()
        # case 锚定提案带证据 (回溯链); knowledge 锚定提案无 case 证据
        evidence = (
            self.evidence.case_evidence_materials(case_id) if case_id else []
        )
        try:
            if kind == "judgment_draft":
                markdown = render_judgment_markdown(
                    case_id=case_id, payload=payload,
                    evidence=evidence, proposal_id=proposal["id"],
                )
                title = f"研判产物 {case_id}".strip()
            else:
                markdown = render_copilot_markdown(
                    kind=kind, anchor_id=case_id or None, payload=payload,
                    evidence=evidence, proposal_id=proposal["id"],
                )
                title = (
                    f"{_ARTIFACT_TITLES[kind]} "
                    f"{case_id or payload.get('title', '')}"
                ).strip()[:200]
            out_dir = Path(config.data_dir) / "run_artifacts"
            out_dir.mkdir(parents=True, exist_ok=True)
            content_ref = out_dir / f"{run_id}.md"
            content_ref.write_text(markdown, encoding="utf-8")
            artifact = self._artifact_svc().create(
                run_id=run_id, kind="report", format="md",
                title=title,
                content=markdown, content_ref=str(content_ref),
            )
        except Exception as e:
            reason = f"proposal artifact materialization failed: {type(e).__name__}: {e}"
            logger.error("run %s → failed: %s", run_id, reason)
            self.runs.update_status(
                run_id, "failed", finished_at=_utcnow_iso(), error=str(e)[:500],
            )
            self.runs.update_outcome(run_id, "failed", reason=reason[:500])
            raise
        self.runs.update_status(
            run_id, "succeeded", finished_at=now,
            result_excerpt=str(payload.get("claim") or payload.get("summary") or payload.get("title") or "")[:500],
            artifact_ids=[artifact["id"]],
        )
        self.runs.update_outcome(run_id, "done")

    # ── 内部 ─────────────────────────────────────────────────────────
    def _get_or_raise(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"proposal {proposal_id} not found")
        return proposal

    @staticmethod
    def _validate_enum(field: str, value: str, allowed: set[str]) -> None:
        if value not in allowed:
            raise ProposalValidationError(
                f"invalid {field}: {value!r}; allowed={sorted(allowed)}"
            )
