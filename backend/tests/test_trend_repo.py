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
    """空表上 rebuild(24) 仍应写入 24 * 7 = 168 行（每桶 count=0）。"""
    n = repo.rebuild(24)
    assert n == 168
    points = repo.get_current()
    assert len(points) == 168


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
    """rebuild 后 get_current 应返回 168 个 TrendPoint。"""
    repo.rebuild(24)
    points = repo.get_current()
    assert len(points) == 168
    # 所有 TrendPoint 都有 hours_ago / category / count
    for p in points:
        assert 0 <= p.hours_ago < 24
        assert p.category in {c.value for c in Category}
        assert p.count >= 0
    # hours_ago 取值集合完整
    assert {p.hours_ago for p in points} == set(range(24))
    # 七个类目各出现 24 次
    for cat in Category:
        cat_points = [p for p in points if p.category == cat.value]
        assert len(cat_points) == 24


def test_rebuild_window_hours_6(repo):
    """rebuild(6) 应写入 6 * 7 = 42 行。"""
    n = repo.rebuild(6)
    assert n == 42
    points = repo.get_current()
    assert len(points) == 42
    # hours_ago 取值仅为 0..5
    assert {p.hours_ago for p in points} == {0, 1, 2, 3, 4, 5}
