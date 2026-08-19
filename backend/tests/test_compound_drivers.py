"""v0.4.3 复利驱动器测试 — 4 个驱动器的行为 + 异常隔离。

覆盖 P1 验收项:
- 采集后即时分类 (domain 非 null)
- sm2_daily_push_job → SSE review_due 事件
- map_rebuild_daily_job → _MAP.md 重建
- 驱动器异常隔离 (任一崩溃不影响采集)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.scheduler.jobs import (
    _classify_new_items,
    map_rebuild_daily_job,
    sm2_daily_push_job,
)


def _insert_item(conn, item_id: str, title: str, tags: str, domain=None,
                 type_=None, difficulty=None, minutes_ago: int = 1) -> None:
    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    conn.execute(
        "INSERT INTO knowledge_items (id, title, source, source_url, domain, topic, "
        "type, difficulty, tags, ingested_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, title, "unit-test", f"https://example.com/{item_id}",
         domain, None, type_, difficulty, tags, now.isoformat(), now.isoformat()),
    )
    conn.commit()


def _insert_review(conn, review_id: str, entity_id: str, due_days_ago: int = 0) -> None:
    due_at = (datetime.now(timezone.utc) - timedelta(days=due_days_ago)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO sm2_reviews (id, entity_type, entity_id, easiness, interval, "
        "repetitions, due_at, created_at, updated_at) "
        "VALUES (?, 'item', ?, 2.5, 1, 0, ?, ?, ?)",
        (review_id, entity_id, due_at, now, now),
    )
    conn.commit()


class TestClassifyNewItems:
    def test_classifies_recent_unclassified_items(self, temp_db, monkeypatch):
        """驱动器①: 5 分钟窗口内未分类 item → domain 填充 + md 回写."""
        from backend.repository.db import get_connection

        conn = get_connection()
        _insert_item(conn, "driver-a1", "GPT-5 架构深度解析",
                     '["AI编程","技术原理"]')
        _insert_item(conn, "driver-a2", "量子计算进展",
                     '["quantum","research"]', domain="tech", type_="news",
                     difficulty="medium")

        calls = {"count": 0}

        orig_write = None
        import backend.services.knowledge_sync as ks
        orig_write = ks.write_item_to_md
        written = []

        def fake_write(item):
            written.append(item["id"])
            return None

        monkeypatch.setattr(ks, "write_item_to_md", fake_write)
        try:
            asyncio.run(_classify_new_items())
        finally:
            ks.write_item_to_md = orig_write

        row = conn.execute(
            "SELECT domain, type, difficulty FROM knowledge_items WHERE id='driver-a1'"
        ).fetchone()
        assert row is not None
        assert row["domain"] is not None
        assert row["type"] is not None
        assert row["difficulty"] is not None
        assert "driver-a1" in written
        assert "driver-a2" not in written
        calls["count"] = len(written)
        assert calls["count"] == 1

    def test_old_items_not_touched(self, temp_db):
        """窗口外 (30 分钟前) 的未分类 item 不处理."""
        from backend.repository.db import get_connection

        conn = get_connection()
        _insert_item(conn, "driver-old1", "旧条目无 domain",
                     '["old"]', minutes_ago=30)

        asyncio.run(_classify_new_items())

        row = conn.execute(
            "SELECT domain FROM knowledge_items WHERE id='driver-old1'"
        ).fetchone()
        assert row["domain"] is None


class TestSm2DailyPush:
    def test_pushes_review_due_event(self, temp_db, monkeypatch):
        """驱动器②: 有待复习条目 → publish review_due."""
        from backend.repository.db import get_connection
        from backend.api import events

        conn = get_connection()
        _insert_review(conn, "r-1", "concept-alpha", due_days_ago=1)

        captured = {}

        async def fake_publish(event_type, data):
            captured["type"] = event_type
            captured["data"] = data

        monkeypatch.setattr(events, "publish_event", fake_publish)
        asyncio.run(sm2_daily_push_job())

        assert captured["type"] == "review_due"
        assert captured["data"]["count"] == 1
        assert captured["data"]["items"][0]["id"] == "concept-alpha"

    def test_no_due_no_event(self, temp_db, monkeypatch):
        """无到期条目 → 不推送."""
        from backend.repository.db import get_connection
        from backend.api import events

        conn = get_connection()
        _insert_review(conn, "r-2", "concept-beta", due_days_ago=-1)

        called = {"v": False}

        async def fake_publish(event_type, data):
            called["v"] = True

        monkeypatch.setattr(events, "publish_event", fake_publish)
        asyncio.run(sm2_daily_push_job())
        assert called["v"] is False


class TestMapRebuildDaily:
    def test_rebuilds_map_file(self, temp_db):
        """驱动器③: 重建 _MAP.md 到隔离目录."""
        from backend.repository.db import get_connection
        from backend.services.map_updater import MAP_PATH

        conn = get_connection()
        _insert_item(conn, "driver-m1", "零信任架构",
                     '["zero-trust","security"]', domain="tech")

        MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(map_rebuild_daily_job())

        assert MAP_PATH.exists()
        content = MAP_PATH.read_text(encoding="utf-8")
        assert "零信任" in content or "zero" in content.lower() or "driver-m1" in content


class TestDriverExceptionIsolation:
    def test_classify_crash_does_not_raise(self, temp_db, monkeypatch):
        """异常隔离: batch_classify 崩溃 → _classify_new_items 捕获不抛出."""
        from backend.repository.db import get_connection
        from backend.services import auto_classifier

        conn = get_connection()
        _insert_item(conn, "driver-x1", "GPT-5 架构深度解析",
                     '["AI编程","技术原理"]')

        def boom(items):
            raise RuntimeError("classifier down")

        monkeypatch.setattr(auto_classifier, "batch_classify", boom)
        result = asyncio.run(_classify_new_items())
        assert result is None

    def test_sm2_push_crash_does_not_raise(self, temp_db, monkeypatch):
        """异常隔离: publish_event 崩溃 → sm2_daily_push_job 捕获不抛出."""
        from backend.api import events
        from backend.repository.db import get_connection

        _insert_review(get_connection(), "r-3", "concept-gamma", due_days_ago=1)

        async def boom(*a, **k):
            raise RuntimeError("sse down")

        monkeypatch.setattr(events, "publish_event", boom)
        result = asyncio.run(sm2_daily_push_job())
        assert result is None