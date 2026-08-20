"""v1.7 Phase 1 — SAG lifecycle 服务测试 (P1-3: KL 五阶段统一)。

覆盖 (P1-3 更新):
- transition: 合法推进 (kl:raw → kl:refine → ... → kl:publish)
- transition: legacy SAG 输入兼容 (signal/amplify:tagged → 归一为 kl:*)
- transition: 非法状态拒绝
- transition: 回退拒绝 (单调性)
- transition: 不存在条目 / 幂等
- promote_favorite_to_knowledge: 新建 lifecycle=kl:raw 条目 (P1-3)
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


def _make_item(item_id: str, lifecycle: str = "kl:raw") -> KnowledgeItem:
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
        """kl:raw → kl:refine 合法推进, 落库为 KL 规范值。"""
        knowledge_repo.upsert_item(_make_item("t1", "kl:raw"))
        assert sag_service.transition("t1", "kl:refine") is True
        assert knowledge_repo.get_item("t1").lifecycle == "kl:refine"

    def test_legacy_input_rejected_after_oneway(self, temp_db):
        """P1.5: 单轨化后 legacy SAG 输入 (amplify:tagged) 不再被接受。

        修复前 (P1-3): legacy 输入兼容, 归一为 kl:*。
        修复后 (P1.5): VALID_LIFECYCLE_STATES 只含 kl:* 状态, legacy 目标拒绝。
        """
        knowledge_repo.upsert_item(_make_item("t1b", "kl:raw"))
        # legacy 目标状态不再合法 → 拒绝
        assert sag_service.transition("t1b", "amplify:tagged") is False
        # 原状态不变
        assert knowledge_repo.get_item("t1b").lifecycle == "kl:raw"

    def test_skip_forward_transition_allowed(self, temp_db):
        """允许跳跃: kl:raw → kl:publish 直接归档。"""
        knowledge_repo.upsert_item(_make_item("t2", "kl:raw"))
        assert sag_service.transition("t2", "kl:publish") is True
        assert knowledge_repo.get_item("t2").lifecycle == "kl:publish"

    def test_reject_invalid_state(self, temp_db):
        knowledge_repo.upsert_item(_make_item("t3", "kl:raw"))
        assert sag_service.transition("t3", "bogus-state") is False
        # 原状态不变
        assert knowledge_repo.get_item("t3").lifecycle == "kl:raw"

    def test_reject_regression(self, temp_db):
        """不允许回退: kl:refine → kl:raw 拒绝。"""
        knowledge_repo.upsert_item(_make_item("t4", "kl:refine"))
        assert sag_service.transition("t4", "kl:raw") is False
        assert knowledge_repo.get_item("t4").lifecycle == "kl:refine"

    def test_idempotent_same_state(self, temp_db):
        knowledge_repo.upsert_item(_make_item("t5", "kl:refine"))
        assert sag_service.transition("t5", "kl:refine") is True
        assert knowledge_repo.get_item("t5").lifecycle == "kl:refine"

    def test_missing_item_returns_false(self, temp_db):
        assert sag_service.transition("no-such", "kl:publish") is False


class TestPromoteFavorite:
    def test_creates_kl_raw_item(self, temp_db):
        """P1-3: 收藏提升创建 lifecycle=kl:raw 条目 (原 signal)。"""
        item_id = sag_service.promote_favorite_to_knowledge(
            "Fav Title", "https://example.com/fav-1"
        )
        assert item_id  # 非空
        item = knowledge_repo.get_item(item_id)
        assert item is not None
        assert item.lifecycle == "kl:raw"  # P1-3 验收
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
        """新建条目 compiled property 应为 False (kl:raw 状态)。"""
        item_id = sag_service.promote_favorite_to_knowledge(
            "T", "https://example.com/fav-3"
        )
        item = knowledge_repo.get_item(item_id)
        assert item.compiled is False  # kl:raw → compiled=False
        # 推进到 kl:publish 后 compiled 应为 True (P1-3)
        sag_service.transition(item_id, "kl:publish")
        assert knowledge_repo.get_item(item_id).compiled is True
