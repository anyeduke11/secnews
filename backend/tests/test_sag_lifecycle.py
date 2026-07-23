"""v1.7 Phase 1 — SAG lifecycle 服务测试。

覆盖:
- transition: 合法推进 signal → amplify:tagged → ... → generate
- transition: 非法状态拒绝
- transition: 回退拒绝 (单调性)
- transition: 不存在条目 / 幂等
- promote_favorite_to_knowledge: 新建 lifecycle=signal 条目
- promote_favorite_to_knowledge: 同 url 幂等 (不覆盖)
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository import db
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync, sag_service


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_sag.db"
    monkeypatch.setattr(config, "db_path", test_db)
    # 重定向 .md 写入到 tmp_path, 避免污染真实 knowledge/items/
    fake_items = tmp_path / "items"
    fake_items.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", fake_items)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _make_item(item_id: str, lifecycle: str = "signal") -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title=f"Item {item_id}",
        source="test",
        lifecycle=lifecycle,
        ingested_at=now_iso(),
        updated_at=now_iso(),
    )


class TestTransition:
    def test_valid_forward_transition(self, temp_db):
        knowledge_repo.upsert_item(_make_item("t1", "signal"))
        assert sag_service.transition("t1", "amplify:tagged") is True
        assert knowledge_repo.get_item("t1").lifecycle == "amplify:tagged"

    def test_skip_forward_transition_allowed(self, temp_db):
        """允许跳跃: signal → generate 直接归档。"""
        knowledge_repo.upsert_item(_make_item("t2", "signal"))
        assert sag_service.transition("t2", "generate") is True
        assert knowledge_repo.get_item("t2").lifecycle == "generate"

    def test_reject_invalid_state(self, temp_db):
        knowledge_repo.upsert_item(_make_item("t3", "signal"))
        assert sag_service.transition("t3", "bogus-state") is False
        # 原状态不变
        assert knowledge_repo.get_item("t3").lifecycle == "signal"

    def test_reject_regression(self, temp_db):
        """不允许回退: amplify:tagged → signal 拒绝。"""
        knowledge_repo.upsert_item(_make_item("t4", "amplify:tagged"))
        assert sag_service.transition("t4", "signal") is False
        assert knowledge_repo.get_item("t4").lifecycle == "amplify:tagged"

    def test_idempotent_same_state(self, temp_db):
        knowledge_repo.upsert_item(_make_item("t5", "amplify:tagged"))
        assert sag_service.transition("t5", "amplify:tagged") is True
        assert knowledge_repo.get_item("t5").lifecycle == "amplify:tagged"

    def test_missing_item_returns_false(self, temp_db):
        assert sag_service.transition("no-such", "generate") is False


class TestPromoteFavorite:
    def test_creates_signal_item(self, temp_db):
        item_id = sag_service.promote_favorite_to_knowledge(
            "Fav Title", "https://example.com/fav-1"
        )
        assert item_id  # 非空
        item = knowledge_repo.get_item(item_id)
        assert item is not None
        assert item.lifecycle == "signal"  # 验收 3
        assert item.source == "secnews"
        assert item.title == "Fav Title"

    def test_idempotent_same_url(self, temp_db):
        id1 = sag_service.promote_favorite_to_knowledge(
            "Title A", "https://example.com/fav-2"
        )
        # 同 url 第二次: 不覆盖, 返回同一 id
        id2 = sag_service.promote_favorite_to_knowledge(
            "Title B (different)", "https://example.com/fav-2"
        )
        assert id1 == id2
        item = knowledge_repo.get_item(id1)
        assert item.title == "Title A"  # 未被覆盖

    def test_compiled_backward_compat(self, temp_db):
        """新建条目 compiled property 应为 False (signal 状态)。"""
        item_id = sag_service.promote_favorite_to_knowledge(
            "T", "https://example.com/fav-3"
        )
        item = knowledge_repo.get_item(item_id)
        assert item.compiled is False  # signal → compiled=False
        # 推进到 generate 后 compiled 应为 True
        sag_service.transition(item_id, "generate")
        assert knowledge_repo.get_item(item_id).compiled is True
