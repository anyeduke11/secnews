"""pick_service — 精选评分合成 (spec 2026-09-27 four-modes §3)。

契约:
- pick_score = quality_score + (boost-1)*25 + 10* favored_source + 时效衰减
- 时效衰减: 24h 内满权重; 24h~7d 线性衰减到 0.6 (不为零 — 旧文仍可比)
- Top-N: 全量按 pick_score DESC 取 N=30 落列, 其余落 NULL? 不 — 全部落分,
  视图取 Top-N; 落列覆盖窗口内全部新条目 (可解释性)
- favored source: favorites 中该 source 出现 ≥2 次
"""
import sqlite3
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

    def test_decay_boundary_exactly_24h_full_weight(self):
        """衰减边界: 恰好 24h 仍满权重 (hours <= FULL_WEIGHT_HOURS 含等号)。"""
        s = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(24),
        )
        assert abs(s - 80.0) < 0.5

    def test_decay_boundary_exactly_168h_at_floor(self):
        """衰减边界: 恰好 168h (7d) 到达下限 0.6 系数。"""
        s = ps.compute_pick_score(
            quality_score=100, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(168),
        )
        assert abs(s - 60.0) < 0.5  # 100 × 0.6

    def test_decay_midpoint_is_linear_halfway(self):
        """衰减线性性: 96h (24h 与 168h 中点) ≈ 0.8 系数。"""
        s = ps.compute_pick_score(
            quality_score=100, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(96),
        )
        assert abs(s - 80.0) < 1.0  # 1.0 - 0.5×0.4 = 0.8

    def test_interest_boost_below_one_negative_bonus(self):
        """boost < 1 (非关注域) → 负加成, 分数低于同条件中性条目。"""
        neutral = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        penalized = ps.compute_pick_score(
            quality_score=80, interest_boost=0.8,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        assert penalized < neutral  # (0.8-1)*25 = -5

    def test_null_quality_score_falls_back_to_60(self):
        """quality_score=0/None 语义: 调用方传 0 → 兜底 60 (refresh 的 COALESCE 同语义)。"""
        s = ps.compute_pick_score(
            quality_score=0, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        assert abs(s - 60.0) < 0.5

    def test_bad_timestamp_treated_as_fresh(self):
        """坏时间戳 (解析失败) → hours=0 满权重容错, 不抛异常。"""
        s = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso="not-a-date",
        )
        assert abs(s - 80.0) < 0.5

    def test_naive_timestamp_treated_as_utc(self):
        """naive 时间戳 (无 tzinfo) → 按 UTC 处理, 不抛异常。"""
        naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        s = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=naive,
        )
        assert 79 <= s <= 81


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

    def test_top_n_from_settings_used_when_param_omitted(self, temp_db, monkeypatch):
        """top_n=None → 读 settings quality.pick_top_n (计划 §3.2 可配置契约)。"""
        from backend.repository.db import get_connection
        from backend.repository.settings_repo import SettingsRepository

        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        for i in range(5):
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 80, 80, '', ?, ?)",
                (f"st_{i}", f"t{i}", f"https://s.com/{i}", ts, ts, ts),
            )
        SettingsRepository().set("quality.pick_top_n", 2)
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: set())
        result = ps.refresh_pick_scores(lookback_hours=40)  # top_n 不传 → settings
        assert result == {"evaluated": 5, "picked": 2}
        picked = conn.execute(
            "SELECT COUNT(*) c FROM hotspots WHERE pick_score IS NOT NULL"
        ).fetchone()
        assert picked["c"] == 2

    def test_unpicked_rows_set_to_null(self, temp_db, monkeypatch):
        """Top-N 外的行落 NULL (非保留旧分) — 精选视图只显示本轮入选。"""
        from backend.repository.db import get_connection

        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        # 先给 l_0 一个旧分, 刷新后它若落选必须被置 NULL (防上轮残留污染)
        conn.execute(
            "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
            " category, published_at, quality_score, score, summary,"
            " fetched_at, ingested_at, pick_score)"
            " VALUES ('l_0', 't0', 'https://l.com/0', 'src', 'security',"
            " ?, 50, 50, '', ?, ?, 99.0)",
            (ts, ts, ts),
        )
        for i in range(1, 4):
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 90, 90, '', ?, ?)",
                (f"l_{i}", f"t{i}", f"https://l.com/{i}", ts, ts, ts),
            )
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: set())
        ps.refresh_pick_scores(lookback_hours=40, top_n=2)
        row = conn.execute(
            "SELECT pick_score FROM hotspots WHERE id = 'l_0'"
        ).fetchone()
        assert row["pick_score"] is None  # 落选 → NULL (旧 99.0 被清除)

    def test_high_quality_score_column_used_over_score(self, temp_db, monkeypatch):
        """quality_score 列值为 0 (falsy) → refresh 内 float(0 or ...) 兜底语义:
        compute_pick_score 收到 0 → base 兜 60。测 COALESCE 链路终点兜底。"""
        from backend.repository.db import get_connection

        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
            " category, published_at, quality_score, score, summary,"
            " fetched_at, ingested_at)"
            " VALUES ('q_0', 't', 'https://q.com/0', 'src', 'security',"
            " ?, 0, 90, '', ?, ?)",
            (ts, ts, ts),
        )
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: set())
        ps.refresh_pick_scores(lookback_hours=40, top_n=5)
        row = conn.execute(
            "SELECT pick_score FROM hotspots WHERE id = 'q_0'"
        ).fetchone()
        # quality_score=0 是 falsy → COALESCE 取 0, compute 内 `or 60` 兜 60
        assert row["pick_score"] is not None and abs(row["pick_score"] - 60.0) < 0.5


