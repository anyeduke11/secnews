"""Knowledge legacy migrate 桥块 — C13 第 5 态 'legacy' 专用 promote 守卫.

knowledge_service 拆分 (Batch 4 B) 的实现模块之一: import legacy_migrate_v1
的部分归属此处。以 mixin 形式并入 KnowledgeService (knowledge_service.py
facade), 公开 API 逐字不变。
"""
from __future__ import annotations

from typing import Any

from backend.services.knowledge_common import _utcnow_iso


class KnowledgeLegacyBridgeMixin:
    """legacy → published 后台通道 (业务 publish/deprecate 不允许)."""

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
