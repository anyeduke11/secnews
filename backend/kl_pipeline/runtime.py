"""KL 管线生产运行时装配 — API 层与 scheduler job 共用的单一出口。

依赖方向: scheduler/jobs → kl_pipeline.runtime → (wiki_fs, ai_hub);
调度器禁止 import backend.api, 故生产单例收敛在本模块。

装配内容 (2026-08-24 wiki 单根裁决 + S1-6):
- wiki_fs   = resolve_wiki_root() 指向 llm-wiki-2.0 (知识唯一存档根)
- llm_client= AIHubLLMClient (ai_hub 单例的同步适配; 未配置 provider 时
  refine 自动走降级摘要)
- queue     = KLQueue(None) 内部落 get_connection() (运营层/事件管理)
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_wiki_fs: Any = None
_pipeline: Any = None


def get_production_pipeline() -> Any:
    """返回生产 KLPipeline 单例 (双检锁, 进程内复用)。"""
    global _pipeline, _wiki_fs
    if _pipeline is None:
        with _lock:
            if _pipeline is None:
                from backend.kl_pipeline import KLPipeline
                from backend.kl_pipeline.llm_adapter import AIHubLLMClient
                from backend.wiki_fs import WikiFs
                from backend.wiki_fs.root import resolve_wiki_root

                if _wiki_fs is None:
                    _wiki_fs = WikiFs(resolve_wiki_root())
                _pipeline = KLPipeline(
                    wiki_fs=_wiki_fs,
                    llm_client=AIHubLLMClient(),
                )
    return _pipeline


def get_production_wiki_fs() -> Any:
    """返回生产 WikiFs 单例 (隐式触发管线装配)。"""
    get_production_pipeline()
    return _wiki_fs


def reset_runtime() -> None:
    """清空单例 (测试隔离用)。"""
    global _pipeline, _wiki_fs
    with _lock:
        _pipeline = None
        _wiki_fs = None


__all__ = [
    "get_production_pipeline",
    "get_production_wiki_fs",
    "reset_runtime",
]
