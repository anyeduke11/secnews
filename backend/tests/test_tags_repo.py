"""TagRepository 单元测试 — tags CRUD + hotspot_tags 关联 + AND/OR 过滤.

测试隔离: tmp_path + monkeypatch config.db_path.
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.tags_repo import TagRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_tags.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db):
    return TagRepository()


@pytest.fixture
def hotspot_repo(temp_db):
    return HotspotRepository()


def _make_hotspot(hid: str) -> HotspotItem:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid,
        title=f"Test {hid}",
        source="test",
        url=f"https://example.com/{hid}",
        category=Category.AI,
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        ingested_at=now,
        summary="test summary",
    )


class TestTagCRUD:
    def test_add_and_get_tag(self, repo):
        """Step 1: 基础 add + get."""
        tag = repo.add("ai-security", "AI安全", "domain")
        assert tag.id == "ai-security"
        assert tag.label == "AI安全"
        assert tag.type == "domain"
        fetched = repo.get("ai-security")
        assert fetched is not None
        assert fetched.label == "AI安全"

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get("nonexistent") is None

    def test_add_replaces_existing(self, repo):
        """INSERT OR REPLACE: 重新 add 同 id 会覆盖."""
        repo.add("x", "X", "domain", weight=1.0)
        repo.add("x", "X-updated", "domain", weight=2.0)
        tag = repo.get("x")
        assert tag is not None
        assert tag.label == "X-updated"
        assert tag.weight == 2.0

    def test_list_by_type(self, repo):
        repo.add("t1", "Tag1", "domain")
        repo.add("t2", "Tag2", "technique")
        repo.add("t3", "Tag3", "domain")
        domain_tags = repo.list(type="domain")
        # 含种子标签, 至少 3 个 domain
        ids = {t.id for t in domain_tags}
        assert "t1" in ids
        assert "t3" in ids
        assert "t2" not in ids

    def test_list_by_parent(self, repo):
        repo.add("parent", "Parent", "domain")
        repo.add("child1", "Child1", "domain", parent_id="parent")
        repo.add("child2", "Child2", "domain", parent_id="parent")
        children = repo.list(parent_id="parent")
        ids = {t.id for t in children}
        assert ids == {"child1", "child2"}

    def test_suggest(self, repo):
        repo.add("langchain-xyz", "LangChain XYZ", "framework")
        results = repo.suggest("langchain")
        ids = {t.id for t in results}
        assert "langchain-xyz" in ids
        # 种子标签 langchain 也应命中
        assert "langchain" in ids

    def test_delete(self, repo):
        repo.add("todelete", "ToDelete", "domain")
        assert repo.delete("todelete") is True
        assert repo.get("todelete") is None
        assert repo.delete("todelete") is False  # already gone


class TestHotspotTagsAssociation:
    def test_attach_and_list_by_hotspot(self, repo, hotspot_repo):
        hotspot_repo.upsert_many([_make_hotspot("h1")])
        repo.add("tag-a", "Tag A", "domain")
        repo.add("tag-b", "Tag B", "technique")
        repo.attach("h1", "tag-a", confidence=0.9)
        repo.attach("h1", "tag-b")
        tags = repo.list_by_hotspot("h1")
        ids = {t.id for t in tags}
        assert ids == {"tag-a", "tag-b"}

    def test_attach_idempotent_updates_confidence(self, repo, hotspot_repo):
        hotspot_repo.upsert_many([_make_hotspot("h2")])
        repo.add("tag-x", "Tag X", "domain")
        repo.attach("h2", "tag-x", confidence=0.5)
        repo.attach("h2", "tag-x", confidence=0.95)
        # 应只有一条关联, confidence 为最新值
        from backend.repository.db import get_connection

        row = get_connection().execute(
            "SELECT confidence FROM hotspot_tags WHERE hotspot_id=? AND tag_id=?",
            ("h2", "tag-x"),
        ).fetchone()
        assert row is not None
        assert row[0] == 0.95

    def test_detach(self, repo, hotspot_repo):
        hotspot_repo.upsert_many([_make_hotspot("h3")])
        repo.add("tag-y", "Tag Y", "domain")
        repo.attach("h3", "tag-y")
        assert len(repo.list_by_hotspot("h3")) == 1
        repo.detach("h3", "tag-y")
        assert len(repo.list_by_hotspot("h3")) == 0

    def test_list_hotspot_ids_by_tags_or(self, repo, hotspot_repo):
        """OR 模式: 拥有任一标签的热点都返回."""
        for hid in ("h-or-1", "h-or-2", "h-or-3"):
            hotspot_repo.upsert_many([_make_hotspot(hid)])
        repo.add("o1", "O1", "domain")
        repo.add("o2", "O2", "domain")
        repo.attach("h-or-1", "o1")
        repo.attach("h-or-2", "o2")
        # h-or-3 无标签
        ids = set(repo.list_hotspot_ids_by_tags(["o1", "o2"], mode="or"))
        assert ids == {"h-or-1", "h-or-2"}

    def test_list_hotspot_ids_by_tags_and(self, repo, hotspot_repo):
        """AND 模式: 必须拥有全部标签."""
        for hid in ("h-and-1", "h-and-2"):
            hotspot_repo.upsert_many([_make_hotspot(hid)])
        repo.add("a1", "A1", "domain")
        repo.add("a2", "A2", "domain")
        repo.attach("h-and-1", "a1")
        repo.attach("h-and-1", "a2")
        repo.attach("h-and-2", "a1")  # 只有一个
        ids = set(repo.list_hotspot_ids_by_tags(["a1", "a2"], mode="and"))
        assert ids == {"h-and-1"}

    def test_list_hotspot_ids_empty_tags(self, repo):
        assert repo.list_hotspot_ids_by_tags([], mode="or") == []
