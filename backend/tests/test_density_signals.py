"""采集密度门禁信号层测试 (density T1).

锁定的契约:
1. get_recent_quality_stats(practice_domains=...): 每源窗口内即时打标
   practice_domain ∈ 关注域的条数 hit_count (含显式 0); hotspots 表无
   practice_domain 列, 打标口径与 hotspot_service 读路径一致
   (classify_practice_domain(tags, title), tags 优先)。
2. 向后兼容: 不传 / 传空 practice_domains → 返回结构与 T4 完全一致
   (仅 {avg_quality, count}, 无 hit_count 键) — T4 既有精确相等断言依赖。
3. get_recent_rejection_stats: 近 N 天每源 {rejections, accepted};
   quality_rejection_log.source_id 列实存源名称 (quality_hook 以
   item.source 落库), 与 hotspots.source 同域直接 GROUP BY;
   时间口径: created_at 空格格式 vs ingested_at ISO-T 格式分别对齐。

执行:
    python -m pytest backend/tests/test_density_signals.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.repository.hotspot_repo import HotspotRepository


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path (全量 migration, 与 test_source_quality_cadence 同模式)。"""
    test_db = tmp_path / "test_density_signals.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_hotspot(
    hid: str,
    source: str,
    *,
    title: str = "item",
    tags: str = "[]",
    quality_score: int = 100,
    published_at: str | None = None,
    ingested_at: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid,
            title,
            "",
            source,
            f"https://example.com/{hid}",
            "ai",
            published_at or (now - timedelta(hours=1)).isoformat(),
            50,
            now.isoformat(),
            0,
            quality_score,
            "[]",
            ingested_at or now.isoformat(),
            tags,
        ),
    )


def _insert_rejection(source_name: str, created_at: str) -> None:
    """quality_rejection_log.source_id 列实存源名称 (quality_hook 口径)。"""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO quality_rejection_log
            (source_id, item_title, item_url, rejected_by, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_name, "rejected item", "https://example.com/x", "recency", "old", created_at),
    )


def _space_fmt(dt: datetime) -> str:
    """created_at 列口径: sqlite datetime('now') → 'YYYY-MM-DD HH:MM:SS'。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


_HIT_TITLE = "CVE-2026-1234 漏洞复现与分析"   # → vuln_research
_MISS_TITLE = "周末美食探店指南"               # → None


# ---------------------------------------------------------------------------
# 1. get_recent_quality_stats 域命中 (hit_count)
# ---------------------------------------------------------------------------
class TestHitCount:
    def test_hit_count_counts_domain_hits_in_window(self, temp_db):
        for i in range(12):
            _insert_hotspot(f"h-{i}", "src-a", title=_HIT_TITLE)
        for i in range(8):
            _insert_hotspot(f"m-{i}", "src-a", title=_MISS_TITLE)
        stats = HotspotRepository().get_recent_quality_stats(
            window=20, practice_domains=["vuln_research"]
        )
        assert stats["src-a"]["hit_count"] == 12, "命中数 = 窗口内打标∈关注域的条数"
        assert stats["src-a"]["count"] == 20
        assert stats["src-a"]["avg_quality"] == 100.0

    def test_hit_count_zero_when_no_hits(self, temp_db):
        for i in range(15):
            _insert_hotspot(f"m-{i}", "src-b", title=_MISS_TITLE)
        stats = HotspotRepository().get_recent_quality_stats(
            practice_domains=["vuln_research"]
        )
        assert stats["src-b"]["hit_count"] == 0, (
            "零命中须显式 0 (M_i h=0→1.4× 消费), 不是缺键"
        )

    def test_no_domains_arg_keeps_legacy_shape(self, temp_db):
        """T4 既有调用零回归: 不传 → 精确 {avg_quality, count}, 无 hit_count 键。"""
        for i in range(6):
            _insert_hotspot(f"l-{i}", "src-c", title=_HIT_TITLE)
        stats = HotspotRepository().get_recent_quality_stats()
        assert stats["src-c"] == {"avg_quality": 100.0, "count": 6}

    def test_empty_domains_list_keeps_legacy_shape(self, temp_db):
        """空列表 = 未配置关注域 → 无信号, 结构同 T4。"""
        for i in range(6):
            _insert_hotspot(f"e-{i}", "src-d", title=_HIT_TITLE)
        stats = HotspotRepository().get_recent_quality_stats(practice_domains=[])
        assert stats["src-d"] == {"avg_quality": 100.0, "count": 6}

    def test_tags_take_priority_over_title(self, temp_db):
        # tags=["渗透测试"] → pentest; title 无任何关键词
        _insert_hotspot(
            "t-1", "src-e", title="季度财报发布", tags='["渗透测试"]'
        )
        stats = HotspotRepository().get_recent_quality_stats(
            practice_domains=["pentest"]
        )
        assert stats["src-e"]["hit_count"] == 1, "打标口径 tags 优先 (与读路径一致)"

    def test_window_truncates_hits_too(self, temp_db):
        """窗口只统计最近 20 条: 旧的命中条目不计入 hit_count。"""
        now = datetime.now(timezone.utc)
        for i in range(5):
            _insert_hotspot(
                f"old-{i}",
                "src-f",
                title=_HIT_TITLE,
                published_at=_iso(now - timedelta(days=10)),
            )
        for i in range(20):
            _insert_hotspot(
                f"new-{i}",
                "src-f",
                title=_MISS_TITLE,
                published_at=_iso(now - timedelta(hours=i + 1)),
            )
        stats = HotspotRepository().get_recent_quality_stats(
            practice_domains=["vuln_research"]
        )
        assert stats["src-f"]["hit_count"] == 0, "窗口截断对 hit 同样生效"


# ---------------------------------------------------------------------------
# 2. 拒收聚合 (M_r 信号源)
# ---------------------------------------------------------------------------
class TestGetRecentRejectionStats:
    def test_counts_rejections_and_accepted_per_source(self, temp_db):
        now = datetime.now(timezone.utc)
        # 窗口内: src-a 3 入库 (ISO-T 格式) + 5 拒收 (空格格式); src-b 仅 2 拒收
        for i in range(3):
            _insert_hotspot(
                f"a-{i}", "src-a", ingested_at=_iso(now - timedelta(days=1))
            )
        for _ in range(5):
            _insert_rejection("src-a", _space_fmt(now - timedelta(days=1)))
        for _ in range(2):
            _insert_rejection("src-b", _space_fmt(now - timedelta(days=1)))
        # 窗口外 (8d): 排除
        for i in range(4):
            _insert_hotspot(
                f"a-old-{i}", "src-a", ingested_at=_iso(now - timedelta(days=8))
            )
        for _ in range(9):
            _insert_rejection("src-a", _space_fmt(now - timedelta(days=8)))

        stats = HotspotRepository().get_recent_rejection_stats(days=7)
        assert stats == {
            "src-a": {"rejections": 5, "accepted": 3},
            "src-b": {"rejections": 2, "accepted": 0},
        }, "attempts 口径 = 窗口内 拒收 + 入库, 窗口外不计"

    def test_accepted_only_source_has_zero_rejections(self, temp_db):
        now = datetime.now(timezone.utc)
        _insert_hotspot("solo", "src-c", ingested_at=_iso(now - timedelta(hours=1)))
        stats = HotspotRepository().get_recent_rejection_stats()
        assert stats == {"src-c": {"rejections": 0, "accepted": 1}}

    def test_empty_db_returns_empty(self, temp_db):
        assert HotspotRepository().get_recent_rejection_stats() == {}
