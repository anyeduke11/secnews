"""TrendRepository 单元测试

每个测试使用 tmp_path 隔离的临时 SQLite，并通过 monkeypatch
重定向 ``config.db_path``，避免污染真实 ``backend/hotspot.db``。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.repository import db
from backend.repository.trend_repo import TrendRepository


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db) -> TrendRepository:
    return TrendRepository()


def _make_item(
    id_: str,
    category: Category = Category.AI,
    *,
    published_at: datetime,
    is_fallback: bool = False,
) -> HotspotItem:
    return HotspotItem(
        id=id_,
        title=f"title-{id_}",
        source="unit-test",
        url=f"https://example.com/{id_}",
        category=category,
        published_at=published_at,
        fetched_at=published_at,
        is_fallback=is_fallback,
    )


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------
def test_rebuild_returns_168(repo):
    """空表上 rebuild(24) 仍应写入 24 * 8 = 192 行（每桶 count=0）。"""
    n = repo.rebuild(24)
    assert n == 192
    points = repo.get_current()
    assert len(points) == 192


def test_rebuild_excludes_fallback(repo):
    """rebuild 硬过滤 is_fallback=1；10 ai（5 fallback）→ ai 总数 = 5。"""
    # 全部放在 hours_ago=0 桶内：[now-1h, now)
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    items: list[HotspotItem] = []
    for i in range(5):
        items.append(_make_item(f"real-{i}", Category.AI, published_at=base, is_fallback=False))
    for i in range(5):
        items.append(_make_item(f"fb-{i}", Category.AI, published_at=base, is_fallback=True))

    from backend.repository.hotspot_repo import HotspotRepository
    HotspotRepository().upsert_many(items)

    repo.rebuild(24)
    points = repo.get_current()

    # 所有 ai 类桶的 count 之和 = 5
    ai_total = sum(p.count for p in points if p.category == Category.AI.value)
    assert ai_total == 5


def test_get_current_returns_168_points(repo):
    """rebuild 后 get_current 应返回 192 个 TrendPoint。"""
    repo.rebuild(24)
    points = repo.get_current()
    assert len(points) == 192
    # 所有 TrendPoint 都有 hours_ago / category / count
    for p in points:
        assert 0 <= p.hours_ago < 24
        assert p.category in {c.value for c in Category}
        assert p.count >= 0
    # hours_ago 取值集合完整
    assert {p.hours_ago for p in points} == set(range(24))
    # 八个类目各出现 24 次
    for cat in Category:
        cat_points = [p for p in points if p.category == cat.value]
        assert len(cat_points) == 24


def test_rebuild_window_hours_6(repo):
    """rebuild(6) 应写入 6 * 8 = 48 行。"""
    n = repo.rebuild(6)
    assert n == 48
    points = repo.get_current()
    assert len(points) == 48
    # hours_ago 取值仅为 0..5
    assert {p.hours_ago for p in points} == {0, 1, 2, 3, 4, 5}


def test_rebuild_bucket_placement_and_wide_window(repo):
    """锁定 GROUP BY 重写后的桶归属语义。

    hours_ago=h 必须等价于旧区间比较的 [now-(h+1)h, now-h)；未来时间戳仍要排除
    （旧 SQL 有 ``< datetime('now','-0 hours')`` 上界）；168h 宽窗口要能真正表示
    超出 24h 的历史桶 —— 旧 job 硬编码 rebuild(24) 时那段只能被上层补成假 0。
    """
    from backend.repository.hotspot_repo import HotspotRepository

    now = datetime.now(timezone.utc)
    HotspotRepository().upsert_many([
        _make_item("b0", Category.AI, published_at=now - timedelta(minutes=30)),   # 桶 0
        _make_item("b2", Category.SECURITY, published_at=now - timedelta(hours=2, minutes=30)),  # 桶 2
        _make_item("b100", Category.AI, published_at=now - timedelta(hours=100)),  # 桶 100 (>24h)
        _make_item("future", Category.AI, published_at=now + timedelta(hours=5)),  # 未来 → 排除
    ])

    assert repo.rebuild(168) == 168 * 8

    def _count(category: Category, hours_ago: int) -> int:
        return sum(
            p.count for p in repo.get_current()
            if p.category == category.value and p.hours_ago == hours_ago
        )

    assert _count(Category.AI, 0) == 1
    assert _count(Category.SECURITY, 2) == 1
    assert _count(Category.AI, 100) == 1, "168h 宽窗口的远端历史桶必须可表达"
    # 未来条目不得污染任何桶；桶 1 应为空
    assert _count(Category.AI, 1) == 0
    ai_total = sum(p.count for p in repo.get_current() if p.category == Category.AI.value)
    assert ai_total == 2, "3 条 ai 入库但有 1 条是未来时间戳 → 只应计 2 条"
