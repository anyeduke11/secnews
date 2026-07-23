"""v1.7 Phase 3 — Mode API 端到端测试.

覆盖:
- GET /api/mode/current: 无简报 → scan, 有未读简报 → brief
- GET /api/mode/current: 已读简报 → scan
- PUT /api/mode/switch: 合法模式 → 200, 非法模式 → 400
- PUT /api/mode/switch: 切换后标记简报已读
- GET /api/mode/modes: 返回模式列表
- digest_service: has_unread_digest / mark_digest_read / create_digest
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.services.digest_service import (
    create_digest,
    has_unread_digest,
    mark_digest_read,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mode_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestCurrentMode:
    def test_no_digest_returns_scan(self, client):
        r = client.get("/api/mode/current")
        assert r.status_code == 200
        assert r.json() == {"version": "1.7.0", "mode": "scan"}

    def test_unread_digest_returns_brief(self, client):
        create_digest("d1", period="daily", summary="今日简报")
        r = client.get("/api/mode/current")
        assert r.status_code == 200
        assert r.json()["mode"] == "brief"

    def test_read_digest_returns_scan(self, client):
        create_digest("d1", period="daily", summary="今日简报")
        mark_digest_read()
        r = client.get("/api/mode/current")
        assert r.json()["mode"] == "scan"

    def test_version_envelope(self, client):
        r = client.get("/api/mode/current")
        assert r.json()["version"] == "1.7.0"


class TestSwitchMode:
    @pytest.mark.parametrize("mode", ["brief", "scan", "deep", "organize", "review", "alert"])
    def test_valid_modes_accepted(self, client, mode):
        r = client.put("/api/mode/switch", params={"mode": mode})
        assert r.status_code == 200
        assert r.json() == {"version": "1.7.0", "mode": mode}

    def test_invalid_mode_rejected_400(self, client):
        r = client.put("/api/mode/switch", params={"mode": "invalid"})
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "invalid mode" in detail["message"]
        assert "brief" in detail["valid_modes"]

    def test_switch_marks_digest_read(self, client):
        """切换模式后, 后续 /current 应返回 scan (简报标记已读)。"""
        create_digest("d1", period="daily", summary="今日简报")
        # 初始: 有未读 → brief
        assert client.get("/api/mode/current").json()["mode"] == "brief"
        # 切换模式 → 标记已读
        client.put("/api/mode/switch", params={"mode": "scan"})
        # 后续: 已读 → scan
        assert client.get("/api/mode/current").json()["mode"] == "scan"

    def test_switch_to_brief_also_marks_read(self, client):
        """即使切换到 brief, 也标记简报已读 (用户已查看)。"""
        create_digest("d1", period="daily", summary="今日简报")
        client.put("/api/mode/switch", params={"mode": "brief"})
        assert client.get("/api/mode/current").json()["mode"] == "scan"


class TestListModes:
    def test_returns_all_modes(self, client):
        r = client.get("/api/mode/modes")
        assert r.status_code == 200
        modes = r.json()["modes"]
        assert set(modes) == {"brief", "scan", "deep", "organize", "review", "alert"}

    def test_modes_sorted(self, client):
        r = client.get("/api/mode/modes")
        modes = r.json()["modes"]
        assert modes == sorted(modes)


class TestDigestService:
    def test_has_unread_no_digest(self, temp_db):
        assert has_unread_digest() is False

    def test_has_unread_with_today_digest(self, temp_db):
        create_digest("d1", period="daily", summary="今日简报")
        assert has_unread_digest() is True

    def test_has_unread_after_mark_read(self, temp_db):
        create_digest("d1", period="daily", summary="今日简报")
        mark_digest_read()
        assert has_unread_digest() is False

    def test_has_unread_old_digest_ignored(self, temp_db):
        """昨日简报不算未读 (验收 4: 每日首次返回 brief)。"""
        from backend.repository.db import get_connection
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn = get_connection()
        conn.execute(
            "INSERT INTO digests (id, period, summary, item_ids, created_at) VALUES (?, ?, ?, ?, ?)",
            ("d_old", "daily", "昨日简报", "[]", yesterday),
        )
        assert has_unread_digest() is False

    def test_has_unread_new_digest_after_read(self, temp_db):
        """读取旧简报后, 新简报到达 → 再次未读。"""
        create_digest("d1", period="daily", summary="简报1")
        mark_digest_read()
        assert has_unread_digest() is False
        # 新简报到达 (create_digest 用当前时间, 必然晚于 mark_digest_read)
        create_digest("d2", period="daily", summary="简报2")
        assert has_unread_digest() is True

    def test_create_digest_returns_record(self, temp_db):
        result = create_digest("d1", period="daily", summary="测试", item_ids=["h1", "h2"])
        assert result["id"] == "d1"
        assert result["period"] == "daily"
        assert result["summary"] == "测试"
        # Phase 4 起 DigestRepository 统一返回解析后的 list (而非 JSON 字符串)
        assert result["item_ids"] == ["h1", "h2"]

    def test_create_digest_upsert(self, temp_db):
        create_digest("d1", period="daily", summary="旧内容")
        create_digest("d1", period="daily", summary="新内容")
        from backend.repository.db import get_connection
        row = get_connection().execute("SELECT summary FROM digests WHERE id='d1'").fetchone()
        assert row["summary"] == "新内容"
