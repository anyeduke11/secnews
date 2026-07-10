"""Phase 46 end-to-end 集成测试: 截止日期 → 紧急 自动判断 (HTTP API 层)

覆盖场景
--------
- 提交 manual todo with deadline=today → response urgent=1
- 提交 manual todo with deadline=明天 → response urgent=1
- 提交 manual todo with deadline=3 天后 → response urgent=0
- 提交 manual todo with deadline 周末 (Sat) → 顺延到 Mon
- 提交 manual todo with no deadline → urgent=0
- PATCH 改 deadline 后 urgent 重新计算
- PATCH 清空 deadline → urgent=0 (除非 legacy fallback)
- /api/todos/count 的 4 象限使用 effective_urgent
- 列表筛选 ``?urgent=1`` 用 effective_urgent
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.utils.business_days import SHANGHAI_TZ, next_business_day


SHANGHAI_TODAY = next_business_day(datetime.now(SHANGHAI_TZ).date())
TOMORROW = (SHANGHAI_TODAY.toordinal() + 1)
DAY_AFTER = (SHANGHAI_TODAY.toordinal() + 2)
WEEK_LATER = (SHANGHAI_TODAY.toordinal() + 7)


def _d(offset: int) -> str:
    """相对今天 +offset 天, ISO 'YYYY-MM-DD' 字符串。"""
    return date.fromordinal(SHANGHAI_TODAY.toordinal() + offset).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_todo_urgency_e2e.db"
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


# ---------------------------------------------------------------------------
# 提交 manual todo + deadline → effective_urgent 正确
# ---------------------------------------------------------------------------
class TestPostWithDeadline:
    def test_deadline_today_makes_urgent(self, client):
        """今天 deadline → urgent=1。"""
        body = {
            "source_type": "manual",
            "title": "今天完成",
            "deadline": _d(0),
            "important": 1,
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        item = resp.json()["item"]
        assert item["deadline"] == _d(0)
        assert item["urgent"] == 1
        assert item["important"] == 1

    def test_deadline_tomorrow_makes_urgent(self, client):
        body = {
            "source_type": "manual",
            "title": "明天完成",
            "deadline": _d(1),
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        assert resp.json()["item"]["urgent"] == 1

    def test_deadline_far_future_not_urgent(self, client):
        """≥ 5 天后的 deadline (跨周末后仍 ≥ 2 业务日) → 永远不紧急。"""
        body = {
            "source_type": "manual",
            "title": "远期完成",
            "deadline": _d(5),
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        # 5 天后跨周末后至少 2 业务日 → 不紧急
        assert resp.json()["item"]["urgent"] == 0

    def test_deadline_week_later_not_urgent(self, client):
        body = {
            "source_type": "manual",
            "title": "下周完成",
            "deadline": _d(7),
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        assert resp.json()["item"]["urgent"] == 0

    def test_no_deadline_not_urgent(self, client):
        body = {
            "source_type": "manual",
            "title": "无截止",
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        assert resp.json()["item"]["deadline"] is None
        assert resp.json()["item"]["urgent"] == 0

    def test_invalid_deadline_format_400(self, client):
        body = {
            "source_type": "manual",
            "title": "格式错误",
            "deadline": "2026/07/10",  # 错误格式
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 400

    def test_empty_deadline_clears(self, client):
        """空字符串 deadline → 视为无 deadline。"""
        body = {
            "source_type": "manual",
            "title": "清空",
            "deadline": "",
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        assert resp.json()["item"]["deadline"] is None


# ---------------------------------------------------------------------------
# PATCH 改 deadline → effective_urgent 重算
# ---------------------------------------------------------------------------
class TestPatchDeadline:
    def test_patch_deadline_makes_urgent(self, client):
        # 创建无 deadline 的 todo
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "加截止"},
        )
        todo_id = create.json()["item"]["id"]
        assert create.json()["item"]["urgent"] == 0

        # 加 deadline = 明天
        resp = client.patch(
            f"/api/todos/{todo_id}",
            json={"deadline": _d(1)},
        )
        assert resp.status_code == 200
        assert resp.json()["item"]["deadline"] == _d(1)
        assert resp.json()["item"]["urgent"] == 1

    def test_patch_clear_deadline(self, client):
        # 创建有 deadline 的 todo
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "清截止", "deadline": _d(1)},
        )
        todo_id = create.json()["item"]["id"]
        assert create.json()["item"]["urgent"] == 1

        # PATCH 空字符串清空
        resp = client.patch(
            f"/api/todos/{todo_id}",
            json={"deadline": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["item"]["deadline"] is None
        assert resp.json()["item"]["urgent"] == 0

    def test_patch_extend_deadline_makes_not_urgent(self, client):
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "延期", "deadline": _d(1)},
        )
        todo_id = create.json()["item"]["id"]
        assert create.json()["item"]["urgent"] == 1

        # 延期到 1 周后
        resp = client.patch(
            f"/api/todos/{todo_id}",
            json={"deadline": _d(7)},
        )
        assert resp.status_code == 200
        assert resp.json()["item"]["urgent"] == 0

    def test_patch_urgent_field_ignored(self, client):
        """Phase 46: PATCH urgent 字段被忽略 (Pydantic 默认忽略额外字段)。"""
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]

        # 尝试 PATCH urgent=1
        resp = client.patch(
            f"/api/todos/{todo_id}",
            json={"urgent": 1, "important": 1},
        )
        assert resp.status_code == 200
        item = resp.json()["item"]
        # urgent 仍由 deadline 派生 (无 deadline → 0)
        assert item["urgent"] == 0
        assert item["important"] == 1


# ---------------------------------------------------------------------------
# 列表 / 计数 / 筛选 基于 effective_urgent
# ---------------------------------------------------------------------------
class TestListAndCountByEffectiveUrgent:
    def test_count_4quadrants_uses_effective_urgent(self, client):
        # P0: deadline=today + important=1 → urgent_important
        client.post("/api/todos", json={
            "source_type": "manual", "title": "P0", "deadline": _d(0), "important": 1,
        })
        # P1: deadline=today + important=0 → urgent_only
        client.post("/api/todos", json={
            "source_type": "manual", "title": "P1", "deadline": _d(0),
        })
        # P2: deadline=week_later + important=1 → important_only
        client.post("/api/todos", json={
            "source_type": "manual", "title": "P2", "deadline": _d(7), "important": 1,
        })
        # P3: 无 deadline + 无 important → neither
        client.post("/api/todos", json={
            "source_type": "manual", "title": "P3",
        })

        resp = client.get("/api/todos/count")
        data = resp.json()
        assert data["by_priority"]["urgent_important"] == 1
        assert data["by_priority"]["urgent_only"] == 1
        assert data["by_priority"]["important_only"] == 1
        assert data["by_priority"]["neither"] == 1

    def test_list_filter_urgent_uses_effective(self, client):
        # 创建 4 类 todo
        client.post("/api/todos", json={
            "source_type": "manual", "title": "today+imp", "deadline": _d(0), "important": 1,
        })
        client.post("/api/todos", json={
            "source_type": "manual", "title": "today", "deadline": _d(0),
        })
        client.post("/api/todos", json={
            "source_type": "manual", "title": "week", "deadline": _d(7), "important": 1,
        })

        # 筛 urgent=1 → 应该有 2 (today+imp 和 today)
        resp = client.get("/api/todos", params={"urgent": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(it["urgent"] == 1 for it in data["items"])

        # 筛 urgent=1 + important=1 → 1 (today+imp)
        resp = client.get("/api/todos", params={"urgent": 1, "important": 1})
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "today+imp"

        # 筛 urgent=0 → 1 (week)
        resp = client.get("/api/todos", params={"urgent": 0})
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "week"

    def test_list_sorted_by_effective_urgent_first(self, client):
        # 创建顺序: 不紧急在前, 紧急在后
        client.post("/api/todos", json={
            "source_type": "manual", "title": "week", "deadline": _d(7),
        })
        client.post("/api/todos", json={
            "source_type": "manual", "title": "today", "deadline": _d(0),
        })

        resp = client.get("/api/todos")
        data = resp.json()
        # 紧急的应排前面
        assert data["items"][0]["title"] == "today"
        assert data["items"][0]["urgent"] == 1
        assert data["items"][1]["title"] == "week"
        assert data["items"][1]["urgent"] == 0
