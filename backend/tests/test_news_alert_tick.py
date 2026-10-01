"""_news_alert_tick — 采集尾部挂点 (异常隔离契约, 2026-09-27 四模式 P1)。

契约:
- news_alert_service 崩溃时 _tick 不抛 (不阻塞 post-ingest 链)
- 正常路径调用一次 run_news_alert_review
- alerted > 0 时经 backend.core.events.publish_event 发 SSE news_alert
  事件 (发布端在 async 上下文直接 await; 服务侧不再自行 spawn,
  原方案 ensure_future 无 running loop 会静默失败)
"""
import asyncio

from backend.scheduler.jobs.collect import _news_alert_tick


def _patch_service(monkeypatch, result=None, impl=None):
    """monkeypatch run_news_alert_review (tick 内 lazy import, patch 模块属性即命中)。"""
    monkeypatch.setattr(
        "backend.services.news_alert_service.run_news_alert_review",
        impl if impl is not None else (lambda **kw: result),
    )


class TestNewsAlertTick:
    def test_tick_isolates_crash(self, monkeypatch):
        def boom(**kw):
            raise RuntimeError("service crashed")
        _patch_service(monkeypatch, impl=boom)
        asyncio.run(_news_alert_tick())  # 不抛 = 通过

    def test_tick_calls_service(self, monkeypatch):
        called = {"n": 0}

        def fake(**kw):
            called["n"] += 1
            return {"candidates": 1, "alerted": 1}
        _patch_service(monkeypatch, impl=fake)
        asyncio.run(_news_alert_tick())
        assert called["n"] == 1

    def test_tick_publishes_sse_when_alerted(self, monkeypatch):
        """alerted>0 → publish_event('news_alert', {'count': N}) 恰好一次。"""
        calls = []

        async def fake_publish(event_type, data, **kw):
            calls.append((event_type, data))

        _patch_service(monkeypatch, result={"candidates": 1, "alerted": 1})
        monkeypatch.setattr("backend.core.events.publish_event", fake_publish)
        asyncio.run(_news_alert_tick())
        assert calls == [("news_alert", {"count": 1})]


def test_pick_tick_isolates_crash(monkeypatch):
    def boom(**kw):
        raise RuntimeError("crash")
    monkeypatch.setattr("backend.services.pick_service.refresh_pick_scores", boom)
    from backend.scheduler.jobs.collect import _pick_score_tick
    asyncio.run(_pick_score_tick())  # 不抛 = 通过


def test_pick_tick_calls_service(monkeypatch):
    called = {"n": 0}

    def fake(**kw):
        called["n"] += 1
        return {"evaluated": 5, "picked": 3}
    monkeypatch.setattr("backend.services.pick_service.refresh_pick_scores", fake)
    from backend.scheduler.jobs.collect import _pick_score_tick
    asyncio.run(_pick_score_tick())
    assert called["n"] == 1
