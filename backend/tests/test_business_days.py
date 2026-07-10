"""Phase 46 紧急自动判断单元测试 — backend/utils/business_days.py

覆盖场景
--------
- 无 deadline → fallback (legacy 兼容)
- 过期 (deadline < today) → 紧急
- 今天 (deadline = today) → 紧急
- 明天 (deadline = today+1) → 紧急
- 后天 (deadline = today+2) → 不紧急
- 截止日期在周末 → 顺延到周一 → 紧急判断基于顺延后
- 今天在周末 → 「今天」= 下周一
- 跨周末 (Fri→Mon) → 1 业务日 → 紧急
- 日期解析失败 (格式错误) → 视为无 deadline
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.utils.business_days import (
    business_days_diff,
    compute_effective_urgent,
    next_business_day,
)


# ---------------------------------------------------------------------------
# next_business_day
# ---------------------------------------------------------------------------
class TestNextBusinessDay:
    def test_monday_unchanged(self):
        d = date(2026, 7, 6)  # Monday
        assert next_business_day(d) == d

    def test_tuesday_unchanged(self):
        d = date(2026, 7, 7)  # Tuesday
        assert next_business_day(d) == d

    def test_wednesday_unchanged(self):
        d = date(2026, 7, 8)  # Wednesday
        assert next_business_day(d) == d

    def test_thursday_unchanged(self):
        d = date(2026, 7, 9)  # Thursday
        assert next_business_day(d) == d

    def test_friday_unchanged(self):
        d = date(2026, 7, 10)  # Friday
        assert next_business_day(d) == d

    def test_saturday_rolls_to_monday(self):
        d = date(2026, 7, 11)  # Saturday
        assert next_business_day(d) == date(2026, 7, 13)  # Monday

    def test_sunday_rolls_to_monday(self):
        d = date(2026, 7, 12)  # Sunday
        assert next_business_day(d) == date(2026, 7, 13)  # Monday


# ---------------------------------------------------------------------------
# business_days_diff
# ---------------------------------------------------------------------------
class TestBusinessDaysDiff:
    def test_same_day_zero(self):
        d = date(2026, 7, 6)  # Monday
        assert business_days_diff(d, d) == 0

    def test_mon_to_tue_one(self):
        assert business_days_diff(date(2026, 7, 6), date(2026, 7, 7)) == 1

    def test_mon_to_wed_two(self):
        assert business_days_diff(date(2026, 7, 6), date(2026, 7, 8)) == 2

    def test_mon_to_fri_four(self):
        assert business_days_diff(date(2026, 7, 6), date(2026, 7, 10)) == 4

    def test_fri_to_next_mon_one(self):
        """跨周末 (Fri→Mon) → 1 业务日。"""
        assert business_days_diff(date(2026, 7, 10), date(2026, 7, 13)) == 1

    def test_fri_to_next_wed_three(self):
        """跨周末 (Fri→Wed) → 3 业务日 (Mon, Tue, Wed)。"""
        assert business_days_diff(date(2026, 7, 10), date(2026, 7, 15)) == 3

    def test_sat_to_next_mon_one(self):
        """Sat → Mon: end-inclusive, Mon 算 1 个业务日 (因为 Sat 不算工作日但 Mon 算)。"""
        assert business_days_diff(date(2026, 7, 11), date(2026, 7, 13)) == 1

    def test_reverse_direction(self):
        """Tue → Mon → -1。"""
        assert business_days_diff(date(2026, 7, 7), date(2026, 7, 6)) == -1

    def test_fri_to_prev_mon_negative_one(self):
        """Fri → 上周一 → -4 (Tue=1, Wed=1, Thu=1, Fri=1 → wait 算清楚)。"""
        # 实际: Fri 是 7/10, 上周一是 7/6; 从 7/10 到 7/6 反向 = -4
        assert business_days_diff(date(2026, 7, 10), date(2026, 7, 6)) == -4


# ---------------------------------------------------------------------------
# compute_effective_urgent
# ---------------------------------------------------------------------------
class TestComputeEffectiveUrgent:
    """所有 today 参数显式注入, 不依赖运行时 Asia/Shanghai 当前时间。"""

    def test_no_deadline_fallback_zero(self):
        assert compute_effective_urgent(None, fallback_urgent=0, today=date(2026, 7, 6)) == 0

    def test_no_deadline_fallback_one(self):
        """legacy: 无 deadline + urgent=1 → 仍视为紧急。"""
        assert compute_effective_urgent(None, fallback_urgent=1, today=date(2026, 7, 6)) == 1

    def test_deadline_today_is_urgent(self):
        assert compute_effective_urgent("2026-07-06", 0, today=date(2026, 7, 6)) == 1

    def test_deadline_tomorrow_is_urgent(self):
        assert compute_effective_urgent("2026-07-07", 0, today=date(2026, 7, 6)) == 1

    def test_deadline_day_after_tomorrow_not_urgent(self):
        assert compute_effective_urgent("2026-07-08", 0, today=date(2026, 7, 6)) == 0

    def test_deadline_one_week_not_urgent(self):
        assert compute_effective_urgent("2026-07-13", 0, today=date(2026, 7, 6)) == 0

    def test_deadline_overdue_is_urgent(self):
        """截止日期已过 → 紧急 (overdue)。"""
        assert compute_effective_urgent("2026-07-01", 0, today=date(2026, 7, 6)) == 1

    def test_deadline_far_past_is_urgent(self):
        assert compute_effective_urgent("2025-01-01", 0, today=date(2026, 7, 6)) == 1

    def test_deadline_on_saturday_rolls_to_monday(self):
        """今天 Mon, 截止 Sat (7/11) → 顺延到 下周一 (7/13) → 1 周 = 5 业务日 → 不紧急。"""
        # Sat rolls forward to next Mon, so from Mon (7/6) to next Mon (7/13) is 5 business days
        assert compute_effective_urgent("2026-07-11", 0, today=date(2026, 7, 6)) == 0

    def test_deadline_on_sunday_rolls_to_monday(self):
        """今天 Mon, 截止 Sun (7/12) → 顺延到 下周一 (7/13) → 1 周 = 5 业务日 → 不紧急。"""
        # Sun rolls forward to next Mon, so from Mon (7/6) to next Mon (7/13) is 5 business days
        assert compute_effective_urgent("2026-07-12", 0, today=date(2026, 7, 6)) == 0

    def test_deadline_on_saturday_from_friday_is_urgent(self):
        """今天 Fri (7/10), 截止 Sat (7/11) → 顺延到 Mon (7/13) → 1 业务日 → 紧急。"""
        assert compute_effective_urgent("2026-07-11", 0, today=date(2026, 7, 10)) == 1

    def test_deadline_on_sunday_from_friday_is_urgent(self):
        """今天 Fri (7/10), 截止 Sun (7/12) → 顺延到 Mon (7/13) → 1 业务日 → 紧急。"""
        assert compute_effective_urgent("2026-07-12", 0, today=date(2026, 7, 10)) == 1

    def test_today_on_saturday_treats_today_as_monday(self):
        """今天 Sat (7/11) → effective_today = Mon (7/13), deadline Mon (7/13) → 0 业务日 → 紧急。"""
        assert compute_effective_urgent("2026-07-13", 0, today=date(2026, 7, 11)) == 1

    def test_today_on_sunday_treats_today_as_monday(self):
        """今天 Sun (7/12) → effective_today = Mon (7/13), deadline Wed (7/15) → 2 业务日 → 不紧急。"""
        assert compute_effective_urgent("2026-07-15", 0, today=date(2026, 7, 12)) == 0

    def test_today_friday_deadline_next_monday_urgent(self):
        """今天 Fri (7/10), 截止 Mon (7/13) → 1 业务日 → 紧急。"""
        assert compute_effective_urgent("2026-07-13", 0, today=date(2026, 7, 10)) == 1

    def test_today_friday_deadline_next_wednesday_not_urgent(self):
        """今天 Fri (7/10), 截止 Wed (7/15) → 3 业务日 → 不紧急。"""
        assert compute_effective_urgent("2026-07-15", 0, today=date(2026, 7, 10)) == 0

    def test_iso_with_time_prefix_takes_first_10(self):
        """允许 '2026-07-06T10:00:00' 这种完整 ISO datetime。"""
        assert compute_effective_urgent("2026-07-06T10:00:00", 0, today=date(2026, 7, 6)) == 1

    def test_empty_string_no_deadline(self):
        assert compute_effective_urgent("", 0, today=date(2026, 7, 6)) == 0

    def test_whitespace_only_no_deadline(self):
        assert compute_effective_urgent("   ", 0, today=date(2026, 7, 6)) == 0

    def test_invalid_format_no_deadline(self):
        """格式错误 → 视为无 deadline。"""
        assert compute_effective_urgent("2026/07/06", 0, today=date(2026, 7, 6)) == 0
        assert compute_effective_urgent("not-a-date", 0, today=date(2026, 7, 6)) == 0

    def test_invalid_format_uses_fallback(self):
        """格式错误 + legacy fallback=1 → 仍紧急。"""
        assert compute_effective_urgent("not-a-date", 1, today=date(2026, 7, 6)) == 1

    def test_legacy_fallback_ignored_when_deadline_present(self):
        """有 deadline 时, 不论 fallback 多少, 都用 deadline 派生。"""
        # deadline 不紧急 (Wed), fallback=1 → 应输出 0
        assert compute_effective_urgent("2026-07-08", 1, today=date(2026, 7, 6)) == 0
        # deadline 紧急 (today), fallback=0 → 应输出 1
        assert compute_effective_urgent("2026-07-06", 0, today=date(2026, 7, 6)) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
