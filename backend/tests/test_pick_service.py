"""pick_service — 精选评分合成 (spec 2026-09-27 four-modes §3)。

契约:
- pick_score = quality_score + (boost-1)*25 + 10* favored_source + 时效衰减
- 时效衰减: 24h 内满权重; 24h~7d 线性衰减到 0.6 (不为零 — 旧文仍可比)
- Top-N: 全量按 pick_score DESC 取 N=30 落列, 其余落 NULL? 不 — 全部落分,
  视图取 Top-N; 落列覆盖窗口内全部新条目 (可解释性)
- favored source: favorites 中该 source 出现 ≥2 次
"""
import pytest
from datetime import datetime, timedelta, timezone

from backend.services import pick_service as ps


def _mk(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class TestComputePickScore:
    def test_base_quality_score(self):
        s = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        assert 79 <= s <= 81  # 衰减近满

    def test_interest_boost_adds(self):
        base = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        boosted = ps.compute_pick_score(
            quality_score=80, interest_boost=1.3,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        assert boosted > base + 5  # (1.3-1)*25 = 7.5

    def test_favored_source_adds_10(self):
        base = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        fav = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=True, fetched_at_iso=_mk(1),
        )
        assert abs((fav - base) - 10) < 0.5

    def test_decay_old_item(self):
        fresh = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        old = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(24 * 6),
        )
        assert old < fresh
        # 衰减下限: 不低于 0.6 系数
        assert old >= 80 * 0.6 - 0.1


class TestRefreshPickScores:
    def test_end_to_end_writes_column(self, temp_db, monkeypatch):
        from backend.repository.db import get_connection
        conn = get_connection()
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now - timedelta(hours=1)).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 80, 80, '', ?, ?)",
                (f"p_{i}", f"t{i}", f"https://x.com/{i}", ts, ts, ts),
            )
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {"security": 1.2})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: {"src"})  # ≥2 收藏的源
        result = ps.refresh_pick_scores(lookback_hours=40, top_n=3)
        assert result["evaluated"] == 5
        assert result["picked"] == 3
        scores = conn.execute(
            "SELECT id, pick_score FROM hotspots WHERE pick_score IS NOT NULL"
        ).fetchall()
        assert len(scores) == 3  # 只有 Top-3 有分 (其余 NULL = 未入选)
        # favored source + boost 都加成 → 分数 > 80
        assert all(r["pick_score"] > 80 for r in scores)

    def test_empty_window_noop(self, temp_db, monkeypatch):
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: set())
        assert ps.refresh_pick_scores(lookback_hours=40, top_n=3) == {
            "evaluated": 0, "picked": 0,
        }


class TestListPickedSince:
    def test_returns_top_by_pick_score(self, temp_db):
        from backend.repository.db import get_connection
        from backend.repository.hotspot_repo import HotspotRepository
        from datetime import datetime, timedelta, timezone
        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        for i, pscore in enumerate([90.0, 70.0, 80.0]):
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at, pick_score)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 80, 80, '', ?, ?, ?)",
                (f"pk_{i}", f"t{i}", f"https://y.com/{i}", ts, ts, ts, pscore),
            )
        since = (now - timedelta(days=7)).isoformat()
        rows = HotspotRepository().list_picked_since(since, limit=2)
        assert [r["pick_score"] for r in rows] == [90.0, 80.0]
        assert rows[0]["id"] == "pk_0"
