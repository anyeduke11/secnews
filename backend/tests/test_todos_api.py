"""Phase 36 Todos API 端到端测试

覆盖范围:
  - POST  /api/todos
    * favorite-source 新建 → 201 + created=true
    * favorite-source 重复 → 200 + created=false + 同一 id
    * manual → 201
  - PATCH /api/todos/{id}
    * 状态迁移时间戳正确 (open→done→archived→open)
    * 404
  - DELETE /api/todos/{id} → 204
  - GET   /api/todos 多维筛选
  - GET   /api/todos/count
  - GET   /api/todos/available_favorites 排除已入 todo
  - POST 错误参数 (缺 title / 错 source_type) → 400
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.favorite_repo import FavoriteRepository
from backend.repository.todo_repo import TodoRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_todos_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def fav_repo(temp_db) -> FavoriteRepository:
    return FavoriteRepository()


@pytest.fixture
def todo_repo(temp_db) -> TodoRepository:
    return TodoRepository()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


def _add_fav(fav_repo, hid: str, category: str = "ai", title: str = "T"):
    fav_repo.add(
        hotspot_id=hid, category=category, title=title,
        source="src", url=f"https://e.com/{hid}",
    )


# ===========================================================================
# 1. POST /api/todos
# ===========================================================================
class TestTodosAPIPost:
    def test_post_favorite_new_returns_201_created(self, client, fav_repo):
        _add_fav(fav_repo, "h-1", title="AI news")
        body = {
            "source_type": "favorite",
            "source_id": "h-1",
            "title": "ignored by snapshot",  # 实际会被 favorites 快照覆盖
            "deadline": "2026-07-10",  # 未来某天, 触发有效 urgent 判断
            "important": 1,
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert data["item"]["source_type"] == "favorite"
        assert data["item"]["source_id"] == "h-1"
        assert data["item"]["title"] == "AI news"  # 来自 favorites 快照
        assert data["item"]["deadline"] == "2026-07-10"
        assert data["item"]["important"] == 1
        assert data["item"]["status"] == "open"
        assert data["item"]["completed_at"] is None
        assert data["item"]["archived_at"] is None

    def test_post_favorite_duplicate_returns_200_created_false(self, client, fav_repo):
        _add_fav(fav_repo, "h-dup", title="dup")
        body = {"source_type": "favorite", "source_id": "h-dup", "title": "x"}
        r1 = client.post("/api/todos", json=body)
        r2 = client.post("/api/todos", json=body)
        assert r1.status_code == 201
        assert r2.status_code == 200
        d1 = r1.json()
        d2 = r2.json()
        assert d1["created"] is True
        assert d2["created"] is False
        assert d1["item"]["id"] == d2["item"]["id"]  # 同一行

    def test_post_manual_returns_201(self, client):
        body = {
            "source_type": "manual",
            "title": "周会",
            "deadline": "2026-07-10",  # 未来, 触发 urgent
            "important": 0,
            "note": "周一下午",
        }
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert data["item"]["source_type"] == "manual"
        assert data["item"]["source_id"] is None
        assert data["item"]["title"] == "周会"
        assert data["item"]["deadline"] == "2026-07-10"
        assert data["item"]["important"] == 0
        assert data["item"]["note"] == "周一下午"

    def test_post_missing_title_400(self, client):
        body = {"source_type": "manual"}
        resp = client.post("/api/todos", json=body)
        # pydantic 校验缺失字段 → 422
        assert resp.status_code in (400, 422)

    def test_post_invalid_source_type_400(self, client):
        body = {"source_type": "nonsense", "title": "x"}
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 400

    def test_post_favorite_missing_source_id_400(self, client):
        body = {"source_type": "favorite", "title": "x"}
        resp = client.post("/api/todos", json=body)
        assert resp.status_code == 400


# ===========================================================================
# 2. PATCH /api/todos/{id}
# ===========================================================================
class TestTodosAPIPatch:
    def test_patch_status_open_to_done_fills_completed_at(self, client):
        # 先建一个
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]

        resp = client.patch(
            f"/api/todos/{todo_id}", json={"status": "done"},
        )
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert item["status"] == "done"
        assert item["completed_at"] is not None
        assert item["archived_at"] is None

    def test_patch_status_done_to_archived_fills_archived_at(self, client):
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]
        client.patch(f"/api/todos/{todo_id}", json={"status": "done"})
        resp = client.patch(f"/api/todos/{todo_id}", json={"status": "archived"})
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert item["status"] == "archived"
        assert item["archived_at"] is not None
        # completed_at 保留
        assert item["completed_at"] is not None

    def test_patch_status_archived_to_open_clears_timestamps(self, client):
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]
        client.patch(f"/api/todos/{todo_id}", json={"status": "done"})
        client.patch(f"/api/todos/{todo_id}", json={"status": "archived"})
        resp = client.patch(f"/api/todos/{todo_id}", json={"status": "open"})
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert item["status"] == "open"
        assert item["completed_at"] is None
        assert item["archived_at"] is None

    def test_patch_404(self, client):
        resp = client.patch("/api/todos/9999", json={"status": "done"})
        assert resp.status_code == 404

    def test_patch_priority(self, client):
        """Phase 46: urgent 不再可写, 但 deadline 可写且影响 effective_urgent。"""
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]
        # 通过 deadline = 明天 触发 urgent
        resp = client.patch(
            f"/api/todos/{todo_id}",
            json={"deadline": "2026-07-10", "important": 1},
        )
        assert resp.status_code == 200
        item = resp.json()["item"]
        assert item["important"] == 1
        assert item["deadline"] == "2026-07-10"
        # effective_urgent 由 deadline 派生
        assert item["urgent"] == 1  # 明天 = 1 业务日 = urgent

    def test_patch_invalid_status_400(self, client):
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]
        resp = client.patch(f"/api/todos/{todo_id}", json={"status": "nonsense"})
        assert resp.status_code == 400


# ===========================================================================
# 3. DELETE /api/todos/{id}
# ===========================================================================
class TestTodosAPIDelete:
    def test_delete_returns_204(self, client):
        create = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "t"},
        )
        todo_id = create.json()["item"]["id"]
        resp = client.delete(f"/api/todos/{todo_id}")
        assert resp.status_code == 204
        # 二次确认 GET 已无此 id
        list_resp = client.get("/api/todos")
        ids = [it["id"] for it in list_resp.json()["items"]]
        assert todo_id not in ids

    def test_delete_nonexistent_idempotent_204(self, client):
        # 不存在也返回 204, 保持幂等
        resp = client.delete("/api/todos/9999")
        assert resp.status_code == 204


# ===========================================================================
# 4. GET /api/todos — 多维筛选
# ===========================================================================
class TestTodosAPIList:
    def _seed(self, client, fav_repo):
        # 1 个 P0 (紧急+重要) — 用 deadline 触发 urgent
        _add_fav(fav_repo, "h-1", category="ai", title="P0")
        client.post(
            "/api/todos",
            json={"source_type": "favorite", "source_id": "h-1", "title": "P0",
                  "deadline": "2026-07-10", "important": 1},  # 明天 = 紧急
        )
        # 1 个 P1 (仅紧急)
        client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "P1",
                  "deadline": "2026-07-10"},  # 明天 = 紧急
        )
        # 1 个 P2 (仅重要) — deadline 在 3 天后, 不紧急
        client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "P2",
                  "deadline": "2026-07-15", "important": 1},  # 3 天后 = 不紧急
        )
        # 1 个 P3 (都不) → 标 done
        r = client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "P3"},
        )
        client.patch(f"/api/todos/{r.json()['item']['id']}", json={"status": "done"})

    def test_list_no_filter(self, client, fav_repo):
        self._seed(client, fav_repo)
        resp = client.get("/api/todos")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.2.0"
        assert data["total"] == 4
        assert len(data["items"]) == 4

    def test_list_filter_status_done(self, client, fav_repo):
        self._seed(client, fav_repo)
        resp = client.get("/api/todos", params={"status": "done"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert all(it["status"] == "done" for it in data["items"])

    def test_list_filter_urgent_and_important(self, client, fav_repo):
        self._seed(client, fav_repo)
        resp = client.get(
            "/api/todos", params={"urgent": 1, "important": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        # P0 (紧急+重要 open) + P1 (urgent=1) → only P0
        assert data["total"] == 1
        assert data["items"][0]["urgent"] == 1
        assert data["items"][0]["important"] == 1

    def test_list_filter_combined(self, client, fav_repo):
        self._seed(client, fav_repo)
        resp = client.get(
            "/api/todos", params={"status": "open", "urgent": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        # open + urgent=1: P0 + P1
        assert data["total"] == 2
        for it in data["items"]:
            assert it["status"] == "open"
            assert it["urgent"] == 1

    def test_list_invalid_status_400(self, client):
        resp = client.get("/api/todos", params={"status": "nonsense"})
        assert resp.status_code == 400


# ===========================================================================
# 5. GET /api/todos/count
# ===========================================================================
class TestTodosAPICount:
    def test_count_empty(self, client):
        resp = client.get("/api/todos/count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["by_status"] == {"open": 0, "done": 0, "archived": 0}
        assert data["by_priority"] == {
            "urgent_important": 0,
            "urgent_only": 0,
            "important_only": 0,
            "neither": 0,
        }

    def test_count_after_inserts(self, client, fav_repo):
        # 1 P0 — 明天 deadline + important=1 → urgent_important
        _add_fav(fav_repo, "h-1", title="P0")
        client.post(
            "/api/todos",
            json={"source_type": "favorite", "source_id": "h-1", "title": "P0",
                  "deadline": "2026-07-10", "important": 1},
        )
        # 1 P3 manual (no deadline, no important)
        client.post(
            "/api/todos",
            json={"source_type": "manual", "title": "P3"},
        )
        resp = client.get("/api/todos/count")
        data = resp.json()
        assert data["total"] == 2
        assert data["by_status"]["open"] == 2
        assert data["by_priority"]["urgent_important"] == 1
        assert data["by_priority"]["neither"] == 1


# ===========================================================================
# 6. GET /api/todos/available_favorites
# ===========================================================================
class TestTodosAPIAvailableFavorites:
    def test_excludes_already_in_todo(self, client, fav_repo):
        # 收藏 3 个
        for i in range(1, 4):
            _add_fav(fav_repo, f"h-{i}", category="ai", title=f"T{i}")
        # 1 个入 todo
        client.post(
            "/api/todos",
            json={"source_type": "favorite", "source_id": "h-2", "title": "ignored"},
        )
        resp = client.get("/api/todos/available_favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        ids = {it["hotspot_id"] for it in data["items"]}
        assert ids == {"h-1", "h-3"}

    def test_empty_when_all_in_todo(self, client, fav_repo):
        for i in range(1, 4):
            _add_fav(fav_repo, f"h-{i}", category="ai", title=f"T{i}")
            client.post(
                "/api/todos",
                json={"source_type": "favorite", "source_id": f"h-{i}", "title": "x"},
            )
        resp = client.get("/api/todos/available_favorites")
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_empty_when_no_favorites(self, client):
        resp = client.get("/api/todos/available_favorites")
        data = resp.json()
        assert data["total"] == 0


# ===========================================================================
# 7. 综合: trace_id + 错误格式
# ===========================================================================
class TestTodosAPIErrors:
    def test_trace_id_injected(self, client):
        resp = client.get("/api/todos/count")
        assert "X-Trace-Id" in resp.headers
        assert len(resp.headers["X-Trace-Id"]) > 0

    def test_post_empty_title_rejected(self, client):
        # title 至少 1 字符, 空字符串 pydantic 应拦
        body = {"source_type": "manual", "title": ""}
        resp = client.post("/api/todos", json=body)
        assert resp.status_code in (400, 422)
