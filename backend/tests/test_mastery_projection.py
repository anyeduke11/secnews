"""v0.6 Phase 5 — Mastery projection 测试 (S5-1/S5-2 闭合).

覆盖:
- compute_mastery: 公式 (min(100, repetitions*20 + easiness*4))
- project_review_to_wiki: last_reviewed_at → md frontmatter (Bugfix 验证)
- project_review_to_wiki: review_count → md frontmatter (S5-2 闭合)
- project_review_to_wiki: 非 knowledge_item 实体跳过
- project_review_to_wiki: 找不到 item 静默跳过
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services import mastery_projection


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mastery.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def temp_knowledge_dir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把 knowledge/items/ 重定向到临时目录, 不污染真实 wiki。"""
    items_dir = tmp_path / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "backend.services.knowledge_sync.ITEMS_DIR", items_dir
    )
    yield items_dir


def _insert_item(item_id: str, mastery: int = 0) -> None:
    """在测试 DB 中插入一个 knowledge_item, 用于投影目标。"""
    from backend.domain.knowledge_models import KnowledgeItem
    from backend.repository.knowledge_repo import knowledge_repo

    item = KnowledgeItem(
        id=item_id,
        title=f"Item {item_id}",
        source="test",
        source_url=None,
        domain="test",
        topic="t",
        type="news",
        difficulty="beginner",
        tags=[],
        concepts=[],
        mastery=mastery,
        lifecycle="kl:raw",
        news_type=None,
        tech_stack=[],
        ingested_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    knowledge_repo.upsert_item(item)


# ===========================================================================
# 1. compute_mastery 纯函数
# ===========================================================================
class TestComputeMastery:
    def test_formula_basic(self):
        """repetitions=0, easiness=2.5 → 0*20 + 2.5*4 = 10。"""
        assert mastery_projection.compute_mastery(2.5, 0) == 10

    def test_formula_repeated(self):
        """repetitions=3, easiness=2.5 → 3*20 + 2.5*4 = 70。"""
        assert mastery_projection.compute_mastery(2.5, 3) == 70

    def test_capped_at_100(self):
        """repetitions=10, easiness=2.5 → 200+10=210 → 截断到 100。"""
        assert mastery_projection.compute_mastery(2.5, 10) == 100


# ===========================================================================
# 2. project_review_to_wiki 写盘验证 (S5-2)
# ===========================================================================
class TestProjectReviewToWiki:
    def test_non_knowledge_item_skipped(self, temp_db):
        """entity_type != 'knowledge_item' 直接 False, 不写盘。"""
        result = mastery_projection.project_review_to_wiki(
            entity_type="hotspot",
            entity_id="x",
            easiness=2.5,
            repetitions=1,
            last_reviewed="2026-08-27T00:00:00+00:00",
            review_count=1,
        )
        assert result is False

    def test_missing_item_skipped(self, temp_db, temp_knowledge_dir):
        """item 不存在 → False, 不抛异常。"""
        result = mastery_projection.project_review_to_wiki(
            entity_type="knowledge_item",
            entity_id="nonexistent",
            easiness=2.5,
            repetitions=1,
            last_reviewed="2026-08-27T00:00:00+00:00",
            review_count=1,
        )
        assert result is False

    def test_writes_frontmatter_with_review_meta(
        self, temp_db, temp_knowledge_dir
    ):
        """Bugfix: last_reviewed_at 字段被正确写入 md frontmatter。

        历史 bug: api/reviews.py:60 用 row.get("last_reviewed") 拿 None,
        落到 md 是 last_reviewed: null。本测试确认用 last_reviewed_at 字段
        修复后, 真值能正确落盘。
        """
        _insert_item("test-1", mastery=10)
        result = mastery_projection.project_review_to_wiki(
            entity_type="knowledge_item",
            entity_id="test-1",
            easiness=2.5,
            repetitions=2,
            last_reviewed="2026-08-27T12:34:56+00:00",
            review_count=3,
        )
        assert result is True

        md_path = temp_knowledge_dir / "test-1.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")

        # mastery 由公式: 2*20 + 2.5*4 = 50
        assert "mastery: 50" in content
        # last_reviewed 真值写入 (修复前是 null)
        assert "last_reviewed: 2026-08-27T12:34:56+00:00" in content
        # review_count 真值写入 (S5-2 闭合, 修复前继承 existing_fm)
        assert "review_count: 3" in content

    def test_overrides_existing_review_count(
        self, temp_db, temp_knowledge_dir
    ):
        """S5-2 闭合: 多次评分, review_count 覆盖而非保留旧值。"""
        _insert_item("test-2", mastery=0)
        # 首次评分 → review_count=1
        mastery_projection.project_review_to_wiki(
            entity_type="knowledge_item",
            entity_id="test-2",
            easiness=2.5,
            repetitions=1,
            last_reviewed="2026-08-26T00:00:00+00:00",
            review_count=1,
        )
        # 二次评分 → review_count=2 (覆盖, 不是保留 1)
        mastery_projection.project_review_to_wiki(
            entity_type="knowledge_item",
            entity_id="test-2",
            easiness=2.5,
            repetitions=2,
            last_reviewed="2026-08-27T00:00:00+00:00",
            review_count=2,
        )

        content = (temp_knowledge_dir / "test-2.md").read_text(encoding="utf-8")
        assert "review_count: 2" in content
        assert "last_reviewed: 2026-08-27T00:00:00+00:00" in content
