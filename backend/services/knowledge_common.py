"""Knowledge 域共享基础 — 错误类型 + 状态机常量 + 纯函数 helpers.

knowledge_service 拆分 (Batch 4 B) 的公共底座: facade (knowledge_service.py)
与各实现 mixin (knowledge_ai / knowledge_evidence_bridge / knowledge_legacy_bridge /
knowledge_lifecycle / knowledge_reuse) 共同 import, 避免互相循环。

对应 contracts.md §9 (Knowledge) + §9.4 (ReuseReceipt 派生) + EXECUTION_GUIDE §T13。

状态机 (4+1 态, §9.2 + C13 第 5 态):
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
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.repository.db import get_connection


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
