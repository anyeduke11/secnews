"""DSHTaskRouter — 运行时 task → agent 路由 + DSH/LLM 降级.

复用 backend.config.agent_runner_schema.route() 做 task_type → agent 决策;
DSH 不可达时自动降级到 llm_service 直连。
"""
from __future__ import annotations

import logging
from typing import Any

from backend.config.agent_runner_schema import route
from backend.services.ai_hub import llm_service

log = logging.getLogger("hotspot.dsh.task_router")


class DSHTaskRouter:
    """task_type → DSH 或 LLM fallback."""

    def __init__(self, dsh_client: Any | None = None) -> None:
        # 延迟导入避免循环
        self._dsh = dsh_client

    def dispatch(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送任务: 优先 DSH, 不可达降级 llm_service."""
        agent = route(task_type)
        log.info("dispatch task_type=%s → agent=%s", task_type, agent)

        if agent != "builtin" and self._dsh is not None:
            try:
                return self._dsh.send_task(task_type, payload)
            except Exception as e:
                log.warning("DSH dispatch failed, fallback to llm: %s", e)

        # fallback: 直接 LLM
        return self._llm_fallback(task_type, payload)

    def _llm_fallback(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """LLM 直连兜底."""
        content = payload.get("content", "")
        if not content:
            return {"ok": False, "error": "empty content"}

        try:
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                score = loop.run_until_complete(llm_service.score(content))
            finally:
                loop.close()
            return {"ok": True, "agent": "llm_direct", "score": score}
        except Exception as e:
            log.error("LLM fallback failed: %s", e)
            return {"ok": False, "agent": "llm_direct", "error": str(e)}
