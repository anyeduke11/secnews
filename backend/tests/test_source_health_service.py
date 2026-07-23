"""v1.7 Phase 4 — SourceHealthService 测试.

覆盖:
- check_health: green / yellow / red 三档判定
- baseline=0 边界: 新源 (recent>0) → green, 死源 (recent=0) → red
- check_all_health: 多源聚合 + 严重度排序
- list_all_sources / health_summary
- 验收 3: 数据源健康状态准确 (green/yellow/red)

测试方法: 直接向 hotspots 表插入带 ingested_at 的行, 控制 24h / 7d 窗口内的产出数。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.services.source_health_service import (
    check_all_health,
    check_health,
    health_summary,
    list_all_sources,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_source_health.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


_UTC = timezone.utc


def _insert_hotspot(hid: str, source: str, ingested_at: datetime) -> None:
    """向 hotspots 表插入一行 (带指定 ingested_at)."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid,
            f"{source} item {hid}",
            "",
            source,
            f"https://example.com/{hid}",
            "ai",
            ingested_at.isoformat(),
            50,
            ingested_at.isoformat(),
            0,
            100,
            "[]",
            ingested_at.isoformat(),
        ),
    )


def _hours_ago(h: int) -> datetime:
    return datetime.now(_UTC) - timedelta(hours=h)


def _days_ago_at(d: int, hour_offset_from_now: int = 0) -> datetime:
    """N 天前的同一时刻 (可加小时偏移).

    用于在 baseline 窗口 [now-7d-24h, now-24h) 内插数据:
    - d=2 → 2 天前 (在 baseline 窗口内)
    - d=8 → 8 天前 (在 baseline 窗口外)
    """
    return datetime.now(_UTC) - timedelta(days=d, hours=hour_offset_from_now)


# ---------------------------------------------------------------------------
# check_health — 基础判定
# ---------------------------------------------------------------------------
def _seed_baseline_days(source: str, articles_per_day: int, days: int = 6) -> None:
    """在 baseline 窗口 [now-7d-24h, now-24h) 内, 每天插 articles_per_day 篇.

    用 d=2..(days+1) 共 `days` 个不同日期, 避开 24h 窗口和 baseline 边界.
    """
    for day in range(2, 2 + days):
        day_moment = datetime.now(_UTC) - timedelta(days=day)
        for i in range(articles_per_day):
            _insert_hotspot(f"bl-{source}-{day}-{i}", source, day_moment)


