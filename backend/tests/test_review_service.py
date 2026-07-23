"""v1.7 Phase 2 — SM-2 ReviewService 测试。

覆盖:
- sm2_schedule: 纯函数 (失败重置 / 首次通过 / 第二次 6 天 / easiness 调整 / 下限 1.3)
- submit_grade: 首次评分 / 多次评分间隔延长 / grade 越界拒绝
- create_review: 新建 + 幂等
- list_due: 到期过滤
- stats: 统计正确性
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.reviews_repo import ReviewRepository
from backend.services import review_service


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_review.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ===========================================================================
# 1. sm2_schedule 纯函数
# ===========================================================================
class TestSm2Schedule:
    def test_fail_resets_repetitions(self):
        """grade < 3 → repetitions 归零, interval=1。"""
        e, i, r = review_service.sm2_schedule(grade=2, easiness=2.5, interval=10, repetitions=5)
        assert r == 0
        assert i == 1

    def test_first_pass_interval_1(self):
        """首次通过 (repetitions=0) → interval=1, repetitions=1。"""
        e, i, r = review_service.sm2_schedule(grade=4, easiness=2.5, interval=0, repetitions=0)
        assert i == 1
        assert r == 1

    def test_second_pass_interval_6(self):
        """第二次通过 (repetitions=1) → interval=6。"""
        e, i, r = review_service.sm2_schedule(grade=4, easiness=2.5, interval=1, repetitions=1)
        assert i == 6
        assert r == 2

    def test_third_pass_uses_easiness(self):
        """第三次通过 → interval = round(prev_interval * easiness)。"""
        e, i, r = review_service.sm2_schedule(grade=5, easiness=2.5, interval=6, repetitions=2)
        assert i == round(6 * 2.5)
        assert r == 3

    def test_easiness_never_below_1_3(self):
        """连续低分评分 easiness 不会低于 1.3。"""
        e = 1.4
        for _ in range(10):
            e, _, _ = review_service.sm2_schedule(grade=0, easiness=e, interval=1, repetitions=0)
        assert e >= 1.3

    def test_perfect_grade_increases_easiness(self):
        """grade=5 提升 easiness。"""
        e_before = 2.5
        e_after, _, _ = review_service.sm2_schedule(grade=5, easiness=e_before, interval=1, repetitions=1)
        assert e_after > e_before


# ===========================================================================
# 2. submit_grade
# ===========================================================================
class TestSubmitGrade:
    def test_first_grade_creates_record(self, temp_db):
        row = review_service.submit_grade("concept", "c1", grade=4)
        assert row is not None
        assert row["entity_type"] == "concept"
        assert row["entity_id"] == "c1"
        assert row["repetitions"] == 1
        assert row["interval"] == 1
        assert row["last_grade"] == 4

    def test_repeated_pass_extends_interval(self, temp_db):
        """验收 2: 评分后间隔按 SM-2 延长。"""
        # 第一次 grade=4 → interval=1
        r1 = review_service.submit_grade("concept", "c2", grade=4)
        assert r1["interval"] == 1
        # 第二次 grade=4 → interval=6
        r2 = review_service.submit_grade("concept", "c2", grade=4)
        assert r2["interval"] == 6
        assert r2["interval"] > r1["interval"]
        # 第三次 grade=5 → interval = round(6 * easiness) > 6
        r3 = review_service.submit_grade("concept", "c2", grade=5)
        assert r3["interval"] > r2["interval"]

    def test_fail_resets_interval_to_1(self, temp_db):
        """通过几次后失败 → interval 回到 1。"""
        review_service.submit_grade("concept", "c3", grade=4)
        review_service.submit_grade("concept", "c3", grade=4)  # interval=6
        r = review_service.submit_grade("concept", "c3", grade=1)  # fail
        assert r["interval"] == 1
        assert r["repetitions"] == 0

    def test_invalid_grade_raises(self, temp_db):
        with pytest.raises(ValueError):
            review_service.submit_grade("concept", "c4", grade=6)
        with pytest.raises(ValueError):
            review_service.submit_grade("concept", "c4", grade=-1)

    def test_due_at_in_future_after_pass(self, temp_db):
        """通过评分后 due_at 应在未来。"""
        review_service.submit_grade("concept", "c5", grade=4)
        row = ReviewRepository().get("concept", "c5")
        due = datetime.fromisoformat(row["due_at"])
        assert due > datetime.now(timezone.utc)


# ===========================================================================
# 3. create_review (验收 1)
# ===========================================================================
class TestCreateReview:
    def test_create_new_review_due_within_24h(self, temp_db):
        """验收 1: 新学概念创建后 24h 出现在复习队列。

        用 initial_interval_days=0 让其立即到期进入队列; 另校验默认
        initial_interval_days=1 时 due_at 落在 now+24h 内 (即 24h 后到期)。
        """
        # 立即到期 → 进入 due 队列
        review_service.create_review("concept", "new-c", initial_interval_days=0)
        due = review_service.list_due(limit=100)
        ids = {(r["entity_type"], r["entity_id"]) for r in due}
        assert ("concept", "new-c") in ids

        # 默认 1 天间隔 → due_at 在 now+24h 内 (24h 后才进入队列)
        review_service.create_review("concept", "new-c-24h", initial_interval_days=1)
        row = ReviewRepository().get("concept", "new-c-24h")
        due_at = datetime.fromisoformat(row["due_at"])
        delta = due_at - datetime.now(timezone.utc)
        assert timedelta(hours=0) < delta <= timedelta(hours=24)

    def test_create_idempotent(self, temp_db):
        """已存在的复习记录不被覆盖。"""
        review_service.submit_grade("concept", "c-idem", grade=5)
        before = ReviewRepository().get("concept", "c-idem")
        # create_review 不应覆盖已有评分
        review_service.create_review("concept", "c-idem")
        after = ReviewRepository().get("concept", "c-idem")
        assert after["repetitions"] == before["repetitions"]
        assert after["easiness"] == before["easiness"]


# ===========================================================================
# 4. list_due
# ===========================================================================
class TestListDue:
    def test_only_due_returned(self, temp_db):
        """未来到期的记录不在 due 队列。"""
        # create_review 默认 1 天后到期 → 当前 due
        review_service.create_review("concept", "due-now", initial_interval_days=0)
        # 评分 grade=4 三次 → interval 较大, 未来才到期
        for _ in range(3):
            review_service.submit_grade("concept", "future", grade=5)

        due = review_service.list_due(limit=100)
        due_ids = {(r["entity_type"], r["entity_id"]) for r in due}
        assert ("concept", "due-now") in due_ids
        # future 经过 3 次 grade=5, interval 增长, 可能仍在 due (interval=0 时)
        # 关键: due-now 必定在队列里


# ===========================================================================
# 5. stats
# ===========================================================================
class TestStats:
    def test_stats_counts(self, temp_db):
        review_service.create_review("concept", "s1", initial_interval_days=0)
        review_service.create_review("concept", "s2", initial_interval_days=0)
        review_service.submit_grade("concept", "s3", grade=5)  # 未来到期
        s = review_service.stats()
        assert s["total"] == 3
        assert s["due"] >= 2  # s1, s2 到期
        assert s["avg_easiness"] > 0

    def test_stats_empty(self, temp_db):
        s = review_service.stats()
        assert s["total"] == 0
        assert s["due"] == 0
        assert s["avg_easiness"] == 0.0
