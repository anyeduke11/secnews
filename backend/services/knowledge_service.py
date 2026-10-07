"""v1.0 T13 KnowledgeService — 编排 facade (Batch 4 B 拆分自 902 行上帝服务).

对应 contracts.md §9 (Knowledge) + §9.4 (ReuseReceipt 派生) + EXECUTION_GUIDE §T13。

本文件是 knowledge 域的编排 facade: 公开 API (类 / 错误 / 模块函数) 逐字不变,
实现按 import 边界拆到 5 个 mixin 模块 + 1 个共享底座:

  knowledge_common.py           — 错误类型 + 状态机常量 + 纯函数 helpers
  knowledge_ai.py               — create 校验 + dsh 适配 + ai 深读/改写 (ai_hub)
  knowledge_evidence_bridge.py  — draft 落库 + V1EvidenceService 追踪 + v1_outbox 事件
  knowledge_legacy_bridge.py    — C13 legacy promote (legacy_migrate_v1 桥)
  knowledge_lifecycle.py        — publish / deprecate / retract / revive 状态机
  knowledge_reuse.py            — adoption / recall / review-due + auto_recall/add_agent_link

wiki 不可变写 (_write_wiki) 保留在本模块 — R10 守卫 (test_c01) 对本模块源码
静态断言 resolve_wiki_root / HOTSPOT_WIKI_ROOT 引用。

状态机 (4 态, §9.2):
  draft → publish → published → deprecate → deprecated
                     │  ↑                │
                     │  retract           ▼
                     ▼                (review_at 触发复审, 不改 status)
                  retracted (终态, allowed_actions=[])

SK-05 复用记录 (ReuseReceipt, §9.4): 派生自 v1_knowledge_refs 关联表; 不存新表.
SK-06 复查: 每日 review_due job 扫 review_at ≤ now + published → 挂 case blocker.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.repository.knowledge_revision_repo import (
    KnowledgeRefRepository,
    KnowledgeRevisionRepository,
)
from backend.repository.v1_knowledge_repo import V1KnowledgeRepository as KnowledgeRepository
from backend.services.knowledge_ai import KnowledgeAiMixin
from backend.services.knowledge_common import (  # noqa: F401 — 公开 re-export
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeValidationError,
)
from backend.services.knowledge_evidence_bridge import KnowledgeEvidenceBridgeMixin
from backend.services.knowledge_legacy_bridge import KnowledgeLegacyBridgeMixin
from backend.services.knowledge_lifecycle import KnowledgeLifecycleMixin
from backend.services.knowledge_reuse import (  # noqa: F401 — 公开 re-export
    KnowledgeReuseMixin,
    add_agent_link,
    auto_recall_for_case,
)


# ---------------------------------------------------------------------------
# KnowledgeService (facade — 编排 + 跨模块共享的 wiki 写 / require)
# ---------------------------------------------------------------------------
class KnowledgeService(
    KnowledgeAiMixin,
    KnowledgeEvidenceBridgeMixin,
    KnowledgeLegacyBridgeMixin,
    KnowledgeLifecycleMixin,
    KnowledgeReuseMixin,
):
    """Knowledge 服务 — 4 态机 + 复用派生 + 复查 (实现见 knowledge_*.py mixin 模块)."""

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
    # create_with_dsh (T13 SK-04 主路径) — 编排: AI 生成 → 校验 → 提案
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
        """通过 dsh (或 mock) 生成 knowledge 经验, **落 copilot 提案** (P2-4 收编).

        v0.8.6 P2-4: SK-04 触发路径不再直写 knowledge draft — dsh 生成 +
        校验链保留, 产物经 ``RunLedgerService.copilot_draft(kind='report')``
        落 STANDARD 提案 (人审后生效, 判定 generate 同模式);
        直写通道 :meth:`_insert_draft` 仅供状态机测试/内部使用。

        Returns
        -------
        {"proposal": <dict>, "idempotent_replay": False}
        """
        parsed = self._generate_parsed_draft(
            case_id=case_id, judgment_id=judgment_id, action_id=action_id,
            subject_name=subject_name, cve_id=cve_id, kind=kind,
            evidence_materials=evidence_materials,
        )
        # 校验
        self._validate_create_payload(
            kind=kind, title=parsed["title"], body=parsed["body"],
            prerequisites=parsed["prerequisites"], counter_examples=parsed["counter_examples"],
            evidence_refs=parsed["evidence_refs"], review_at=parsed["review_at"],
            expiry_at=parsed.get("expiry_at"),
        )
        # evidence hash 校验
        self._validate_evidence_hashes(parsed["evidence_refs"])
        # P2-4: 提案化 (人审后生效) — 提案 approval 走 P1-3 四 kind 产物化
        from backend.services.run_ledger_service import RunLedgerService

        payload: dict[str, Any] = {
            "title": parsed["title"],
            "body": parsed["body"],
            "knowledge_kind": kind,
            "prerequisites": parsed["prerequisites"],
            "counter_examples": parsed["counter_examples"],
            "evidence_refs": parsed["evidence_refs"],
            "review_at": parsed["review_at"],
            "source": {"case_id": case_id, "judgment_id": judgment_id,
                       "action_id": action_id, "subject_name": subject_name,
                       "cve_id": cve_id},
        }
        proposal = RunLedgerService().copilot_draft(
            "report", case_id=case_id, drafter=lambda _ctx: payload,
        )
        return {"proposal": proposal, "idempotent_replay": False}

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
