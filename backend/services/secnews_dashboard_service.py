"""SecNews Dashboard 聚合服务 — build_dashboard 工厂 (Batch 2 D 下沉)。

v0.6.3 P0-1 卡顿根治的线程亲和纪律落点: ``get_connection`` 是 thread-local
(SQLite 连接默认 check_same_thread=True), handler 跑在 ``asyncio.to_thread``
工作线程, **必须在工作线程内** 取连接并构造 dashboard — 缓存整个 dashboard
会把首个线程的连接带进别的线程 → ProgrammingError。

本服务把「每请求新建聚合器 + 当前线程连接」的装配从 api 层收拢,
``wiki_fs`` 是进程级单例只取一次; api 层只负责路由与 to_thread。
"""
from __future__ import annotations

from backend.secnews_dashboard import SecNewsDashboard

_wiki_fs = None


def build_dashboard() -> SecNewsDashboard:
    """每次调用新建聚合器 (轻量, 无状态), db 取自当前线程连接。"""
    global _wiki_fs
    from backend.repository.db import get_connection

    if _wiki_fs is None:
        from backend.kl_pipeline.runtime import get_production_wiki_fs

        _wiki_fs = get_production_wiki_fs()
    return SecNewsDashboard(db=get_connection(), wiki_fs=_wiki_fs)


__all__ = ["build_dashboard"]
