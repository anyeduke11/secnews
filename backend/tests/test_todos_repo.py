"""Phase 36 待办 (Todos) 仓库 + API 测试

覆盖范围:
  - TodoRepository 单元
    * add_or_get 新建 / 重复 favorite-source 幂等 / manual
    * list 多维筛选 (status/urgent/important) + 排序
    * count by_status / by_priority 4 象限
    * update priority (urgent/important)
    * update status 状态迁移 (open→done→archived→open)
    * delete
    * list_available_favorites 排除已入 todo
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
    test_db = tmp_path / "test_todos.db"
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


# ===========================================================================
# 1. TodoRepository.add_or_get
# ===========================================================================
class TestTodoRepoAddOrGet:
    def test_add_manual_new_created_true(self, todo_repo):
        item, created = todo_repo.add_or_get(
            source_type="manual",
            source_id=None,
            title="开周会",
            url=None,
            source=None,
            category=None,
            urgent=0,
            important=0,
            note="周一上午",
        )
        assert created is True
        assert item.id > 0
        assert item.source_type == "manual"
        assert item.source_id is None
        assert item.title == "开周会"
        assert item.urgent == 0
        assert item.important == 0
        assert item.status == "open"
        assert item.completed_at is None
        assert item.archived_at is None
        assert item.created_at  # ISO 字符串

    def test_add_manual_with_urgent_important(self, todo_repo):
        item, created = todo_repo.add_or_get(
            source_type="manual",
            source_id=None,
            title="P0 任务",
            url=None,
            source=None,
            category=None,
            urgent=1,
            important=1,
            note=None,
        )
        assert created is True
        assert item.urgent == 1
        assert item.important == 1

    def test_add_favorite_new(self, todo_repo, fav_repo):
        # 先在 favorites 表创建一条
        fav_repo.add(
            hotspot_id="h-1",
            category="ai",
            title="AI breakthrough",
            source="src",
            url="https://e.com/1",
        )
        item, created = todo_repo.add_or_get(
            source_type="favorite",
            source_id="h-1",
            title="ignored by snapshot",
            url="ignored",
            source="ignored",
            category="ignored",
            urgent=1,
            important=0,
            note="n",
        )
        assert created is True
        assert item.source_type == "favorite"
        assert item.source_id == "h-1"
        # 来自 favorites 快照
        assert item.title == "AI breakthrough"
        assert item.url == "https://e.com/1"
        assert item.source == "src"
        assert item.category == "ai"

    def test_add_favorite_duplicate_idempotent(self, todo_repo, fav_repo):
        fav_repo.add(
            hotspot_id="h-dup",
            category="ai",
            title="first",
            source="s1",
            url="https://e.com/dup",
        )
        first, c1 = todo_repo.add_or_get(
            source_type="favorite",
            source_id="h-dup",
            title="x", url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        second, c2 = todo_repo.add_or_get(
            source_type="favorite",
            source_id="h-dup",
            title="x", url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        assert c1 is True
        assert c2 is False
        assert first.id == second.id  # 同一行
        assert second.title == "first"  # 原值不被覆盖

    def test_add_manual_does_not_have_source_id(self, todo_repo):
        # 即便传了 source_id, manual 路径下也应置空
        item, _ = todo_repo.add_or_get(
            source_type="manual",
            source_id="should-be-dropped",
            title="t", url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        assert item.source_id is None

    def test_add_favorite_without_source_id_raises(self, todo_repo):
        with pytest.raises(Exception):
            todo_repo.add_or_get(
                source_type="favorite",
                source_id="",
                title="t", url=None, source=None, category=None,
                urgent=0, important=0, note=None,
            )

    def test_add_invalid_source_type_raises(self, todo_repo):
        with pytest.raises(Exception):
            todo_repo.add_or_get(
                source_type="nonsense",
                source_id="x",
                title="t", url=None, source=None, category=None,
                urgent=0, important=0, note=None,
            )

    def test_add_empty_title_raises(self, todo_repo):
        with pytest.raises(Exception):
            todo_repo.add_or_get(
                source_type="manual",
                source_id=None,
                title="", url=None, source=None, category=None,
                urgent=0, important=0, note=None,
            )


# ===========================================================================
# 2. TodoRepository.list — 多维筛选 + 排序
# ===========================================================================
class TestTodoRepoList:
    def _seed(self, todo_repo, fav_repo):
        """3 个 todo: 1 紧急+重要, 1 仅紧急, 1 仅重要; 第二个标 done。"""
        fav_repo.add(
            hotspot_id="h-1", category="ai", title="T1",
            source="s", url="https://e.com/1",
        )
        a, _ = todo_repo.add_or_get(
            source_type="favorite", source_id="h-1",
            title="ignored", url=None, source=None, category=None,
            urgent=1, important=1, note=None,
        )
        b, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None,
            title="M2", url=None, source=None, category=None,
            urgent=1, important=0, note=None,
        )
        c, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None,
            title="M3", url=None, source=None, category=None,
            urgent=0, important=1, note=None,
        )
        # 第二个标 done
        todo_repo.update(b.id, status="done")
        return a, b, c

    def test_list_all(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list()
        assert total == 3
        assert len(items) == 3

    def test_list_filter_status_done(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list(status="done")
        assert total == 1
        assert items[0].status == "done"

    def test_list_filter_status_open(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list(status="open")
        assert total == 2
        for it in items:
            assert it.status == "open"

    def test_list_filter_urgent(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list(urgent=1)
        assert total == 2  # a 和 b

    def test_list_filter_important(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list(important=1)
        assert total == 2  # a 和 c

    def test_list_combined_status_and_urgent(self, todo_repo, fav_repo):
        self._seed(todo_repo, fav_repo)
        items, total = todo_repo.list(status="open", urgent=1)
        # open + urgent=1: 只有 a
        assert total == 1
        assert items[0].id == next(
            x.id for x in [self._seed(todo_repo, fav_repo)[0]] if x.urgent == 1
        ) if False else items[0].urgent == 1

    def test_list_sort_priority_desc(self, todo_repo, fav_repo):
        a, _, _ = self._seed(todo_repo, fav_repo)
        items, _ = todo_repo.list()
        # 排序: urgent DESC → important DESC → created_at DESC
        # a: 1,1 / b: 1,0 / c: 0,1 → a 第一
        assert items[0].id == a.id

    def test_list_empty(self, todo_repo):
        items, total = todo_repo.list()
        assert total == 0
        assert items == []


# ===========================================================================
# 3. TodoRepository.count
# ===========================================================================
class TestTodoRepoCount:
    def test_count_empty(self, todo_repo):
        c = todo_repo.count()
        assert c["total"] == 0
        assert c["by_status"] == {"open": 0, "done": 0, "archived": 0}
        assert c["by_priority"] == {
            "urgent_important": 0,
            "urgent_only": 0,
            "important_only": 0,
            "neither": 0,
        }

    def test_count_after_mixed_inserts(self, todo_repo, fav_repo):
        # P0: 紧急+重要 (open)
        todo_repo.add_or_get(
            source_type="manual", source_id=None, title="p0",
            url=None, source=None, category=None,
            urgent=1, important=1, note=None,
        )
        # P1: 仅紧急 (open)
        todo_repo.add_or_get(
            source_type="manual", source_id=None, title="p1",
            url=None, source=None, category=None,
            urgent=1, important=0, note=None,
        )
        # P2: 仅重要 (open)
        todo_repo.add_or_get(
            source_type="manual", source_id=None, title="p2",
            url=None, source=None, category=None,
            urgent=0, important=1, note=None,
        )
        # P3: 都不 (open)
        _, p3 = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="p3",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        # 标 done 一个 P0
        p0, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="p0-2",
            url=None, source=None, category=None,
            urgent=1, important=1, note=None,
        )
        # archived 一个 P3 (不计入 priority)
        todo_repo.add_or_get(
            source_type="manual", source_id=None, title="archived-p3",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        # 把 p0 标 done
        todo_repo.update(p0.id, status="done")
        # 找 archived 项
        items, _ = todo_repo.list()
        for it in items:
            if it.title == "archived-p3":
                todo_repo.update(it.id, status="archived")
                break

        c = todo_repo.count()
        assert c["total"] == 6
        assert c["by_status"]["open"] == 4   # p0, p1, p2, p3
        assert c["by_status"]["done"] == 1   # p0-2
        assert c["by_status"]["archived"] == 1
        # by_priority 只算 open + done (archived 不计入)
        assert c["by_priority"]["urgent_important"] == 2   # p0 + p0-2
        assert c["by_priority"]["urgent_only"] == 1        # p1
        assert c["by_priority"]["important_only"] == 1     # p2
        assert c["by_priority"]["neither"] == 1            # p3
        # archived-p3 不计入 priority


# ===========================================================================
# 4. TodoRepository.update
# ===========================================================================
class TestTodoRepoUpdate:
    def test_update_priority(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=1, note=None,
        )
        updated = todo_repo.update(item.id, urgent=1, important=0)
        assert updated.urgent == 1
        assert updated.important == 0

    def test_update_status_open_to_done_fills_completed_at(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        assert item.completed_at is None
        updated = todo_repo.update(item.id, status="done")
        assert updated.status == "done"
        assert updated.completed_at is not None
        assert updated.archived_at is None

    def test_update_status_done_to_archived_fills_archived_at(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        todo_repo.update(item.id, status="done")
        updated = todo_repo.update(item.id, status="archived")
        assert updated.status == "archived"
        assert updated.archived_at is not None
        # completed_at 应保留 (表示先完成再归档)
        assert updated.completed_at is not None

    def test_update_status_archived_to_open_clears_timestamps(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        todo_repo.update(item.id, status="done")
        todo_repo.update(item.id, status="archived")
        updated = todo_repo.update(item.id, status="open")
        assert updated.status == "open"
        assert updated.completed_at is None
        assert updated.archived_at is None

    def test_update_status_open_to_archived_skips_done(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        updated = todo_repo.update(item.id, status="archived")
        assert updated.status == "archived"
        assert updated.archived_at is not None
        # 没有 done 这一步, completed_at 应为 None
        assert updated.completed_at is None

    def test_update_note(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note="original",
        )
        updated = todo_repo.update(item.id, note="new note")
        assert updated.note == "new note"

    def test_update_nonexistent_raises(self, todo_repo):
        with pytest.raises(Exception):
            todo_repo.update(9999, status="done")


# ===========================================================================
# 5. TodoRepository.delete
# ===========================================================================
class TestTodoRepoDelete:
    def test_delete_existing(self, todo_repo):
        item, _ = todo_repo.add_or_get(
            source_type="manual", source_id=None, title="t",
            url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        assert todo_repo.delete(item.id) is True
        assert todo_repo.get(item.id) is None

    def test_delete_nonexistent_returns_false(self, todo_repo):
        assert todo_repo.delete(99999) is False


# ===========================================================================
# 6. TodoRepository.list_available_favorites
# ===========================================================================
class TestTodoRepoListAvailableFavorites:
    def test_excludes_todo_sources(self, todo_repo, fav_repo):
        # 收藏 3 个
        for i in range(1, 4):
            fav_repo.add(
                hotspot_id=f"h-{i}", category="ai",
                title=f"T{i}", source=f"src{i}",
                url=f"https://e.com/{i}",
            )
        # 1 个进 todo
        todo_repo.add_or_get(
            source_type="favorite", source_id="h-2",
            title="ignored", url=None, source=None, category=None,
            urgent=0, important=0, note=None,
        )
        items = todo_repo.list_available_favorites()
        # 应返回 2 个 (h-1, h-3)
        ids = {it["hotspot_id"] for it in items}
        assert ids == {"h-1", "h-3"}

    def test_empty_when_all_in_todo(self, todo_repo, fav_repo):
        for i in range(1, 4):
            fav_repo.add(
                hotspot_id=f"h-{i}", category="ai",
                title=f"T{i}", source="s", url=f"https://e.com/{i}",
            )
            todo_repo.add_or_get(
                source_type="favorite", source_id=f"h-{i}",
                title="ignored", url=None, source=None, category=None,
                urgent=0, important=0, note=None,
            )
        items = todo_repo.list_available_favorites()
        assert items == []

    def test_empty_when_no_favorites(self, todo_repo):
        items = todo_repo.list_available_favorites()
        assert items == []

    def test_includes_metadata(self, todo_repo, fav_repo):
        fav_repo.add(
            hotspot_id="h-meta", category="bid",
            title="招标标题", source="招标网",
            url="https://e.com/meta",
        )
        items = todo_repo.list_available_favorites()
        assert len(items) == 1
        assert items[0]["hotspot_id"] == "h-meta"
        assert items[0]["title"] == "招标标题"
        assert items[0]["url"] == "https://e.com/meta"
        assert items[0]["source"] == "招标网"
        assert items[0]["category"] == "bid"
