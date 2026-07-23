"""v1.7 Phase 3/4 — 简报 (Digest) 服务.

Phase 3 (读取状态):
- ``has_unread_digest()`` — 判断当日是否有未读简报
- ``mark_digest_read(read_at)`` — 标记简报已读

Phase 4 (简报生成):
- ``generate_daily_digest()`` — 生成昨日简报, 写入 digests 表
- ``create_digest(...)`` — 通用简报创建 (兼容 Phase 3 测试)

设计决策
---------
- ``digests`` 表 (migration 031) 没有 ``read`` 列, 读取状态用 ``kv_cache``
  表 (migration 032) 记录, key=``digest_last_read_at``, value=ISO 时间戳。
- "未读" 定义: digests 表中存在 created_at >= 今日 00:00 (Shanghai) 的简报,
  且 kv_cache 中 ``digest_last_read_at`` < 该简报的 created_at。
- 时区: 使用 Asia/Shanghai (与 RecencyGate / TimeRange 对齐, Phase 48)。
- Phase 4 简报: 取昨日 [yesterday_00:00, today_00:00) Shanghai 的 hotspots,
  按 score DESC 取 Top 3, 摘要 + item_ids 写入 digests 表。
- ID 格式: ``digest-YYYY-MM-DD`` (Shanghai 日期), 同日重复生成覆盖。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.repository.db import get_connection
from backend.repository.digest_repo import DigestRepository, digest_repo

# kv_cache key: 记录用户最后一次标记简报已读的时间
_KV_DIGEST_LAST_READ = "digest_last_read_at"

# 时区: Asia/Shanghai (UTC+8)
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_start_shanghai_utc() -> datetime:
    """返回上海时区今日 00:00 对应的 UTC datetime。

    例: 上海 2026-07-23 15:38 → 今日 00:00 上海 = 2026-07-22 16:00 UTC。
    """
    now_shanghai = datetime.now(_SHANGHAI_TZ)
    today_start_shanghai = now_shanghai.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return today_start_shanghai.astimezone(timezone.utc)


def has_unread_digest() -> bool:
    """判断当日是否有未读简报。

    Returns
    -------
    bool
        True 如果 digests 表中存在 created_at >= 今日上海 00:00 的简报,
        且用户尚未标记已读 (kv_cache digest_last_read_at < 简报 created_at)。
    """
    today_start = _today_start_shanghai_utc().isoformat()
    conn = get_connection()

    # 查找今日创建的简报
    row = conn.execute(
        "SELECT MAX(created_at) AS latest FROM digests WHERE created_at >= ?",
        (today_start,),
    ).fetchone()

    latest_digest_at = row["latest"] if row else None
    if not latest_digest_at:
        return False  # 今日无简报

    # 查找用户最后标记已读的时间
    read_row = conn.execute(
        "SELECT value FROM kv_cache WHERE key = ?",
        (_KV_DIGEST_LAST_READ,),
    ).fetchone()

    if not read_row:
        return True  # 从未标记已读 → 有未读

    last_read_at = read_row["value"]
    # 如果最后读取时间 < 最新简报创建时间 → 未读
    return last_read_at < latest_digest_at


def mark_digest_read(read_at: datetime | None = None) -> None:
    """标记简报已读, 写入 kv_cache。

    Parameters
    ----------
    read_at:
        标记读取的时间戳, 默认当前 UTC 时间。
    """
    ts = (read_at or _now_utc()).isoformat()
    now = _now_utc().isoformat()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO kv_cache (key, value, expires_at, created_at, updated_at)
        VALUES (?, ?, NULL, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (_KV_DIGEST_LAST_READ, ts, now, now),
    )


def create_digest(
    digest_id: str,
    period: str = "daily",
    summary: str = "",
    item_ids: list[str] | None = None,
) -> dict:
    """创建一条简报记录 (兼容 Phase 3 测试, 内部委托给 DigestRepository).

    Returns
    -------
    dict
        创建的简报记录 (含解析后的 ``item_ids`` list).
    """
    return DigestRepository().add(
        digest_id=digest_id,
        period=period,
        summary=summary,
        item_ids=item_ids,
    )


# ---------------------------------------------------------------------------
# Phase 4: 简报生成
# ---------------------------------------------------------------------------
def _yesterday_window_shanghai() -> tuple[datetime, datetime, str]:
    """返回昨日简报时间窗口 (Shanghai 时区).

    Returns
    -------
    tuple
        ``(yesterday_start_utc, today_start_utc, yesterday_date_str)``
        - ``yesterday_start_utc``: 昨日 00:00 Shanghai 对应的 UTC datetime
        - ``today_start_utc``: 今日 00:00 Shanghai 对应的 UTC datetime
        - ``yesterday_date_str``: 昨日 Shanghai 日期 ``"YYYY-MM-DD"``
    """
    now_shanghai = datetime.now(_SHANGHAI_TZ)
    today_start_shanghai = now_shanghai.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_start_shanghai = today_start_shanghai - timedelta(days=1)
    return (
        yesterday_start_shanghai.astimezone(timezone.utc),
        today_start_shanghai.astimezone(timezone.utc),
        yesterday_start_shanghai.strftime("%Y-%m-%d"),
    )


def generate_daily_digest(
    top_n: int = 3,
    repo: Optional[DigestRepository] = None,
) -> dict:
    """生成昨日 (Shanghai) 简报, 写入 digests 表.

    流程
    -----
    1. 计算 [昨日 00:00, 今日 00:00) Shanghai 时间窗口
    2. 查询窗口内 hotspots (复用 HotspotRepository.query_in_range)
    3. 按 score DESC 取 Top N (默认 3)
    4. 生成摘要文本 + item_ids
    5. 用 ``digest-YYYY-MM-DD`` 作为 ID upsert 到 digests 表

    Parameters
    ----------
    top_n:
        Top N 文章数, 默认 3.
    repo:
        可选 DigestRepository 注入 (测试用).

    Returns
    -------
    dict
        生成的简报记录: ``{id, period, summary, item_ids, created_at, count}``
        - ``count``: 窗口内文章总数 (供前端 "昨日共 N 篇" 显示)

    验收 4: "每日 08:00 生成简报"
      → 调度器 (scheduler) 每天 08:00 Shanghai 调用本函数;
        本函数本身不依赖时间触发, 只保证被调用时正确生成昨日简报。
    """
    from backend.repository.hotspot_repo import HotspotRepository

    effective_top_n = max(1, min(top_n, 10))
    yesterday_start, today_start, yesterday_str = _yesterday_window_shanghai()

    # 查询昨日 hotspots (limit 留余量以拿到 Top N)
    hotspot_repo = HotspotRepository()
    items, _ = hotspot_repo.query_in_range(
        start=yesterday_start,
        end=today_start,
        limit=50,
    )

    # 按 score DESC 取 Top N (score 为 None 视为 0)
    sorted_items = sorted(items, key=lambda x: x.score or 0, reverse=True)
    top = sorted_items[:effective_top_n]
    top_titles = ", ".join(i.title for i in top) if top else "(无)"
    summary = (
        f"昨日共 {len(items)} 篇文章，Top {len(top)}: {top_titles}"
    )

    digest_id = f"digest-{yesterday_str}"
    item_ids = [i.id for i in top]
    repository = repo or digest_repo
    record = repository.add(
        digest_id=digest_id,
        period="daily",
        summary=summary,
        item_ids=item_ids,
    )
    # 补充 count 字段 (前端展示用)
    record["count"] = len(items)
    return record


__all__ = [
    "has_unread_digest",
    "mark_digest_read",
    "create_digest",
    "generate_daily_digest",
]