class TestLoadHelpersDegradation:
    """三个 _load_* 的降级路径: 任何失败 → 空默认 (refresh 全程不抛的根基)。"""

    def test_load_boost_map_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(
            "backend.services.interest_engine_service.InterestEngineService.get_boost_map",
            lambda self: (_ for _ in ()).throw(RuntimeError("engine down")),
        )
        assert ps._load_boost_map() == {}

    def test_load_favored_sources_query_failure_degrades(self, temp_db, monkeypatch):
        """get_connection 抛错 → 空集合 (refresh 全程不抛的降级根基)。"""
        from backend.repository import db as db_mod

        def boom():
            raise sqlite3.OperationalError("db gone")
        monkeypatch.setattr(db_mod, "get_connection", boom)
        assert ps._load_favored_sources(min_count=2) == set()

    def test_load_favored_sources_min_count_filter(self, temp_db):
        """favorites 1 篇的源不入选 (≥2 才 favored) — 防单次误收藏污染。"""
        from backend.repository.db import get_connection
        from backend.services.pick_service import _load_favored_sources

        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        for pid in ("fav_1", "fav_2"):
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at)"
                " VALUES (?, ?, ?, 'favsrc', 'security', ?, 80, 80, '', ?, ?)",
                (pid, pid, f"https://fav.com/{pid}", ts, ts, ts),
            )
        conn.execute(
            "INSERT OR IGNORE INTO favorites (hotspot_id, category, title,"
            " source, url, favorited_at, created_via)"
            " VALUES ('fav_1', 'security', 'fav_1', 'favsrc',"
            " 'https://fav.com/fav_1', ?, 'ui')",
            (ts,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO favorites (hotspot_id, category, title,"
            " source, url, favorited_at, created_via)"
            " VALUES ('fav_2', 'security', 'fav_2', 'favsrc',"
            " 'https://fav.com/fav_2', ?, 'ui')",
            (ts,),
        )
        # favsrc 有 2 篇收藏 → favored
        assert "favsrc" in _load_favored_sources(min_count=2)
        conn.execute("DELETE FROM favorites WHERE hotspot_id = 'fav_2'")
        # 只剩 1 篇 → 不再 favored
        assert "favsrc" not in _load_favored_sources(min_count=2)

    def test_load_top_n_invalid_value_degrades_to_default(self, temp_db):
        """settings 写坏值 (负数/字符串) → 回退默认 30 (fail-safe)。"""
        from backend.repository.settings_repo import SettingsRepository

        repo = SettingsRepository()
        repo.set("quality.pick_top_n", -5)
        assert ps._load_top_n() == 30
        repo.set("quality.pick_top_n", "abc")
        assert ps._load_top_n() == 30
        repo.set("quality.pick_top_n", 10)
        assert ps._load_top_n() == 10


class TestListPickedSince:
    def test_returns_top_by_pick_score(self, temp_db):
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection
        from backend.repository.hotspot_repo import HotspotRepository
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
