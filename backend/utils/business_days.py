"""Phase 46 业务日工具 — 用于「截止日期 → 紧急」自动判断。

设计原则
--------
- **过滤周六日**: 周六/周日不算「工作日」(即 截止日期落在周末 → 顺延到下周一)。
- **今天落在周末**: 周六/周日时, 「今天」= 即将到来的周一 (而非周六/周日本身)。
- **紧急阈值**: 截止日期 ≤ 1 个业务日 (含今天 / 明天 / 顺延后 ≤ 1 业务日) → 紧急。
- **过期**: 截止日期 < 有效今天 → 紧急 (overdue)。
- **无截止日期**: 非紧急 (除非 fallback 标记为 1, 用于 legacy 数据兼容)。

时区
----
- 用 ``Asia/Shanghai`` (与 Phase 42 跨端同步一致, 用户决策 Q2)。
- Python ``datetime.now(ZoneInfo("Asia/Shanghai")).date()``。
- 截止日期存 'YYYY-MM-DD' (无时区), 直接当 Shanghai date 用。

API
---
- :func:`next_business_day`  : 给定日期, 若为周末 → 下周一。
- :func:`business_days_diff` : 两个日期之间的工作日数 (排除 Sat/Sun)。
- :func:`compute_effective_urgent` : 核心入口, deadline (ISO 字符串 or None) → 0/1。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# 日期工具
# ---------------------------------------------------------------------------
def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    """'YYYY-MM-DD' → date; 其他格式 / None / 解析失败 → None。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    # 仅取前 10 位 (允许 '2026-07-15T10:00:00...' 这种 ISO datetime)
    s = s[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _to_shanghai_date(dt: datetime) -> date:
    """把任意 tz-aware datetime 转 Shanghai date; tz-naive → 视为 Shanghai。"""
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(SHANGHAI_TZ).date()


def next_business_day(d: date) -> date:
    """如果 d 是 Sat(5)/Sun(6), 返回下周一; 否则原样返回。"""
    # weekday(): Mon=0, Sun=6
    if d.weekday() == 5:  # Saturday
        from datetime import timedelta
        return d + timedelta(days=2)
    if d.weekday() == 6:  # Sunday
        from datetime import timedelta
        return d + timedelta(days=1)
    return d


def business_days_diff(start: date, end: date) -> int:
    """``start`` 与 ``end`` 之间的工作日数 (Mon-Fri 计数)。

    - 返回 ``end - start`` 的工作日 (排除 Sat/Sun)。
    - 端点约定: 包含 end, 排除 start。
    - 例: start=Mon, end=Mon → 0
    - 例: start=Mon, end=Tue → 1
    - 例: start=Mon, end=Wed → 2
    - 例: start=Mon, end=Fri → 4
    - 例: start=Fri, end=Mon(下周一) → 1 (跨周末不计入)
    - 例: start=Mon, end=前一周 Fri → -4
    - 例: start=end(同一天) → 0
    """
    if start == end:
        return 0
    from datetime import timedelta
    a, b = (start, end) if start < end else (end, start)
    sign = 1 if end > start else -1
    # Count Mon-Fri in (a, b]
    count = 0
    cur = a
    while cur < b:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            count += 1
    return count * sign


# ---------------------------------------------------------------------------
# 核心: 截止日期 → 紧急 (0/1)
# ---------------------------------------------------------------------------
def compute_effective_urgent(
    deadline_iso: Optional[str],
    fallback_urgent: int = 0,
    today: Optional[date] = None,
) -> int:
    """根据截止日期计算 effective_urgent (0/1)。

    Parameters
    ----------
    deadline_iso : 'YYYY-MM-DD' (允许 'YYYY-MM-DDTHH:MM:SS' 取前 10 位), 或 None
    fallback_urgent : 当 deadline_iso 为 None 时, 用此值 (兼容 legacy 数据)
    today : 用于测试注入的「今天」; 运行时省略 → Asia/Shanghai 当前日期

    Returns
    -------
    0 = 不紧急, 1 = 紧急
    """
    deadline = _parse_iso_date(deadline_iso)
    if deadline is None:
        # 无截止日期 → fallback (legacy 数据保留原 urgent 值)
        return 1 if int(fallback_urgent or 0) else 0

    if today is None:
        today = datetime.now(SHANGHAI_TZ).date()

    # 今天和截止日期都先「顺延到工作日」 (周末视为休息)
    effective_today = next_business_day(today)
    effective_deadline = next_business_day(deadline)

    # 过期: effective_deadline < effective_today → 紧急
    if effective_deadline < effective_today:
        return 1

    # 工作日差 (从 effective_today 到 effective_deadline 的工作日数)
    # 0 = 同一天 (今天) → 紧急
    # 1 = 明天 → 紧急
    # 2+ = 不紧急
    diff = business_days_diff(effective_today, effective_deadline)
    return 1 if diff <= 1 else 0


# ---------------------------------------------------------------------------
# Phase 47: 本周一起点 — 资讯/标讯时效硬门禁阈值
# ---------------------------------------------------------------------------
def current_week_start(today: Optional[datetime | date] = None) -> datetime:
    """返回「本周周一 00:00:00 Asia/Shanghai」tz-aware datetime。

    用途: 资讯/标讯时效硬门禁 (Phase 47 RecencyGate) 阈值。
    - ``published_at < current_week_start()`` → 视为历史资讯, 拒绝入库。
    - 缺失 published_at → 拒绝 (无法验证时效, 宁缺毋滥)。
    - 用 Shanghai 时区(用户/业务视角), 与 Phase 42/46 跨端同步一致。

    Parameters
    ----------
    today : 用于测试注入的「今天」; 接受 ``datetime`` (tz-naive 当作 Shanghai)
            或 ``date``。运行时省略 → Asia/Shanghai 当前时间。

    Returns
    -------
    tz-aware datetime (Asia/Shanghai), 时分秒 = 00:00:00
    例: today=2026-07-10 (Fri) → return=2026-07-06 00:00:00+08:00
       today=2026-07-06 (Mon) → return=2026-07-06 00:00:00+08:00
       today=2026-07-05 (Sun) → return=2026-06-29 00:00:00+08:00 (上周一)

    Notes
    -----
    Phase 48 之后: 与 :meth:`TimeRange.D7.start_datetime()` 语义一致
    (都是 Shanghai 本周一 00:00), 不再差 8h, 跨周末时不再错位 1 天。
    """
    if today is None:
        today = datetime.now(SHANGHAI_TZ)
    if isinstance(today, datetime):
        d = today.date() if today.tzinfo is None else today.astimezone(SHANGHAI_TZ).date()
    else:
        d = today
    monday = d - timedelta(days=d.weekday())
    return datetime.combine(monday, time(0, 0, 0), tzinfo=SHANGHAI_TZ)


__all__ = [
    "SHANGHAI_TZ",
    "next_business_day",
    "business_days_diff",
    "compute_effective_urgent",
    "current_week_start",
]
