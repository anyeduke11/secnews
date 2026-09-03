"""dsh (DeepSeek Harness) 桥接子包 (v0.6 P0 dsh 桥接层).

对外暴露:
- DSHClient: HTTP 客户端 (health/send_task/get_session)
- DSHTaskRouter: 运行时 task → agent 路由 + DSH/LLM 降级
- DSHSessionManager: 会话生命周期 (内存 MVP)
- DshRuntime / DshRuntimeMode / dsh_runtime: v0.8 B4 mock/真子进程
  运行时切换 (settings.kv 持久化 + 失败自动回退 mock)
"""
from __future__ import annotations

from backend.services.dsh.bridge import DSHClient
from backend.services.dsh.runtime import DshRuntime, DshRuntimeMode, dsh_runtime
from backend.services.dsh.session import DSHSessionManager
from backend.services.dsh.task_router import DSHTaskRouter

__all__ = [
    "DSHClient",
    "DSHSessionManager",
    "DSHTaskRouter",
    "DshRuntime",
    "DshRuntimeMode",
    "dsh_runtime",
]
