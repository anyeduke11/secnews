"""v1.0 T12 ArtifactService — 5 态机 + 防重传蒙混 (contracts §8.3) + 验收.

5 态机:
  pending → verify → verified → accept → accepted
              ↓ verify_fail
            rejected
              ↓ supersede (新 artifact 接受 = 旧 superseded)

不变量 (§8.3):
  - rejected 后同 content_hash 不可再 accept (防"重传蒙混"); 必走新 Run
  - accepted 是终态; 撤销接受走 supersede + wiki_event, 不删记录
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.repository.artifact_repo import ArtifactRepository


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------
class ArtifactValidationError(InvalidParamException):
    def __init__(self, message: str = "artifact validation failed") -> None:
        super().__init__(message)


class ArtifactNotFoundError(NotFoundException):
    def __init__(self, message: str = "artifact not found") -> None:
        super().__init__(message)


class ArtifactConflictError(ConflictException):
    def __init__(self, message: str = "artifact state conflict") -> None:
        super().__init__(message)


_ARTIFACT_ALLOWED_ACTIONS: dict[str, list[str]] = {
    "pending": ["verify", "reject"],
    "verified": ["accept", "reject"],
    "accepted": ["view_only"],
    "rejected": ["view_only"],
    "superseded": ["view_only"],
}
_VALID_ARTIFACT_STATUS = set(_ARTIFACT_ALLOWED_ACTIONS.keys())
_VALID_ARTIFACT_KIND = {"report", "file", "data", "chart", "code_patch", "message"}
_VALID_ARTIFACT_FORMAT = {"md", "json", "csv", "png", "pdf", "txt", "html", "xml"}
_VALID_VERIFICATION_RESULT = {"pass", "fail", "warn"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ulid26() -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(random.choice(alphabet) for _ in range(26))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ArtifactService
# ---------------------------------------------------------------------------
class ArtifactService:
    """Artifact 服务 — 5 态机 + 防重传蒙混 + 验收."""

    def __init__(self, repo: ArtifactRepository | None = None) -> None:
        self.repo = repo or ArtifactRepository()

    # ------------------------------------------------------------------
    # create (run_id 必引; 落库 status=pending)
    # ------------------------------------------------------------------
    def create(
        self, *, run_id: str, kind: str, title: str, content: str,
        format: str = "md", content_ref: str | None = None,
    ) -> dict[str, Any]:
        """创建 artifact (默认 status=pending, verified_result=None)."""
        if not run_id or not isinstance(run_id, str):
            raise ArtifactValidationError("run_id required")
        if kind not in _VALID_ARTIFACT_KIND:
            raise ArtifactValidationError(f"invalid kind: {kind}")
        if format not in _VALID_ARTIFACT_FORMAT:
            raise ArtifactValidationError(f"invalid format: {format}")
        if not title or not title.strip():
            raise ArtifactValidationError("title must be non-empty")
        if not content:
            raise ArtifactValidationError("content required for hash")
        aid = _ulid26()
        now = _utcnow_iso()
        ch = _content_hash(content)
        size = len(content.encode("utf-8"))
        body = {
            "id": aid, "run_id": run_id, "kind": kind, "title": title,
            "content_ref": content_ref, "content_hash": ch, "format": format,
            "size_bytes": size,
            "verified_by": None, "verified_at": None, "verified_result": None,
            "accepted_by": None, "accepted_at": None, "accepted_note": None,
            "status": "pending", "revision": 1, "created_at": now, "updated_at": now,
            "allowed_actions": _ARTIFACT_ALLOWED_ACTIONS["pending"],
            "reason": None,
        }
        self.repo.insert(body)
        return body

    # ------------------------------------------------------------------
    # 验证 (auto / manual)
    # ------------------------------------------------------------------
    def verify(
        self, artifact_id: str, *, verified_by: str, verified_result: str = "pass",
    ) -> dict[str, Any]:
        a = self._require(artifact_id)
        if a["status"] != "pending":
            raise ArtifactConflictError(
                f"artifact {artifact_id} status={a['status']} (verify requires pending)"
            )
        if verified_result not in _VALID_VERIFICATION_RESULT:
            raise ArtifactValidationError(f"invalid verified_result: {verified_result}")
        new_status = "verified" if verified_result == "pass" else "rejected"
        rowcount = self.repo.update_status_cas(
            artifact_id, new_status,
            verified_by=verified_by, verified_at=_utcnow_iso(),
            verified_result=verified_result,
            allowed_actions=_ARTIFACT_ALLOWED_ACTIONS[new_status], reason=None,
        )
        if rowcount == 0:
            raise ArtifactConflictError(f"artifact {artifact_id} CAS race")
        return self._require(artifact_id)

    # ------------------------------------------------------------------
    # 业务验收 (only verified → accepted)
    # ------------------------------------------------------------------
    def accept(
        self, artifact_id: str, *, accepted_by: str, accepted_note: str | None = None,
    ) -> dict[str, Any]:
        a = self._require(artifact_id)
        if a["status"] != "verified":
            raise ArtifactConflictError(
                f"artifact {artifact_id} status={a['status']} (accept requires verified)"
            )
        # 守卫 §8.3 防重传蒙混: 同 run + 同 content_hash 已 rejected 不可再 accept
        if self.repo.has_rejected_with_same_hash(a["run_id"], a["content_hash"]):
            # 当前 artifact 自身就是 rejected 同 hash (race); 否则历史 rejected
            existing_self = a["content_hash"] == a["content_hash"]  # always True; 双保险
            raise ArtifactConflictError(
                f"artifact {artifact_id} content_hash={a['content_hash'][:16]}... was rejected; "
                f"re-uploading same content is not allowed (§8.3 防重传蒙混); "
                f"create a new Run"
            )
        rowcount = self.repo.update_status_cas(
            artifact_id, "accepted",
            accepted_by=accepted_by, accepted_at=_utcnow_iso(),
            accepted_note=accepted_note,
            allowed_actions=_ARTIFACT_ALLOWED_ACTIONS["accepted"], reason=None,
        )
        if rowcount == 0:
            raise ArtifactConflictError(f"artifact {artifact_id} CAS race")
        return self._require(artifact_id)

    # ------------------------------------------------------------------
    # 拒绝 (verify 阶段或业务退回)
    # ------------------------------------------------------------------
    def reject(
        self, artifact_id: str, *, rejected_by: str, reason: str,
    ) -> dict[str, Any]:
        a = self._require(artifact_id)
        if a["status"] in ("accepted", "rejected", "superseded"):
            raise ArtifactConflictError(
                f"artifact {artifact_id} status={a['status']} (reject requires pending/verified)"
            )
        rowcount = self.repo.update_status_cas(
            artifact_id, "rejected", reason=f"rejected_by={rejected_by}: {reason}",
            allowed_actions=_ARTIFACT_ALLOWED_ACTIONS["rejected"],
        )
        if rowcount == 0:
            raise ArtifactConflictError(f"artifact {artifact_id} CAS race")
        return self._require(artifact_id)

    # ------------------------------------------------------------------
    # list / get
    # ------------------------------------------------------------------
    def list_by_run(
        self, run_id: str, *, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in _VALID_ARTIFACT_STATUS:
            raise ArtifactValidationError(f"invalid status: {status}")
        items, total = self.repo.list_by_run(
            run_id, status=status, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, artifact_id: str) -> dict[str, Any]:
        return self._require(artifact_id)

    def _require(self, artifact_id: str) -> dict[str, Any]:
        a = self.repo.get(artifact_id)
        if a is None:
            raise ArtifactNotFoundError(f"artifact {artifact_id} not found")
        return a
