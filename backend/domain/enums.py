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
from zoneinfo import ZoneInfo

from backend.exceptions import InvalidParamException

# Phase 48: D7 / H24 / D3 改用 Shanghai TZ, 与 current_week_start() / RecencyGate
# 的"本周一 00:00 Asia/Shanghai" 语义一致, 修复"上海 0 点未自动归档" 8h 错位。
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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

        Phase 48: H24 / D3 / D7 改为基于 Shanghai TZ 的「日历日/周」语义
        (与用户的「资讯每周归档从上海周一开始」对齐, 与 current_week_start()
        / RecencyGate 一致 — 之前用 UTC 与 RecencyGate 差 8h, 跨周末时差 1 天)。

        - H24: Shanghai 今日 00:00 转 UTC
        - D3 : Shanghai 今日 - 2 天 00:00 转 UTC (3 个日历日: 前 2 日 + 今日)
        - D7 : Shanghai 本周一 00:00 转 UTC (calendar week, 符合「资讯 7 天一个循环」)
        - D30: now_utc - 30d (滚动 30 天, 暂未改为日历月)
        """
        now_utc = datetime.now(timezone.utc)
        now_sh = now_utc.astimezone(SHANGHAI_TZ)
        today_sh_midnight = now_sh.replace(hour=0, minute=0, second=0, microsecond=0)
        if self == TimeRange.H24:
            return today_sh_midnight.astimezone(timezone.utc)
        if self == TimeRange.D3:
            return (today_sh_midnight - timedelta(days=2)).astimezone(timezone.utc)
        if self == TimeRange.D7:
            monday_sh = today_sh_midnight - timedelta(days=today_sh_midnight.weekday())
            return monday_sh.astimezone(timezone.utc)
        if self == TimeRange.D30:
            return now_utc - timedelta(days=30)
        raise ValueError(f"unknown time range: {self}")


class CollectorStatus(str, Enum):
    """Outcome of a single collector run."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


__all__ = ["Category", "TimeRange", "CollectorStatus"]
