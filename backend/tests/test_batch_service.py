"""Phase 28 批次计算单元测试 (纯函数, 不依赖 DB).

覆盖场景
--------
- get_batch_no: 边界 (HISTORY_START_DATE 当天, 边界前, 跨批次, 跨多年)
- get_batch_range: 起始边界, 异常 batch_no (< 1)
- get_current_batch_no: 当前时间所属批次号
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.batch_service import (
    HISTORY_START_DATE,
    get_batch_no,
    get_batch_range,
    get_current_batch_no,
)


# ---------------------------------------------------------------------------
# get_batch_no
# ---------------------------------------------------------------------------
class TestGetBatchNo:
    def test_history_start_date_is_batch_1(self):
        """HISTORY_START_DATE 自身 (周一 00:00) = batch 1."""
        ts = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 1

    def test_same_batch_mid_week(self):
        """同一批次内任意时间都返回 1."""
        for day_offset in range(7):
            ts = datetime(2026, 7, 6, tzinfo=timezone.utc) + timedelta(days=day_offset, hours=12)
            assert get_batch_no(ts) == 1, f"day_offset={day_offset} should be batch 1"

    def test_next_monday_is_batch_2(self):
        """下周一 00:00 = batch 2."""
        ts = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 2

    def test_sunday_2359_is_previous_batch(self):
        """周日 23:59 仍是上一批次 (因为 [start, end) 半开区间)."""
        ts = datetime(2026, 7, 12, 23, 59, 59, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 1

    def test_monday_0000_is_new_batch(self):
        """周一 00:00:00 是新批次起点."""
        ts = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 2

    def test_before_history_start_fallback_to_1(self):
        """HISTORY_START_DATE 之前的时间回退到 batch 1."""
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 1

    def test_third_batch(self):
        """14 天后 = batch 3."""
        ts = datetime(2026, 7, 20, 0, 0, 0, tzinfo=timezone.utc)
        assert get_batch_no(ts) == 3

    def test_naive_datetime_treated_as_utc(self):
        """naive datetime 视为 UTC."""
        ts = datetime(2026, 7, 6, 0, 0, 0)  # no tzinfo
        assert get_batch_no(ts) == 1

    def test_cst_time_5am_monday_is_utc_9pm_sunday(self):
        """Asia/Shanghai 周一 05:00 = UTC 周日 21:00 → 仍在 batch 1."""
        # 周一 05:00 CST = UTC 周日 21:00, 距 HISTORY_START_DATE 仅 21 小时
        from datetime import timezone as tz, timedelta as td
        cst = tz(td(hours=8))
        ts = datetime(2026, 7, 13, 5, 0, 0, tzinfo=cst)
        assert ts.astimezone(tz.utc).isoformat() == "2026-07-12T21:00:00+00:00"
        assert get_batch_no(ts) == 1


# ---------------------------------------------------------------------------
# get_batch_range
# ---------------------------------------------------------------------------
class TestGetBatchRange:
    def test_batch_1_range(self):
        s, e = get_batch_range(1)
        assert s.isoformat() == "2026-07-06T00:00:00+00:00"
        assert e.isoformat() == "2026-07-13T00:00:00+00:00"

    def test_batch_2_range(self):
        s, e = get_batch_range(2)
        assert s.isoformat() == "2026-07-13T00:00:00+00:00"
        assert e.isoformat() == "2026-07-20T00:00:00+00:00"

    def test_batch_100_range(self):
        s, e = get_batch_range(100)
        # 99 * 7 = 693 days after 2026-07-06
        expected_start = HISTORY_START_DATE + timedelta(days=99 * 7)
        expected_end = expected_start + timedelta(days=7)
        assert s.date() == expected_start
        assert e.date() == expected_end

    def test_zero_batch_raises(self):
        with pytest.raises(ValueError, match="batch_no must be >= 1"):
            get_batch_range(0)

    def test_negative_batch_raises(self):
        with pytest.raises(ValueError, match="batch_no must be >= 1"):
            get_batch_range(-5)

    def test_range_is_half_open(self):
        """end - start = 7 天 整."""
        s, e = get_batch_range(5)
        assert (e - s) == timedelta(days=7)


# ---------------------------------------------------------------------------
# get_current_batch_no
# ---------------------------------------------------------------------------
class TestGetCurrentBatchNo:
    def test_returns_positive_int(self):
        bn = get_current_batch_no()
        assert isinstance(bn, int)
        assert bn >= 1

    def test_consistent_with_get_batch_no(self):
        """current 与传入 now() 的结果一致."""
        bn = get_current_batch_no()
        bn2 = get_batch_no(datetime.now(timezone.utc))
        assert bn == bn2
