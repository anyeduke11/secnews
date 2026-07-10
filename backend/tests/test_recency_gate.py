"""Phase 47: RecencyGate 单元测试 — 资讯/标讯时效硬门禁。

覆盖场景
--------
- published_at 为 None → 拒收 + flag no_published_at + 扣 80
- published_at = 本周一 00:00 Shanghai → 通过 (边界)
- published_at = 本周一 - 1s → 拒收 + flag historical_published + 扣 100
- published_at = 上周 7 天前 → 拒收 (嘶吼典型)
- published_at = 本周一 + 1s → 通过
- published_at = now → 通过 (嘶吼页面级 published_at 永远临近)
- published_at = tz-naive (被 model validator 拒绝前) → 兜底视为 UTC
- 跨周末: Sat/Sun → 仍是「本周」, 所以 Sun 23:00 Shanghai 还属于本周
- 跨时区: UTC published_at 早于 Shanghai 本周一 → 拒收
- 所有 category (ai/tech/finance/security/bid/startup/github) 都走同一个门禁
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.base import GateContext
from backend.quality.recency_gate import RecencyGate
from backend.utils.business_days import SHANGHAI_TZ, current_week_start


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str = "t1",
    *,
    title: str = "OpenAI announces GPT-5 model with new capabilities",
    source: str = "src_a",
    category: Category = Category.AI,
    url: str = "https://example.com/t1",
    published_at: datetime | None = None,
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=url,
        category=category,
        published_at=published_at if published_at is not None else now,
        fetched_at=now,
    )


def _ctx() -> GateContext:
    return GateContext(mode="loose")


# ---------------------------------------------------------------------------
# 缺失 published_at
# ---------------------------------------------------------------------------
class TestMissingPublishedAt:
    def test_none_published_at_rejected(self):
        """嘶吼典型: 提取不到发布时间 → 拒收。"""
        item = _make_item(published_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        # 模拟 None (绕过 model validator): 用 Pydantic model_construct
        item_na = HotspotItem.model_construct(
            id="t1", title="Some title", source="src_a", url="https://x.com/1",
            category=Category.SECURITY, published_at=None, fetched_at=datetime.now(timezone.utc),
            quality_score=100, quality_flags=[],
        )
        result = RecencyGate().check(item_na, _ctx())
        assert result.passed is False
        assert "no_published_at" in result.flags
        assert result.score_deduction == 80
        assert "cannot verify recency" in (result.reason or "")


# ---------------------------------------------------------------------------
# 早于本周一 → historical_published
# ---------------------------------------------------------------------------
class TestHistoricalPublished:
    def test_one_second_before_week_start(self):
        """published_at = 本周一 00:00:00 Shanghai - 1s → 拒收。"""
        week_start = current_week_start()
        pub = week_start - timedelta(seconds=1)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is False
        assert "historical_published" in result.flags
        assert result.score_deduction == 100
        assert "0d" in (result.reason or "") or "by 0d" in (result.reason or "")

    def test_seven_days_before_week_start(self):
        """published_at = 7 天前 → 拒收 (嘶吼典型)。"""
        week_start = current_week_start()
        pub = week_start - timedelta(days=7)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is False
        assert "historical_published" in result.flags
        assert result.score_deduction == 100
        assert "by 7d" in (result.reason or "")

    def test_one_year_ago(self):
        """published_at = 1 年前 → 拒收。"""
        now = datetime.now(timezone.utc)
        pub = now - timedelta(days=365)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is False
        assert "historical_published" in result.flags


# ---------------------------------------------------------------------------
# 边界: = 本周一 00:00:00 Shanghai → 通过
# ---------------------------------------------------------------------------
class TestWeekStartBoundary:
    def test_exact_week_start_passes(self):
        """published_at 正好 = 本周一 00:00:00 Shanghai → 通过 (>= 边界放行)。"""
        week_start = current_week_start()
        item = _make_item(published_at=week_start)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True
        assert result.flags == []
        assert result.score_deduction == 0

    def test_one_second_after_week_start_passes(self):
        week_start = current_week_start()
        pub = week_start + timedelta(seconds=1)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True


# ---------------------------------------------------------------------------
# 当周内: now / 几小时前 / 几天前 (Mon/Tue/Wed/Thu/Fri) → 通过
# ---------------------------------------------------------------------------
class TestWithinWeek:
    def test_now_passes(self):
        item = _make_item(published_at=datetime.now(timezone.utc))
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True

    def test_few_hours_ago_passes(self):
        pub = datetime.now(timezone.utc) - timedelta(hours=4)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True

    def test_three_days_ago_within_week_passes(self):
        week_start = current_week_start()
        # 假设今天 Thu/Fri → 周一 + 3 天 = 周四 (本周内)
        pub = week_start + timedelta(days=3, hours=10)
        item = _make_item(published_at=pub)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True


# ---------------------------------------------------------------------------
# 跨周末 / 跨时区
# ---------------------------------------------------------------------------
class TestTimezone:
    def test_naive_datetime_treated_as_utc(self):
        """tz-naive published_at → 视为 UTC 兜底。"""
        week_start = current_week_start()  # Shanghai
        # UTC 等价的时间 (即 Shanghai - 8h) 早于 Shanghai 本周一
        naive = week_start.replace(tzinfo=None) - timedelta(hours=8) - timedelta(seconds=1)
        # model validator 拒绝 tz-naive, 用 model_construct 绕过
        now = datetime.now(timezone.utc)
        item = HotspotItem.model_construct(
            id="t1", title="OpenAI announces GPT-5", source="src_a",
            url="https://x.com/1", category=Category.AI,
            published_at=naive, fetched_at=now,
            quality_score=100, quality_flags=[],
        )
        result = RecencyGate().check(item, _ctx())
        # 视为 UTC → 换算到 Shanghai 是本周一 - 1s → 拒收
        assert result.passed is False
        assert "historical_published" in result.flags

    def test_utc_published_at_converts_via_shanghai(self):
        """published_at 是 UTC, 早于 Shanghai 本周一 → 拒收。"""
        # Shanghai 本周一 00:00 = UTC 上周日 16:00
        # UTC 2026-07-05 15:00 (上周日 15:00 UTC) → 早于 Shanghai 本周一
        utc = datetime(2026, 7, 5, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
        item = _make_item(published_at=utc)
        result = RecencyGate().check(item, _ctx())
        # 换算到 Shanghai 是 2026-07-05 23:00, 是上周日, 不在本周
        assert result.passed is False
        assert "historical_published" in result.flags


# ---------------------------------------------------------------------------
# 所有 category 都走同一个门禁
# ---------------------------------------------------------------------------
class TestAllCategories:
    @pytest.mark.parametrize("cat", list(Category))
    def test_all_categories_affected(self, cat):
        """RecencyGate 对所有 category 都生效, 不是 bid-only。"""
        # 历史 published_at
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        item = _make_item(category=cat, published_at=old)
        result = RecencyGate().check(item, _ctx())
        assert result.passed is False
        assert "historical_published" in result.flags

    @pytest.mark.parametrize("cat", list(Category))
    def test_all_categories_passes_when_within_week(self, cat):
        item = _make_item(
            category=cat,
            published_at=datetime.now(timezone.utc),
        )
        result = RecencyGate().check(item, _ctx())
        assert result.passed is True


# ---------------------------------------------------------------------------
# 异常处理
# ---------------------------------------------------------------------------
class TestRobustness:
    def test_exception_in_check_returns_passed_with_error(self):
        """内部异常 → 不应 crash, 走 _wrap_exception。"""
        # 构造一个会出错的 item (eg 强制 type 错误)
        # 这里用 model_construct 构造一个 timezone 异常的 published_at
        item = HotspotItem.model_construct(
            id="t1", title="Some title", source="src_a", url="https://x.com/1",
            category=Category.SECURITY,
            published_at="not a datetime",  # type: ignore
            fetched_at=datetime.now(timezone.utc),
            quality_score=100, quality_flags=[],
        )
        result = RecencyGate().check(item, _ctx())
        # _wrap_exception 返回 passed=True + error_msg
        assert result.error_msg is not None
        assert result.passed is True
        assert result.score_deduction == 0
