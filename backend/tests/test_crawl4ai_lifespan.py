"""gateway 方案第 1 步: crawl4ai 单例 lifespan 优雅停机测试.

缺口背景: crawl4ai_client.get_client() 的 Playwright/Chromium 单例常驻
进程, 此前 FastAPI lifespan shutdown 从未调用 close_client() — 进程
退出时浏览器变僵尸进程。本文件锁定: TestClient 退出 (lifespan 收尾)
时 close_client 必须被调用且异常被吞 (不阻塞 shutdown)。
"""
from __future__ import annotations

import pytest


@pytest.fixture
def _stub_scheduler_stop(monkeypatch):
    """隔离 lifespan 里的 scheduler.stop / DB teardown 对真实资源的依赖.

    TestClient(__enter__/__exit__) 会走完整 lifespan: startup 建调度器
    + shutdown 停调度器。这里只 stub stop 的副作用, 其余保持真实路径。
    """
    # scheduler.stop 在 shutdown 分支被调用 — mock 掉避免真实线程池等待
    from backend.scheduler.scheduler import HotspotScheduler

    monkeypatch.setattr(HotspotScheduler, "stop", lambda self: None)


def test_lifespan_shutdown_calls_close_client(monkeypatch, _stub_scheduler_stop):
    """lifespan yield 之后 (TestClient 退出) 必须调 close_client()."""
    from fastapi.testclient import TestClient

    from backend.utils import crawl4ai_client

    called = {"closed": False}

    async def fake_close():
        called["closed"] = True

    monkeypatch.setattr(crawl4ai_client, "close_client", fake_close)

    from backend.main import app
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
    # with 退出 = lifespan shutdown 已跑
    assert called["closed"] is True


def test_lifespan_shutdown_swallows_close_client_error(monkeypatch, _stub_scheduler_stop):
    """close_client 抛异常不能阻塞 shutdown (scheduler.stop / close_db 仍执行)."""
    from fastapi.testclient import TestClient

    from backend.utils import crawl4ai_client

    async def boom():
        raise RuntimeError("playwright gone")

    monkeypatch.setattr(crawl4ai_client, "close_client", boom)

    from backend.main import app
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
    # with 退出未抛异常 = shutdown 链路完整
