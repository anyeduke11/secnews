"""P3 重构 — knowledge 真相源统一 (md = source of truth, SQLite = 可重建索引)。

覆盖:
- write_item_to_md: 保留 md-only frontmatter 字段 (sources/last_reviewed/...)
- write_item_to_md: 正文不重复写入 (回归: 模板内嵌 body + 拼接 body 翻倍 bug)
- full_sync_items_to_db / full_sync_concepts_to_db: 孤儿行清理 + 空目录保护
- sag_service.transition: md 写失败 → 整个 transition 失败, DB 不动
- update_md_frontmatter_field: 就地改单字段
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.domain.knowledge_models import KnowledgeConcept, KnowledgeItem, now_iso
from backend.repository import db
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync, sag_service
from backend.services.knowledge_sync import (
    full_sync_concepts_to_db,
    full_sync_items_to_db,
    update_md_frontmatter_field,
    write_item_to_md,
)


@pytest.fixture
def temp_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """独立 DB + 重定向 items/concepts 目录到 tmp_path。"""
    test_db = tmp_path / "test_truth.db"
    monkeypatch.setattr(config, "db_path", test_db)
    items_dir = tmp_path / "items"
    concepts_dir = tmp_path / "concepts"
    items_dir.mkdir()
    concepts_dir.mkdir()
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", items_dir)
    monkeypatch.setattr(knowledge_sync, "CONCEPTS_DIR", concepts_dir)
    db.close_db()
    db.init_db()
    yield {"items": items_dir, "concepts": concepts_dir}
    db.close_db()


def _make_item(item_id: str, **kw) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title=kw.get("title", f"Item {item_id}"),
        source="test",
        lifecycle=kw.get("lifecycle", "signal"),
        ingested_at=now_iso(),
        updated_at=now_iso(),
    )


class TestWriteItemToMd:
    def test_preserves_md_only_fields(self, temp_env):
        """DB→md 回写不重置 sources/last_reviewed/review_count/related_items。"""
        path = temp_env["items"] / "i1.md"
        path.write_text(
            "---\n"
            'id: "i1"\n'
            'title: "Old"\n'
            "mastery: 10\n"
            'last_reviewed: "2026-07-01"\n'
            "review_count: 3\n"
            'related_items: ["x", "y"]\n'
            'sources: ["cubox"]\n'
            "---\n\nbody text\n",
            encoding="utf-8",
        )
        write_item_to_md(_make_item("i1", title="New").to_dict())
        text = path.read_text(encoding="utf-8")
        assert 'title: "New"' in text
        assert "last_reviewed: 2026-07-01" in text
        assert "review_count: 3" in text
        assert '"x"' in text and '"y"' in text
        assert 'sources: ["cubox"]' in text
        assert "body text" in text

    def test_body_not_duplicated(self, temp_env):
        """回归: 旧实现 frontmatter 模板内嵌 body 后又拼接 body → 正文翻倍。"""
        write_item_to_md(_make_item("i2").to_dict(), content="UNIQUE_BODY_MARK\n")
        # 第二次回写 (保留正文)
        write_item_to_md(_make_item("i2", title="v2").to_dict())
        text = (temp_env["items"] / "i2.md").read_text(encoding="utf-8")
        assert text.count("UNIQUE_BODY_MARK") == 1


class TestFullSyncOrphanCleanup:
    def test_items_orphan_rows_removed(self, temp_env):
        """md 已删除的 DB 行在 full_sync 时被清理。"""
        (temp_env["items"] / "keep.md").write_text(
            '---\nid: "keep"\ntitle: "Keep"\n---\n\nbody\n', encoding="utf-8"
        )
        knowledge_repo.upsert_item(_make_item("keep"))
        knowledge_repo.upsert_item(_make_item("orphan"))
        count = full_sync_items_to_db()
        assert count == 1
        assert knowledge_repo.get_item("keep") is not None
        assert knowledge_repo.get_item("orphan") is None

    def test_items_empty_dir_no_wipe(self, temp_env):
        """目录为空 (可能是挂载/权限异常) → 不清空索引。"""
        knowledge_repo.upsert_item(_make_item("survivor"))
        count = full_sync_items_to_db()
        assert count == 0
        assert knowledge_repo.get_item("survivor") is not None

    def test_concepts_orphan_rows_removed(self, temp_env):
        (temp_env["concepts"] / "c-keep.md").write_text(
            '---\nslug: "c-keep"\ntitle: "CKeep"\n---\n\nbody\n', encoding="utf-8"
        )
        knowledge_repo.upsert_concept(KnowledgeConcept(
            slug="c-keep", title="CKeep", updated_at=now_iso(),
        ))
        knowledge_repo.upsert_concept(KnowledgeConcept(
            slug="c-orphan", title="COrphan", updated_at=now_iso(),
        ))
        count = full_sync_concepts_to_db()
        assert count == 1
        assert knowledge_repo.get_concept("c-keep") is not None
        assert knowledge_repo.get_concept("c-orphan") is None


class TestTransitionMdFirst:
    def test_md_write_failure_aborts_transition(self, temp_env, monkeypatch):
        """md 是真相源: md 写失败 → transition 返回 False 且 DB lifecycle 不变。"""
        knowledge_repo.upsert_item(_make_item("t1", lifecycle="signal"))

        def _boom(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(knowledge_sync, "write_item_to_md", _boom)
        assert sag_service.transition("t1", "generate") is False
        assert knowledge_repo.get_item("t1").lifecycle == "signal"

    def test_md_write_success_updates_both(self, temp_env):
        knowledge_repo.upsert_item(_make_item("t2", lifecycle="signal"))
        assert sag_service.transition("t2", "generate") is True
        assert knowledge_repo.get_item("t2").lifecycle == "generate"
        md = (temp_env["items"] / "t2.md").read_text(encoding="utf-8")
        assert 'lifecycle: "generate"' in md


class TestUpdateMdFrontmatterField:
    def test_replaces_existing_key(self, tmp_path):
        p = tmp_path / "c.md"
        p.write_text(
            '---\nslug: "c"\nlocal_wiki_ref: null\n---\n\nbody\n', encoding="utf-8"
        )
        assert update_md_frontmatter_field(p, "local_wiki_ref", "wiki:local:concepts/c")
        text = p.read_text(encoding="utf-8")
        assert 'local_wiki_ref: "wiki:local:concepts/c"' in text
        assert "body" in text

    def test_adds_missing_key(self, tmp_path):
        p = tmp_path / "c.md"
        p.write_text('---\nslug: "c"\n---\n\nbody\n', encoding="utf-8")
        assert update_md_frontmatter_field(p, "local_wiki_ref", "ref-1")
        assert 'local_wiki_ref: "ref-1"' in p.read_text(encoding="utf-8")

    def test_no_frontmatter_returns_false(self, tmp_path):
        p = tmp_path / "plain.md"
        p.write_text("just body\n", encoding="utf-8")
        assert update_md_frontmatter_field(p, "k", "v") is False

    def test_missing_file_returns_false(self, tmp_path):
        assert update_md_frontmatter_field(tmp_path / "nope.md", "k", "v") is False
