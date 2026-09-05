"""全局并发单一真相源 (v0.8.2 Y-A1, CRITICAL_REVIEW §1.1)。

背景: ``asyncio.Semaphore`` 此前散落 7+ 文件各自创建 — LLM 出站无并发上限
(llm.yaml ``max_concurrent`` 声明但全仓零消费), 批处理信号量互不感知
(同一端点被 N 个调用方 × N 份并发放大), provider/源站 429 无背压。

契约:
- ``get_semaphore(group, size=None)`` 按 **(group, event-loop)** 惰性建
  Semaphore: 同进程同 loop 同 group 共享一个预算; 同 group 重复调用时
  **首次 size 生效** (后续实参仅作声明, 不重建)。
- size 解析: 显式实参 > env ``HOTSPOT_CONCURRENCY_<GROUP 大写下划线>`` >
  内建默认 4。
- **loop 键控**: asyncio 原语不可跨 loop 复用 (混用抛
  "bound to a different event loop") — 注册表以 running loop 为键,
  生产单 loop 下即进程级单例, 测试多 loop 天然隔离。
- **等待即背压**: 获取不设超时、不计健康窗口 (饱和 ≠ 失败, 不驱动
  breaker) — 这是限流与熔断的正交边界 (v0.8.1 Day 2 契约延续)。

接入点 (v0.8.2 Y-A1): gateway._call_provider 与 image_service 出站
(``llm:<provider>``, size=llm.yaml max_concurrent) / crawl4ai_client
(``crawl4ai``) / summary_enricher (``enrich``) / url_batch_check +
quality jobs (``url_check``) / knowledge job (``knowledge_sync``) /
source_scheduler (``source_fetch``)。
"""
from __future__ import annotations

import asyncio
import os
import threading
import weakref
from typing import Any

from backend.logging_config import logger

DEFAULT_SIZE = 4

_lock = threading.Lock()
# loop -> {group: (Semaphore, size)}; 弱键 — loop 关闭被 GC 后条目自动消失,
# 既防泄漏也防 id() 地址复用把两个不同 loop 判成同一个 (测试实测踩中)。
# 无 running loop 的同步上下文用模块级哨兵占位 (首次 await 绑定当时的 loop)。
_registry: weakref.WeakKeyDictionary[Any, dict[str, tuple[asyncio.Semaphore, int]]] = (
    weakref.WeakKeyDictionary()
)


class _SyncContext:
    """无 running loop 占位键 (普通实例支持弱引用; 模块强引用永不过期)。"""


_SYNC_CONTEXT = _SyncContext()


def _context_key() -> Any:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return _SYNC_CONTEXT


def _env_size(group: str) -> int | None:
    """HOTSPOT_CONCURRENCY_<GROUP> → int | None (非法值忽略不抛)。"""
    env_name = "HOTSPOT_CONCURRENCY_" + group.upper().replace(":", "_").replace("-", "_")
    raw = os.getenv(env_name)
    if raw is None:
        return None
    try:
        v = int(raw)
    except ValueError:
        return None
    return v if v >= 1 else None


def get_semaphore(group: str, size: int | None = None) -> asyncio.Semaphore:
    """取 (group, loop) 级共享 Semaphore — 首次创建定容, 后续共享。

    Args:
        group: 并发组名 (如 ``llm:sensenova`` / ``enrich`` / ``url_check``)。
        size: 首次创建时的容量; None 则查 env, 再退 DEFAULT_SIZE。
    """
    ctx = _context_key()
    with _lock:
        sub = _registry.get(ctx)
        if sub is None:
            sub = {}
            _registry[ctx] = sub
        entry = sub.get(group)
        if entry is None:
            effective = size if size is not None and size >= 1 else None
            if effective is None:
                effective = _env_size(group) or DEFAULT_SIZE
            entry = (asyncio.Semaphore(effective), effective)
            sub[group] = entry
            logger.debug("concurrency registry: group={} size={}", group, effective)
        return entry[0]


def registry_snapshot() -> dict[str, int]:
    """当前 loop 的组 → 容量快照 (测试与运维自省; 无 loop 返回空)。"""
    ctx = _context_key()
    with _lock:
        sub = _registry.get(ctx)
        if not sub:
            return {}
        return {group: size for group, (_, size) in sub.items()}


def reset_concurrency() -> None:
    """清空注册表 (测试复位; 下一 get 重建)。"""
    with _lock:
        _registry.clear()


__all__ = ["DEFAULT_SIZE", "get_semaphore", "registry_snapshot", "reset_concurrency"]
