"""Domain enums: Category / TimeRange / CollectorStatus.

These are the canonical enumeration types used across the data layer.
String-valued (str, Enum) so they serialize cleanly to SQLite TEXT columns
and to JSON API responses.

- Category.from_str() is the canonical string-to-enum parser; it accepts
  any casing / surrounding whitespace and rejects unknowns with
  InvalidParamException (no ValueError leakage to callers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from backend.exceptions import InvalidParamException


class Category(str, Enum):
    """Top-level hotspot domain categories."""

    AI = "ai"
    SECURITY = "security"
    FINANCE = "finance"
    STARTUP = "startup"
    BID = "bid"
    GITHUB = "github"
    # Phase 25 P1: IT/科技 分类 (Solidot/IT之家/稀土掘金/酷安 等)
    TECH = "tech"

    @classmethod
    def from_str(cls, s: str) -> "Category":
        """Parse a free-form string into a Category.

        Steps: strip surrounding whitespace, lowercase, then exact match
        against any member's value. Raises InvalidParamException on
        unknown input (do NOT raise raw ValueError — the API contract is
        uniform HotspotException subclasses).
        """
        if not isinstance(s, str):
            raise InvalidParamException(
                f"category must be a string, got {type(s).__name__}"
            )
        normalized = s.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(repr(m.value) for m in cls)
        raise InvalidParamException(
            f"unknown category {s!r}; valid values: {valid}"
        )


class TimeRange(str, Enum):
    """Supported look-back windows for hotspot queries.

    Phase 35 变更: ``start_datetime()`` 替代原 ``to_hours()`` 做过滤
    起点。**D7 改为「本周周一 00:00」** (而非 now-7d), 与用户描述
    的「资讯 7 天一个循环, 默认从周一开始」语义对齐。其余窗口保留
    相对 hours 语义。
    """

    H24 = "24h"
    D3 = "3d"
    D7 = "7d"
    D30 = "30d"

    def to_hours(self) -> int:
        """Return the window size in hours.

        保留做向后兼容 (测试 / 调度任务)。新代码请用 ``start_datetime()``。
        """
        mapping = {
            TimeRange.H24: 24,
            TimeRange.D3: 72,
            TimeRange.D7: 168,
            TimeRange.D30: 720,
        }
        return mapping[self]

    def start_datetime(self) -> datetime:
        """Return the start ``datetime`` for the filter window.

        始终返回 **tz-aware UTC** datetime (与 ingested_at 列存储的
        ``datetime.now(timezone.utc).isoformat()`` 格式可直接比较)。

        Phase 39 调整: H24 / D3 改为「基于日历日」语义, 与用户的「资讯每周归档」对齐。
        - H24: 今日 00:00 UTC (calendar day, 不再是滚动 24h)
        - D3 : 今日 - 2 天 00:00 UTC (3 个日历日: 前 2 日 + 今日)
        - D7 : 本周周一 00:00 UTC (calendar week, 符合「资讯 7 天一个循环」)
        - D30: now_utc - 30d (滚动 30 天, 暂未改为日历月)
        """
        now_utc = datetime.now(timezone.utc)
        today_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        if self == TimeRange.H24:
            return today_midnight
        if self == TimeRange.D3:
            return today_midnight - timedelta(days=2)
        if self == TimeRange.D7:
            monday = today_midnight - timedelta(days=today_midnight.weekday())
            return monday
        if self == TimeRange.D30:
            return now_utc - timedelta(days=30)
        raise ValueError(f"unknown time range: {self}")


class CollectorStatus(str, Enum):
    """Outcome of a single collector run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


__all__ = ["Category", "TimeRange", "CollectorStatus"]
