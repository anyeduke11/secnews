"""Knowledge 状态机块 — publish / deprecate / retract / revive (CAS 守卫, contracts §9.2).

knowledge_service 拆分 (Batch 4 B) 的实现模块之一: 4 态机转移 + revision 追加
+ 弃用/撤回 blocker 联动归属此处。以 mixin 形式并入 KnowledgeService
(knowledge_service.py facade), 公开 API 逐字不变。

wiki 不可变写 (_write_wiki) 留在 facade — R10 守卫 (test_c01) 对
knowledge_service 模块源码做静态断言 (resolve_wiki_root / HOTSPOT_WIKI_ROOT)。
"""
from __future__ import annotations

from typing import Any

from backend.services.knowledge_common import (
    _KNOWLEDGE_ALLOWED_ACTIONS,
    KnowledgeConflictError,
    _utcnow_iso,
)


class KnowledgeLifecycleMixin:
    """draft/published/deprecated/retracted 间的业务态转移 (CAS + revision append)."""

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
