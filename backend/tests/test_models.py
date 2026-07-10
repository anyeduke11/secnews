"""领域模型 / 枚举 单元测试

覆盖：
  - HotspotItem 必填字段、默认值、字段校验
  - Category.from_str 归一化
  - TimeRange.to_hours 数值映射
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import HttpUrl, ValidationError

from backend.domain.enums import Category, TimeRange
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _minimal_item(**overrides) -> HotspotItem:
    """构造一个最小可用的 HotspotItem（所有必填字段填齐）。"""
    base = dict(
        id="x-1",
        title="hello",
        source="unit-test",
        url="https://example.com/a",
        category=Category.AI,
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return HotspotItem(**base)


# ---------------------------------------------------------------------------
# HotspotItem — 必填字段 / 默认值
# ---------------------------------------------------------------------------
def test_hotspot_item_minimal_required():
    """只填必填字段，构造应成功。"""
    item = _minimal_item()
    assert item.id == "x-1"
    assert item.title == "hello"
    assert item.url_str() == "https://example.com/a"
    assert item.category is Category.AI
    assert item.published_at.tzinfo is not None


def test_hotspot_item_default_values():
    """默认值：is_fallback=False / quality_score=100 / quality_flags=[]."""
    item = _minimal_item()
    assert item.is_fallback is False
    assert item.quality_score == 100
    assert item.quality_flags == []
    # score / summary / quality_checked_at / url_check_status 默认 None
    assert item.score is None
    assert item.summary is None
    assert item.quality_checked_at is None
    assert item.url_check_status is None


# ---------------------------------------------------------------------------
# HotspotItem — 字段校验
# ---------------------------------------------------------------------------
def test_hotspot_item_missing_title_raises():
    """缺 title 应抛 ValidationError。"""
    with pytest.raises(ValidationError):
        HotspotItem(
            id="x-1",
            source="unit-test",
            url="https://example.com/a",
            category=Category.AI,
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_hotspot_item_invalid_url_raises():
    """url='not-a-url' 应抛 ValidationError。"""
    with pytest.raises(ValidationError):
        _minimal_item(url="not-a-url")


def test_hotspot_item_invalid_category_raises():
    """category='bogus' 应抛 ValidationError。"""
    with pytest.raises(ValidationError):
        _minimal_item(category="bogus")


def test_hotspot_item_timezone_required():
    """published_at=naive datetime 应抛 ValidationError（数据层要求 tz-aware）。"""
    with pytest.raises(ValidationError):
        HotspotItem(
            id="x-1",
            title="hello",
            source="unit-test",
            url="https://example.com/a",
            category=Category.AI,
            published_at=datetime(2026, 1, 1),  # no tzinfo
            fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_hotspot_item_quality_score_bounds():
    """quality_score 超出 [0, 100] 范围应抛 ValidationError。"""
    with pytest.raises(ValidationError):
        _minimal_item(quality_score=200)
    with pytest.raises(ValidationError):
        _minimal_item(quality_score=-1)


def test_hotspot_item_url_check_status_enum():
    """url_check_status 不在合法集合内应抛 ValidationError。"""
    with pytest.raises(ValidationError):
        _minimal_item(url_check_status="bogus-status")
    # 合法值可以接受
    item = _minimal_item(url_check_status="verified")
    assert item.url_check_status == "verified"


# ---------------------------------------------------------------------------
# Category / TimeRange
# ---------------------------------------------------------------------------
def test_category_from_str_normalize():
    """Category.from_str 自动 strip / lowercase。"""
    assert Category.from_str("  AI  ") is Category.AI
    assert Category.from_str("security") is Category.SECURITY
    assert Category.from_str("FINANCE") is Category.FINANCE
    # 非法值抛 InvalidParamException（不是裸 ValueError）
    from backend.exceptions import InvalidParamException

    with pytest.raises(InvalidParamException):
        Category.from_str("bogus")


def test_time_range_to_hours():
    """TimeRange.to_hours 应返回 24 / 72 / 168 / 720。"""
    assert TimeRange.H24.to_hours() == 24
    assert TimeRange.D3.to_hours() == 72
    assert TimeRange.D7.to_hours() == 168
    assert TimeRange.D30.to_hours() == 720


def test_time_range_start_datetime_calendar_based():
    """Phase 39: H24 / D3 改为「基于日历日」语义 (不再滚动 24h / 3d)。

    - H24: 今日 00:00 UTC
    - D3 : 今日 - 2 天 00:00 UTC (3 个日历日)
    - D7 : 本周周一 00:00 UTC (calendar week, 不变)
    """
    from datetime import datetime, timezone
    now_utc = datetime(2026, 7, 8, 14, 30, 0, tzinfo=timezone.utc)  # 周三下午
    h24 = TimeRange.H24.start_datetime()
    d3 = TimeRange.D3.start_datetime()
    d7 = TimeRange.D7.start_datetime()
    # H24 起点 = 今日 00:00 UTC
    assert h24.hour == 0 and h24.minute == 0 and h24.second == 0
    assert (now_utc - h24).total_seconds() < 24 * 3600  # 不超过 24h 之前
    # D3 起点 = 今日 - 2 天 00:00 UTC
    assert d3.hour == 0 and d3.minute == 0 and d3.second == 0
    assert (h24 - d3).days == 2  # 恰好 2 天
    # D7 起点 = 本周周一 00:00 UTC (周三 → 周一 = 2 天前)
    assert d7.weekday() == 0  # 周一
    assert d7.hour == 0 and d7.minute == 0
    assert (h24 - d7).days == 2  # 周三 → 周一 = 2 天前
    # 全部是 tz-aware UTC
    assert h24.tzinfo is not None
    assert d3.tzinfo is not None
    assert d7.tzinfo is not None
