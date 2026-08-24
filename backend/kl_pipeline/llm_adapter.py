"""ai_hub LLM 同步适配器 — kl_pipeline stages 期望的 chat() 接口桥接。

stage handler 是同步函数, 期望 ``llm_client.chat(prompt, response_format=...)``
返回文本; ai_hub.llm_service 提供 async generate(prompt)。本适配器做
async→sync 桥接:
- 工作线程 (scheduler asyncio.to_thread) 无事件循环 → asyncio.run 直跑;
- API 事件循环线程内调用 → 独立单线程池跑新循环, 避免嵌套循环。

generate() 在未配置 provider / 全部失败时返回 "" — refine 阶段据此
走降级摘要 (S1-6), 不抛异常。
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# chat() 桥接超时: refine 为轻 AI 任务 (flash 档), 3 分钟足够。
_CHAT_TIMEOUT_SECONDS = 180


class AIHubLLMClient:
    """把 ai_hub.llm_service (async generate) 适配为同步 chat() 客户端。"""

    def __init__(self, service: Any = None) -> None:
        # 允许注入测试替身; 生产路径惰性复用 ai_hub 模块级单例。
        self._service = service
        self._lock = threading.Lock()

    def _svc(self) -> Any:
        with self._lock:
            if self._service is None:
                from backend.services.ai_hub import llm_service
                self._service = llm_service
            return self._service

    def chat(self, prompt: str, response_format: str | None = None) -> str:
        """同步生成文本。response_format 仅作 stage 侧契约标记, 由
        refine 自行解析 JSON; 底层 generate() 返回原始文本。"""
        svc = self._svc()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(svc.generate(prompt))
        # 已在事件循环内 (API 同步路径): 用独立线程跑新循环。
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, svc.generate(prompt)).result(
                timeout=_CHAT_TIMEOUT_SECONDS
            )


__all__ = ["AIHubLLMClient"]