class TestCheckHealth:
    def test_no_data_returns_red(self, temp_db):
        """源完全无产出 → baseline=0, recent=0 → red."""
        result = check_health("ghost")
        assert result["source"] == "ghost"
        assert result["status"] == "red"
        assert result["recent_24h"] == 0
        assert result["baseline_7d_avg"] == 0.0
        assert result["ratio"] is None

    def test_new_source_with_recent_only_is_green(self, temp_db):
        """新源: 24h 内有产出, 7d baseline 窗口内无历史 → baseline=0, recent>0 → green."""
        _insert_hotspot("h1", "newsrc", _hours_ago(2))
        result = check_health("newsrc")
        assert result["status"] == "green"
        assert result["recent_24h"] == 1
        assert result["baseline_7d_avg"] == 0.0
        assert result["ratio"] is None

    def test_green_within_30pct(self, temp_db):
        """recent 与 baseline 偏差 < 30% → green.

        baseline 窗口 6 天 × 10 篇 = 60, baseline = 60/7 ≈ 8.571
        24h 内 9 篇, ratio = |9-8.571|/8.571 ≈ 0.05 < 0.3 → green
        """
        _seed_baseline_days("src-green", articles_per_day=10, days=6)
        for i in range(9):
            _insert_hotspot(f"new-{i}", "src-green", _hours_ago(1))

        result = check_health("src-green")
        assert result["status"] == "green", f"expected green, got {result}"
        assert result["recent_24h"] == 9
        assert abs(result["baseline_7d_avg"] - 60.0 / 7.0) < 0.01
        assert result["ratio"] is not None
        assert result["ratio"] < 0.3

    def test_yellow_30_to_60pct(self, temp_db):
        """recent 与 baseline 偏差 30-60% → yellow.

        baseline = 60/7 ≈ 8.571, 24h = 5 篇,
        ratio = |5-8.571|/8.571 ≈ 0.417 ∈ [0.3, 0.6) → yellow
        """
        _seed_baseline_days("src-yellow", articles_per_day=10, days=6)
        for i in range(5):
            _insert_hotspot(f"new-{i}", "src-yellow", _hours_ago(1))

        result = check_health("src-yellow")
        assert result["status"] == "yellow", f"expected yellow, got {result}"
        assert result["recent_24h"] == 5
        assert 0.3 <= result["ratio"] < 0.6

    def test_red_above_60pct(self, temp_db):
        """recent 与 baseline 偏差 >= 60% → red.

        baseline = 60/7 ≈ 8.571, 24h = 0 篇,
        ratio = 8.571/8.571 = 1.0 >= 0.6 → red
        """
        _seed_baseline_days("src-red", articles_per_day=10, days=6)
        # 24h 内不插入任何行

        result = check_health("src-red")
        assert result["status"] == "red", f"expected red, got {result}"
        assert result["recent_24h"] == 0
        assert result["ratio"] >= 0.6

    def test_red_when_recent_far_exceeds_baseline(self, temp_db):
        """recent 远高于 baseline (异常飙升) → red.

        baseline = 12/7 ≈ 1.714, 24h = 10 篇,
        ratio = |10-1.714|/1.714 ≈ 4.83 >= 0.6 → red
        """
        _seed_baseline_days("src-spike", articles_per_day=2, days=6)
        for i in range(10):
            _insert_hotspot(f"new-{i}", "src-spike", _hours_ago(1))

        result = check_health("src-spike")
        assert result["status"] == "red", f"expected red, got {result}"
        assert result["ratio"] >= 0.6

    def test_return_shape(self, temp_db):
        """验证返回字段完整."""
        _insert_hotspot("h1", "shp", _hours_ago(1))
        result = check_health("shp")
        for key in ("source", "status", "recent_24h", "baseline_7d_avg",
                    "ratio", "checked_at"):
            assert key in result, f"missing key: {key}"

    def test_only_counts_specified_source(self, temp_db):
        """check_health 只统计指定 source, 不被其他 source 干扰."""
        _insert_hotspot("a1", "alpha", _hours_ago(1))
        _insert_hotspot("b1", "beta", _hours_ago(1))
        assert check_health("alpha")["recent_24h"] == 1
        assert check_health("beta")["recent_24h"] == 1
        assert check_health("gamma")["recent_24h"] == 0


# ---------------------------------------------------------------------------
# list_all_sources
# ---------------------------------------------------------------------------
class TestListAllSources:
    def test_empty_returns_empty_list(self, temp_db):
        assert list_all_sources() == []

    def test_returns_distinct_sorted(self, temp_db):
        _insert_hotspot("h1", "zeta", _hours_ago(1))
        _insert_hotspot("h2", "alpha", _hours_ago(1))
        _insert_hotspot("h3", "zeta", _hours_ago(2))  # 重复
        sources = list_all_sources()
        assert sources == ["alpha", "zeta"]


