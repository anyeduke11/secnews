"""Pydantic v2 data models for the hotspot domain.

Conventions
-----------
- All datetime fields MUST be tz-aware (UTC). Construct with
  ``datetime.now(timezone.utc)`` or equivalent. Repository layer
  persists them as ``.isoformat()`` strings and parses them back with
  ``datetime.fromisoformat()``.
- ``url`` is a ``pydantic.networks.HttpUrl``. In Pydantic v2 ``HttpUrl``
  is a ``Url`` object, not a bare ``str``; ``model_dump(mode="json")``
  serializes it as a plain string, and ``str(item.url)`` returns the
  string form for direct SQLite writes. Use ``model_dump(mode="json")``
  when handing the model to JSON APIs.
- ``use_enum_values=False`` keeps ``Category`` / ``CollectorStatus`` as
  enum members on the model instance (callers can do ``item.category ==
  Category.AI``). For DB writes the repository explicitly calls
  ``.value`` to get the string.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from backend.domain.enums import Category, CollectorStatus


def _require_tz_aware(v: datetime) -> datetime:
    """Reject naive ``datetime`` instances — the data layer requires UTC."""
    if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
        raise ValueError("datetime must be timezone-aware (use timezone.utc)")
    return v


# ---------------------------------------------------------------------------
# HotspotItem — SPEC §3.1, all 14 fields.
# ---------------------------------------------------------------------------
class HotspotItem(BaseModel):
    """A single hotspot/news entry, normalized across all collectors."""

    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=False)

    # Identity / source
    id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=500)
    summary: str | None = Field(None, max_length=500)
    source: str = Field(..., min_length=1, max_length=50)
    url: HttpUrl
    category: Category

    # Timestamps (must be tz-aware UTC; see module docstring)
    published_at: datetime
    fetched_at: datetime
    # P1.6: 当 published_at 由 naive 字符串(strptime / 无 tz 的 HTML 提取)
    # 经过 ``.replace(tzinfo=timezone.utc)`` 显式假定 UTC 时为 True;
    # 由 ``datetime.fromtimestamp(..., tz=utc)`` / ISO 携带时区得到的为 False。
    # 仅供审计与排查; 不影响序列化。
    published_at_tz_assumed: bool = False
    # Phase 15: ingested_at = 录入时间(列表排序/过滤用)。
    # - 新抓取的资讯 ingested_at = now()
    # - 已录入的老资讯(本次迁移前) ingested_at = published_at
    #   让历史老旧资讯按发布时间显示在历史位置,而不是显示在最新录入位置。
    # - published_at 保留原语义(文章真实发布时间),前端卡片继续显示。
    ingested_at: datetime | None = None
    # Phase 20: bid_status 标讯状态(仅 category=bid 有效)
    # 可选值: 招标中 / 中标 / 变更 / 终止 / 成交 / 询价 / 比选 / 其他
    # 由 :func:`backend.collectors.bid_status.extract_bid_status` 标题正则提取
    bid_status: str | None = Field(None, max_length=20)
    # Phase 8 (v1.3.0): 标讯地区(仅 category=bid 有效)
    # 由 :func:`_extract_region` 从标题/内容解析
    region: str | None = Field(None, max_length=30)

    @field_validator("published_at", "fetched_at", "ingested_at")
    @classmethod
    def _validate_tz(cls, v: datetime) -> datetime:
        if v is None:
            return v
        return _require_tz_aware(v)

    # Popularity / fallback signal
    score: int | None = Field(None, ge=0, le=100)
    is_fallback: bool = False

    # Quality pipeline
    quality_score: int = Field(100, ge=0, le=100)
    quality_flags: list[str] = Field(default_factory=list)
    quality_checked_at: datetime | None = None
    url_check_status: Literal["pending", "verified", "mismatch", "skipped", "unreachable"] | None = None

    # ---- helpers -----------------------------------------------------------
    def url_str(self) -> str:
        """Return ``url`` as a plain ``str`` for SQLite storage / logging."""
        return str(self.url)


# ---------------------------------------------------------------------------
# TrendPoint — hourly trend bucket, one row per (hours_ago, category).
# ---------------------------------------------------------------------------
class TrendPoint(BaseModel):
    """One hourly bucket in the trend heatmap.

    ``hours_ago`` 的上界必须与 ``/api/trends`` 声明的 ``hours ≤ 168`` 一致：
    旧值 ``le=23`` 把数据层锁死在 24 桶, 而 ``trend_snapshots.hours_ago`` 本身
    没有 CHECK 约束 → 超出 24h 的请求只能被 service 补成假 0, "没有快照"于是被
    渲染成"零资讯" (实测 ``/api/trends?hours=168`` 168 点仅 19 个非零)。
    """

    model_config = ConfigDict(use_enum_values=False)

    label: str
    hours_ago: int = Field(..., ge=0, le=167)
    category: str
    count: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# CollectionRun — audit record of one collector invocation.
# ---------------------------------------------------------------------------
class CollectionRun(BaseModel):
    """Audit row written at the end of each collector run."""

    model_config = ConfigDict(use_enum_values=False)

    id: int | None = None
    category: str
    started_at: datetime
    finished_at: datetime | None = None
    status: CollectorStatus
    item_count: int = 0
    fallback_count: int = 0
    error_msg: str | None = None


__all__ = ["CollectionRun", "HotspotItem", "TrendPoint"]
