"""Phase 47 ``current_week_start()`` 单元测试。

覆盖场景
--------
- Mon / Tue / ... / Sun 各 → 正确返回本周一 00:00 Shanghai
- 跨周末 (Sun → 上周一; Sat → 本周一)
- 接受 date / tz-naive datetime / tz-aware datetime
- 运行时默认 → Asia/Shanghai 当前周的周一
- tz-naive 视为 Shanghai (与 business_days 其他工具一致)
- tz-aware (UTC) → 正确转换到 Shanghai 后取周
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from backend.utils.business_days import SHANGHAI_TZ, current_week_start


# ---------------------------------------------------------------------------
# 7 个 weekday 的预期行为
# ---------------------------------------------------------------------------
class TestWeekdayMapping:
    """2026-07-06 是周一。整周测试。"""

    def test_monday(self):
        assert current_week_start(date(2026, 7, 6)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_tuesday(self):
        assert current_week_start(date(2026, 7, 7)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_wednesday(self):
        assert current_week_start(date(2026, 7, 8)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_thursday(self):
        assert current_week_start(date(2026, 7, 9)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_friday(self):
        assert current_week_start(date(2026, 7, 10)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_saturday_rolls_to_monday(self):
        # Sat = 当周 Mon (2026-07-06) — 不像 next_business_day 那样顺延
        assert current_week_start(date(2026, 7, 11)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_sunday_rolls_to_same_monday(self):
        # Sun 跟 Mon 同一周 (Python ISO: Mon=0, Sun=6) → 本周一
        assert current_week_start(date(2026, 7, 12)) == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)


# ---------------------------------------------------------------------------
# 输入类型
# ---------------------------------------------------------------------------
class TestInputTypes:
    def test_accepts_date(self):
        result = current_week_start(date(2026, 7, 8))  # Wednesday
        assert isinstance(result, datetime)
        assert result.tzinfo == SHANGHAI_TZ

    def test_accepts_naive_datetime(self):
        # tz-naive 视为 Shanghai
        result = current_week_start(datetime(2026, 7, 10, 14, 30, 0))
        assert result == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_accepts_utc_datetime_converts_correctly(self):
        # 2026-07-10 16:00 UTC = 2026-07-11 00:00 Shanghai (周六)
        # Shanghai 周六 → 仍是本周一 (2026-07-06)
        utc = datetime(2026, 7, 10, 16, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = current_week_start(utc)
        assert result == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_accepts_shanghai_datetime(self):
        sh = datetime(2026, 7, 10, 9, 0, 0, tzinfo=SHANGHAI_TZ)
        result = current_week_start(sh)
        assert result == datetime(2026, 7, 6, 0, 0, 0, tzinfo=SHANGHAI_TZ)


# ---------------------------------------------------------------------------
# 默认值 (无 today 参数) — 不依赖运行时刻, 只检查返回类型
# ---------------------------------------------------------------------------
class TestDefault:
    def test_default_returns_tz_aware_monday_midnight(self):
        result = current_week_start()
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.weekday() == 0  # Monday
        assert result.time() == time(0, 0, 0)
        # tz 应该 = Shanghai
        assert result.tzinfo == SHANGHAI_TZ


# ---------------------------------------------------------------------------
# 跨月 / 跨年 边界
# ---------------------------------------------------------------------------
class TestBoundary:
    def test_january_1_midweek(self):
        # 2026-01-01 是 Thursday → 本周一是 2025-12-29
        assert current_week_start(date(2026, 1, 1)) == datetime(2025, 12, 29, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_december_31_midweek(self):
        # 2026-12-31 是 Thursday → 本周一是 2026-12-28
        assert current_week_start(date(2026, 12, 31)) == datetime(2026, 12, 28, 0, 0, 0, tzinfo=SHANGHAI_TZ)

    def test_monday_january_1_2024(self):
        # 2024-01-01 是 Monday → 本周一是它本身
        assert current_week_start(date(2024, 1, 1)) == datetime(2024, 1, 1, 0, 0, 0, tzinfo=SHANGHAI_TZ)