# ---------------------------------------------------------------------------
# check_all_health
# ---------------------------------------------------------------------------
class TestCheckAllHealth:
    def test_empty_returns_empty(self, temp_db):
        assert check_all_health() == []

    def test_includes_all_sources(self, temp_db):
        _insert_hotspot("h1", "alpha", _hours_ago(1))
        _insert_hotspot("h2", "beta", _hours_ago(1))
        items = check_all_health()
        sources = {it["source"] for it in items}
        assert sources == {"alpha", "beta"}

    def test_sorted_by_severity(self, temp_db):
        """red 在 yellow 前, yellow 在 green 前."""
        # red: baseline 有产出, 24h 无
        _seed_baseline_days("src-red", articles_per_day=10, days=6)
        # yellow: baseline=60/7≈8.57, 24h=5 → ratio≈0.417
        _seed_baseline_days("src-yellow", articles_per_day=10, days=6)
        for i in range(5):
            _insert_hotspot(f"yel-new-{i}", "src-yellow", _hours_ago(1))
        # green: 新源 24h 有产出 (baseline=0)
        _insert_hotspot("g1", "src-green", _hours_ago(1))

        items = check_all_health()
        statuses = [it["status"] for it in items]
        # red 在最前
        assert statuses[0] == "red", f"expected red first, got {statuses}"
        # green 在最后
        assert statuses[-1] == "green", f"expected green last, got {statuses}"
        # yellow 在中间
        assert "yellow" in statuses


# ---------------------------------------------------------------------------
# health_summary
# ---------------------------------------------------------------------------
class TestHealthSummary:
    def test_empty(self, temp_db):
        s = health_summary()
        assert s["total"] == 0
        assert s["green"] == 0
        assert s["yellow"] == 0
        assert s["red"] == 0
        assert "checked_at" in s

    def test_counts(self, temp_db):
        # green: 新源 (24h 有产出, baseline=0)
        _insert_hotspot("g1", "src-green", _hours_ago(1))
        # red: 7d 历史但 24h 无
        _seed_baseline_days("src-red", articles_per_day=10, days=6)

        s = health_summary()
        assert s["total"] == 2
        assert s["green"] == 1, f"expected 1 green, got {s}"
        assert s["red"] == 1
        assert s["yellow"] == 0


# ---------------------------------------------------------------------------
# 验收 3: 数据源健康状态准确 (green/yellow/red)
# ---------------------------------------------------------------------------
class TestAcceptance3SourceHealthAccurate:
    def test_three_tiers_accurate(self, temp_db):
        """验收 3: 三个源分别对应 green / yellow / red, 状态判定准确.

        - green-src:  baseline=60/7≈8.57, 24h=9 → ratio≈0.05 < 0.3 → green
        - yellow-src: baseline=60/7≈8.57, 24h=5 → ratio≈0.417 ∈ [0.3,0.6) → yellow
        - red-src:    baseline=60/7≈8.57, 24h=0 → ratio=1.0 >= 0.6 → red
        """
        # green 源
        _seed_baseline_days("green-src", articles_per_day=10, days=6)
        for i in range(9):
            _insert_hotspot(f"g-new-{i}", "green-src", _hours_ago(1))

        # yellow 源
        _seed_baseline_days("yellow-src", articles_per_day=10, days=6)
        for i in range(5):
            _insert_hotspot(f"y-new-{i}", "yellow-src", _hours_ago(1))

        # red 源 (24h 内无产出)
        _seed_baseline_days("red-src", articles_per_day=10, days=6)

        green = check_health("green-src")
        yellow = check_health("yellow-src")
        red = check_health("red-src")

        assert green["status"] == "green", f"expected green, got {green}"
        assert yellow["status"] == "yellow", f"expected yellow, got {yellow}"
        assert red["status"] == "red", f"expected red, got {red}"

    def test_trend_endpoint_payload_shape(self, temp_db):
        """验收 3 (API 层): /health/trend 返回结构正确 (通过 service 直调验证)."""
        _insert_hotspot("h1", "alpha", _hours_ago(1))
        items = check_all_health()
        assert len(items) == 1
        item = items[0]
        assert item["source"] == "alpha"
        assert item["status"] in {"green", "yellow", "red"}
        assert isinstance(item["recent_24h"], int)
        assert isinstance(item["baseline_7d_avg"], float)
