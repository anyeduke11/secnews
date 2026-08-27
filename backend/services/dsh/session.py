"""DSHSessionManager — 会话生命周期管理 (内存 MVP).

不落库; 超时自动清理 (默认 30min)。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger("hotspot.dsh.session")

_TIMEOUT = 30 * 60  # 30min


class DSHSessionManager:
    """内存会话管理."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_session(self, task_type: str, payload: dict[str, Any]) -> str:
        """创建会话, 返回 session_id."""
        session_id = f"sess_{int(time.time() * 1000)}"
        with self._lock:
            self._sessions[session_id] = {
                "id": session_id,
                "task_type": task_type,
                "payload": payload,
                "status": "created",
                "created_at": time.time(),
            }
        self._cleanup()
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """查询会话."""
        with self._lock:
            return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """关闭会话."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess:
                sess["status"] = "closed"
                sess["closed_at"] = time.time()

    def _cleanup(self) -> None:
        """清理超时会话."""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s["created_at"] > _TIMEOUT
        ]
        for sid in expired:
            del self._sessions[sid]
