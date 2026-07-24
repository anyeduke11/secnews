"""v1.7 Phase 5 — Agent HTTP Client.

Thin wrapper over requests (or urllib fallback if requests not installed).
Provides typed methods for all /api/agent/* endpoints.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

try:
    import requests  # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class AgentError(Exception):
    """Raised when backend returns an error."""

    def __init__(self, message: str, status: int = 0, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class HotspotClient:
    """HTTP client for hotspot backend agent API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: int = 30,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self._use_requests = _HAS_REQUESTS

    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
    ) -> Any:
        url = f"{self.base}{path}"
        if self._use_requests:
            return self._request_requests(method, url, json_body)
        return self._request_urllib(method, url, json_body)

    def _request_requests(self, method: str, url: str, json_body: Optional[dict]) -> Any:
        try:
            r = requests.request(
                method=method,
                url=url,
                json=json_body,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise AgentError(f"network error: {e}") from e
        if r.status_code >= 400:
            raise AgentError(
                f"HTTP {r.status_code}: {r.text[:200]}",
                status=r.status_code,
                body=r.text,
            )
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    def _request_urllib(self, method: str, url: str, json_body: Optional[dict]) -> Any:
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                try:
                    return json.loads(body)
                except ValueError:
                    return {"raw": body}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise AgentError(
                f"HTTP {e.code}: {body[:200]}",
                status=e.code,
                body=body,
            ) from e
        except urllib.error.URLError as e:
            raise AgentError(f"network error: {e}") from e

    # ---- 端点 ----

    def get_tasks(self, status: str = "pending", limit: int = 10) -> list[dict]:
        """拉取任务列表."""
        result = self._request("GET", f"/api/agent/tasks?status={status}&limit={limit}")
        return result.get("tasks", [])

    def get_task(self, task_id: int) -> dict:
        """查询单个任务."""
        return self._request("GET", f"/api/agent/tasks/{task_id}")

    def write_knowledge(self, payload: dict) -> dict:
        """写回知识条目."""
        return self._request("POST", "/api/agent/knowledge", json_body=payload)

    def complete_task(
        self,
        task_id: int,
        status: str = "done",
        result: Optional[dict] = None,
        error: str = "",
    ) -> dict:
        """标记任务完成."""
        body = {"status": status, "result": result or {}, "error": error}
        return self._request(
            "POST",
            f"/api/agent/tasks/{task_id}/complete",
            json_body=body,
        )

    def health_check(self) -> bool:
        """检查后端是否可达."""
        try:
            self._request("GET", "/api/health")
            return True
        except AgentError:
            return False
