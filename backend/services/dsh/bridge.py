"""DSHClient — HTTP 客户端连接 deepseek-harness 运行时.

配置:
- DSH_ENDPOINT env (默认 http://localhost:3210)
- timeout=30s, 失败抛 ConnectionError (上层降级用)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger("hotspot.dsh.bridge")

DSH_ENDPOINT = os.getenv("DSH_ENDPOINT", "http://localhost:3210")
TIMEOUT = 30.0


class DSHClient:
    """DSH HTTP 客户端."""

    def __init__(self, endpoint: str | None = None) -> None:
        self._endpoint = endpoint or DSH_ENDPOINT
        self._client = httpx.Client(timeout=TIMEOUT)

    def health_check(self) -> bool:
        """GET /health → True/False."""
        try:
            r = self._client.get(f"{self._endpoint}/health")
            return r.status_code == 200
        except Exception as e:
            log.warning("DSH health_check failed: %s", e)
            return False

    def send_task(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/task."""
        r = self._client.post(
            f"{self._endpoint}/api/task",
            json={"task_type": task_type, "payload": payload},
        )
        r.raise_for_status()
        return r.json()

    def get_session(self, session_id: str) -> dict[str, Any]:
        """GET /api/session/{session_id}."""
        r = self._client.get(f"{self._endpoint}/api/session/{session_id}")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        """关闭底层 httpx client."""
        self._client.close()
