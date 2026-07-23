"""v1.7 Phase 4 — ProfileService 测试.

覆盖:
- ProfileRepository: get/set/list_all/list_by_prefix/delete/decay_all/count
- apply_signal: 新维度/已有维度/clamp/负信号/局部衰减
- decay_all: 全局衰减
- get_weight / get_profile / get_profile_by_prefix
- record_read: 阅读行为记录 (验收 1)
- 验收 1: 阅读 3 篇 AI 文章后 AI 分类权重提升
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.profile_repo import ProfileRepository
from backend.services.profile_service import (
    SIGNAL_FAVORITE,
    SIGNAL_READ,
    SIGNAL_SKIP,
    WEIGHT_MAX,
    WEIGHT_MIN,
    apply_signal,
    decay_all,
    get_profile,
    get_profile_by_prefix,
    get_weight,
    record_read,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_profile.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# ProfileRepository
# ---------------------------------------------------------------------------
class TestProfileRepository:
    def test_get_missing_returns_none(self, temp_db):
        assert ProfileRepository().get("category:ai") is None

    def test_set_and_get(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", 0.5)
        row = repo.get("category:ai")
        assert row is not None
        assert row["dimension"] == "category:ai"
        assert abs(row["weight"] - 0.5) < 1e-6

    def test_set_upsert(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", 0.3)
        repo.set("category:ai", 0.7)
        assert abs(repo.get("category:ai")["weight"] - 0.7) < 1e-6

    def test_set_clamps_to_max(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", 10.0)
        assert abs(repo.get("category:ai")["weight"] - WEIGHT_MAX) < 1e-6

    def test_set_clamps_to_min(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", -10.0)
        assert abs(repo.get("category:ai")["weight"] - WEIGHT_MIN) < 1e-6

    def test_list_all_ordered_by_abs_weight(self, temp_db):
        repo = ProfileRepository()
        repo.set("a", 0.1)
        repo.set("b", -0.9)
        repo.set("c", 0.5)
        rows = repo.list_all()
        # abs(0.5) < abs(-0.9), 所以 b 在 c 前, a 最后
        assert rows[0]["dimension"] == "b"
        assert rows[1]["dimension"] == "c"
        assert rows[2]["dimension"] == "a"

    def test_list_by_prefix(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", 0.5)
        repo.set("category:security", 0.3)
        repo.set("tag:fastapi", 0.2)
        rows = repo.list_by_prefix("category:")
        assert len(rows) == 2
        assert all(r["dimension"].startswith("category:") for r in rows)

    def test_delete(self, temp_db):
        repo = ProfileRepository()
        repo.set("category:ai", 0.5)
        assert repo.delete("category:ai") is True
        assert repo.get("category:ai") is None

    def test_delete_missing_returns_false(self, temp_db):
        assert ProfileRepository().delete("nonexistent") is False

    def test_decay_all(self, temp_db):
        repo = ProfileRepository()
        repo.set("a", 1.0)
        repo.set("b", -0.8)
        affected = repo.decay_all()
        assert affected == 2
        # 1.0 * 0.95 = 0.95
        assert abs(repo.get("a")["weight"] - 0.95) < 1e-6
        # -0.8 * 0.95 = -0.76
        assert abs(repo.get("b")["weight"] - (-0.76)) < 1e-6

    def test_decay_all_empty(self, temp_db):
        assert ProfileRepository().decay_all() == 0

    def test_count(self, temp_db):
        repo = ProfileRepository()
        assert repo.count() == 0
        repo.set("a", 0.1)
        repo.set("b", 0.2)
        assert repo.count() == 2


# ---------------------------------------------------------------------------
# apply_signal
# ---------------------------------------------------------------------------
class TestApplySignal:
    def test_new_dimension_starts_from_zero(self, temp_db):
        # new = 0.0 * 0.95 + 0.1 = 0.1
        w = apply_signal("category:ai", SIGNAL_READ)
        assert abs(w - 0.1) < 1e-6

    def test_existing_dimension_ema(self, temp_db):
        apply_signal("category:ai", 0.5)  # → 0.5
        w = apply_signal("category:ai", 0.5)  # → 0.5*0.95 + 0.5 = 0.975
        assert abs(w - 0.975) < 1e-6

    def test_clamp_to_max(self, temp_db):
        apply_signal("category:ai", 2.0)  # → 2.0
        w = apply_signal("category:ai", 2.0)  # → 2.0*0.95 + 2.0 = 3.9 → clamp 2.0
        assert abs(w - WEIGHT_MAX) < 1e-6

    def test_clamp_to_min(self, temp_db):
        apply_signal("category:ai", -2.0)  # → -2.0
        w = apply_signal("category:ai", -2.0)  # → -2.0*0.95 + (-2.0) = -3.9 → clamp -2.0
        assert abs(w - WEIGHT_MIN) < 1e-6

    def test_negative_signal(self, temp_db):
        apply_signal("category:ai", 0.5)
        w = apply_signal("category:ai", SIGNAL_SKIP)  # 0.5*0.95 + (-0.05) = 0.425
        assert abs(w - 0.425) < 1e-6

    def test_local_decay_applied(self, temp_db):
        """每次 apply_signal 先对旧权重做 *0.95 衰减, 再叠加信号。"""
        apply_signal("a", 1.0)  # → 1.0
        w = apply_signal("a", 0.0)  # → 1.0 * 0.95 + 0.0 = 0.95
        assert abs(w - 0.95) < 1e-6


# ---------------------------------------------------------------------------
# decay_all (service 层)
# ---------------------------------------------------------------------------
class TestDecayAll:
    def test_decay_all_returns_affected_count(self, temp_db):
        apply_signal("a", 0.5)
        apply_signal("b", 0.3)
        n = decay_all()
        assert n == 2

    def test_decay_all_reduces_weight(self, temp_db):
        apply_signal("a", 1.0)
        decay_all()
        assert abs(get_weight("a") - 0.95) < 1e-6

    def test_decay_all_empty_returns_zero(self, temp_db):
        assert decay_all() == 0


# ---------------------------------------------------------------------------
# get_weight / get_profile
# ---------------------------------------------------------------------------
class TestGetWeight:
    def test_missing_returns_zero(self, temp_db):
        assert get_weight("nonexistent") == 0.0

    def test_returns_current_weight(self, temp_db):
        apply_signal("category:ai", 0.5)
        assert abs(get_weight("category:ai") - 0.5) < 1e-6


class TestGetProfile:
    def test_empty_returns_empty_list(self, temp_db):
        assert get_profile() == []

    def test_returns_all_dimensions(self, temp_db):
        apply_signal("a", 0.1)
        apply_signal("b", 0.2)
        profile = get_profile()
        assert len(profile) == 2

    def test_ordered_by_abs_weight_desc(self, temp_db):
        apply_signal("a", 0.1)
        apply_signal("b", -0.9)
        apply_signal("c", 0.5)
        profile = get_profile()
        assert profile[0]["dimension"] == "b"  # abs(0.9)
        assert profile[1]["dimension"] == "c"  # abs(0.5)
        assert profile[2]["dimension"] == "a"  # abs(0.1)

    def test_limit(self, temp_db):
        for i in range(5):
            apply_signal(f"d{i}", 0.1 * (i + 1))
        assert len(get_profile(limit=3)) == 3

    def test_get_profile_by_prefix(self, temp_db):
        apply_signal("category:ai", 0.5)
        apply_signal("category:sec", 0.3)
        apply_signal("tag:fastapi", 0.2)
        rows = get_profile_by_prefix("category:")
        assert len(rows) == 2
        assert all(r["dimension"].startswith("category:") for r in rows)


# ---------------------------------------------------------------------------
# record_read
# ---------------------------------------------------------------------------
class TestRecordRead:
    def test_updates_category_weight(self, temp_db):
        w = record_read("ai")
        assert abs(w - SIGNAL_READ) < 1e-6
        assert abs(get_weight("category:ai") - SIGNAL_READ) < 1e-6

    def test_updates_source_weight_optional(self, temp_db):
        record_read("ai", source="freebuf")
        assert get_weight("category:ai") > 0
        assert get_weight("source:freebuf") > 0

    def test_without_source_only_category(self, temp_db):
        record_read("ai")
        assert get_weight("source:freebuf") == 0.0


# ---------------------------------------------------------------------------
# 验收 1: 阅读 3 篇 AI 文章后 AI 分类权重提升
# ---------------------------------------------------------------------------
class TestAcceptance1ReadBoostsWeight:
    """验收 1: 阅读 3 篇 AI 文章后 AI 分类权重提升。"""

    def test_three_reads_boost_weight(self, temp_db):
        # 初始权重为 0
        assert get_weight("category:ai") == 0.0

        # 模拟阅读 3 篇 AI 文章
        record_read("ai")
        w1 = get_weight("category:ai")
        record_read("ai")
        w2 = get_weight("category:ai")
        record_read("ai")
        w3 = get_weight("category:ai")

        # 权重应持续提升 (每次 EMA 叠加正信号)
        assert w1 > 0
        assert w2 > w1
        assert w3 > w2

        # 3 次后权重应明显高于初始 0
        assert w3 > 0.25  # 0.1 + 0.1*0.95 + 0.1*0.95^2 ≈ 0.285

    def test_favorite_signal_stronger_than_read(self, temp_db):
        """收藏信号 (0.3) 应比阅读信号 (0.1) 产生更高权重。"""
        apply_signal("category:ai", SIGNAL_READ)
        w_read = get_weight("category:ai")

        # 清空重来
        ProfileRepository().delete("category:ai")
        apply_signal("category:ai", SIGNAL_FAVORITE)
        w_fav = get_weight("category:ai")

        assert w_fav > w_read
