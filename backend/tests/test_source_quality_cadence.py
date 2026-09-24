"""质量自适应 cadence 测试 (采集闭环 T4, owner 裁决③).

锁定的契约:
1. 倍率映射 (纯函数): avg≥75 → 0.5×; 40≤avg<75 → 1.0×; avg<40 → 2.0×;
   窗口样本 <5 条 → 无信号恒 1.0×; 边界值 40/75 归属正确。
2. 夹取 (纯函数): 乘后 cadence ∈ [max(600, base×0.25), base×4]。
3. hotspot_repo.get_recent_quality_stats: 每源最近 N=20 条 (published_at
   回退 ingested_at 排序) 的 avg + count, 窗口截断正确。
4. get_schedulable(cadence_overrides): 倍率只在 due 计算处生效,
   不回写 cadence_seconds 静态配置 (可回退); 未命中 override 回落 base。
5. stale 对齐: 健康机 stale 判定是连续失败次数口径, 无时间型阈值 —
   倍率拉长的抓取间隔 (最大 4×cadence) 不会误触 stale, 无需动态对齐。
6. density T2 三信号复合: 倍率 = M_q × M_r × M_i 后仍夹取
   [max(600, base×0.25), base×4]; 零命中×高质量 = 1.4×0.5 = 0.7 仍加密
   (裁决②质量豁免由复合结构自然给出); 各信号样本不足恒 1.0×;
   未配置关注域 M_i 恒 1.0; 既有 T4 单乘子用例零回归。

执行:
    python -m pytest backend/tests/test_source_quality_cadence.py -v
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.settings_repo import SettingsRepository
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.services.source_health_machine import STALE_THRESHOLD, SourceHealthMachine
from backend.services.source_scheduler_service import (
    INTEREST_MIN_SAMPLES,
    QUALITY_WINDOW,
    REJECTION_MIN_ATTEMPTS,
    SourceSchedulerService,
    build_cadence_overrides,
    clamp_adjusted_cadence,
    interest_cadence_multiplier,
    quality_cadence_multiplier,
    rejection_cadence_multiplier,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path (全量 migration, 与 test_source_alerter 同模式)。"""
    test_db = tmp_path / "test_quality_cadence.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_cs(
    sid: str,
    *,
    name: str | None = None,
    cadence_seconds: int = 1800,
    last_fetch_at: str | None = None,
    status: str = "active",
    enabled: int = 1,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, status, priority, enabled,
             cadence_seconds, last_fetch_at, consecutive_failures,
             health_score, created_at, updated_at)
        VALUES (?, 'ai', ?, 'html', ?, 50, ?, ?, ?, 0, 1.0,
                datetime('now'), datetime('now'))
        """,
        (sid, name or sid, status, enabled, cadence_seconds, last_fetch_at),
    )


def _insert_hotspot(
    hid: str,
    source: str,
    *,
    title: str | None = None,
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
            quality_score, quality_flags, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid,
            title or f"item {hid}",
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
        ),
    )


def _insert_rejection(source_name: str, created_at: str | None = None) -> None:
    """quality_rejection_log.source_id 列实存源名称 (quality_hook 口径)。"""
    now = datetime.now(timezone.utc)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO quality_rejection_log
            (source_id, item_title, item_url, rejected_by, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_name,
            "rejected item",
            "https://example.com/x",
            "recency",
            "old",
            created_at or now.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# 1. 倍率映射纯函数
# ---------------------------------------------------------------------------
class TestQualityCadenceMultiplier:
    def test_three_tiers(self):
        assert quality_cadence_multiplier(90.0, 10) == 0.5  # 高质量 → 加密
        assert quality_cadence_multiplier(60.0, 10) == 1.0  # 中间 → 不变
        assert quality_cadence_multiplier(20.0, 10) == 2.0  # 低质量 → 降频

    def test_boundaries_75_and_40(self):
        assert quality_cadence_multiplier(75.0, 10) == 0.5, "75 归加密档 (≥75)"
        assert quality_cadence_multiplier(74.9, 10) == 1.0
        assert quality_cadence_multiplier(40.0, 10) == 1.0, "40 归中间档 (≥40)"
        assert quality_cadence_multiplier(39.9, 10) == 2.0

    def test_few_samples_means_no_signal(self):
        assert quality_cadence_multiplier(100.0, 4) == 1.0, "<5 条不调倍率"
        assert quality_cadence_multiplier(100.0, 0) == 1.0
        assert quality_cadence_multiplier(None, 10) == 1.0
        assert quality_cadence_multiplier(10.0, 5) == 2.0, "恰好 5 条有信号"

    def test_window_constant(self):
        assert QUALITY_WINDOW == 20


# ---------------------------------------------------------------------------
# 2. 夹取纯函数
# ---------------------------------------------------------------------------
class TestClampAdjustedCadence:
    def test_unclamped_when_within_bounds(self):
        assert clamp_adjusted_cadence(3600, 1800) == 1800  # 0.5×
        assert clamp_adjusted_cadence(3600, 7200) == 7200  # 2×

    def test_floor_600s(self):
        assert clamp_adjusted_cadence(800, 400) == 600, "下限 600s 防打爆"
        assert clamp_adjusted_cadence(200, 400) == 600

    def test_defensive_bounds(self):
        # 防御性: 输入超出倍率映射值域时仍被夹住
        assert clamp_adjusted_cadence(3600, 100) == 900, "lo = max(600, base×0.25)"
        assert clamp_adjusted_cadence(3600, 100000) == 14400, "hi = base×4"


# ---------------------------------------------------------------------------
# 3. hotspot_repo 质量窗口查询
# ---------------------------------------------------------------------------
class TestGetRecentQualityStats:
    def test_window_truncates_to_latest_20(self, temp_db):
        now = datetime.now(timezone.utc)
        # 25 条: 5 条旧(0 分, published 更早) + 20 条新(100 分)
        for i in range(5):
            _insert_hotspot(
                f"old-{i}",
                "src-a",
                quality_score=0,
                published_at=_iso(now - timedelta(days=10)),
            )
        for i in range(20):
            _insert_hotspot(
                f"new-{i}",
                "src-a",
                quality_score=100,
                published_at=_iso(now - timedelta(hours=i + 1)),
            )
        stats = HotspotRepository().get_recent_quality_stats(window=QUALITY_WINDOW)
        assert stats["src-a"] == {"avg_quality": 100.0, "count": 20}, (
            "窗口只取最近 20 条, 最老的 5 条 0 分不计入"
        )

    def test_returns_count_below_min_samples(self, temp_db):
        for i in range(4):
            _insert_hotspot(f"few-{i}", "src-b", quality_score=100)
        stats = HotspotRepository().get_recent_quality_stats()
        assert stats["src-b"] == {"avg_quality": 100.0, "count": 4}, (
            "repo 如实返回 count, 无信号判定由调用方做"
        )

    def test_published_at_fallback_to_ingested_at(self, temp_db):
        now = datetime.now(timezone.utc)
        # published_at 全 NULL → 按 ingested_at 排序; 最新一条 0 分应拉低均值
        for i in range(5):
            _insert_hotspot(
                f"pb-{i}",
                "src-c",
                quality_score=100,
                published_at=None,
                ingested_at=_iso(now - timedelta(hours=i + 1)),
            )
        _insert_hotspot(
            "pb-late",
            "src-c",
            quality_score=0,
            published_at=None,
            ingested_at=_iso(now),
        )
        stats = HotspotRepository().get_recent_quality_stats(window=5)
        assert stats["src-c"]["count"] == 5
        # 窗口 5 = 最新 5 条: pb-late(0) + pb-0..3(100) → avg 80
        assert stats["src-c"]["avg_quality"] == pytest.approx(80.0)

    def test_empty_db_returns_empty(self, temp_db):
        assert HotspotRepository().get_recent_quality_stats() == {}


# ---------------------------------------------------------------------------
# 4. get_schedulable cadence_overrides (due 计算处生效, 可回退)
# ---------------------------------------------------------------------------
class TestGetSchedulableOverrides:
    def test_fast_multiplier_pulls_due_earlier(self, temp_db):
        now = datetime.now(timezone.utc)
        now_iso = _iso(now)
        # base=3600, 上次抓取 1801s 前: base 口径未到期
        _insert_cs(
            "ai:fast",
            name="fast",
            cadence_seconds=3600,
            last_fetch_at=_iso(now - timedelta(seconds=1801)),
        )
        repo = SourceSchedulerRepository()
        assert repo.get_schedulable(limit=10, now_iso=now_iso) == []
        # override 1800 (0.5×) → 到期被选中
        rows = repo.get_schedulable(
            limit=10,
            now_iso=now_iso,
            cadence_overrides={"ai:fast": 1800.0},
        )
        assert [r["id"] for r in rows] == ["ai:fast"]

    def test_slow_multiplier_defers_due(self, temp_db):
        now = datetime.now(timezone.utc)
        now_iso = _iso(now)
        # base=1800, 上次抓取 2700s 前: base 口径已到期
        _insert_cs(
            "ai:slow",
            name="slow",
            cadence_seconds=1800,
            last_fetch_at=_iso(now - timedelta(seconds=2700)),
        )
        repo = SourceSchedulerRepository()
        assert len(repo.get_schedulable(limit=10, now_iso=now_iso)) == 1
        # override 3600 (2×) → 未到期, 不选
        rows = repo.get_schedulable(
            limit=10,
            now_iso=now_iso,
            cadence_overrides={"ai:slow": 3600.0},
        )
        assert rows == []

    def test_override_miss_falls_back_to_base(self, temp_db):
        now = datetime.now(timezone.utc)
        now_iso = _iso(now)
        _insert_cs(
            "ai:x",
            name="x",
            cadence_seconds=600,
            last_fetch_at=_iso(now - timedelta(seconds=700)),
        )
        repo = SourceSchedulerRepository()
        rows = repo.get_schedulable(
            limit=10,
            now_iso=now_iso,
            cadence_overrides={"other-source": 99999.0},
        )
        assert [r["id"] for r in rows] == ["ai:x"]

    def test_static_config_not_mutated(self, temp_db):
        now = datetime.now(timezone.utc)
        now_iso = _iso(now)
        _insert_cs(
            "ai:slow2",
            name="slow2",
            cadence_seconds=1800,
            last_fetch_at=_iso(now - timedelta(seconds=2700)),
        )
        repo = SourceSchedulerRepository()
        repo.get_schedulable(
            limit=10, now_iso=now_iso, cadence_overrides={"ai:slow2": 3600.0}
        )
        row = repo.get_by_id("ai:slow2")
        assert row["cadence_seconds"] == 1800, "倍率只作用调度计算, 不回写静态配置"


# ---------------------------------------------------------------------------
# 5. service 层 overrides 构建 + tick 接线
# ---------------------------------------------------------------------------
class TestBuildCadenceOverrides:
    def _sources(self) -> list[dict]:
        return [
            {"id": "ai:a", "name": "a", "cadence_seconds": 3600},
            {"id": "ai:b", "name": "b", "cadence_seconds": 1800},
            {"id": "ai:c", "name": "c", "cadence_seconds": 800},
        ]

    def test_maps_quality_to_overrides_by_name(self):
        stats = {
            "a": {"avg_quality": 90.0, "count": 20},
            "b": {"avg_quality": 20.0, "count": 10},
            "c": {"avg_quality": 60.0, "count": 10},  # 1.0× → 不入表
        }
        assert build_cadence_overrides(self._sources(), stats) == {
            "ai:a": 1800.0,  # 3600 × 0.5
            "ai:b": 3600.0,  # 1800 × 2
        }

    def test_no_signal_sources_absent(self):
        stats = {"a": {"avg_quality": 90.0, "count": 4}}  # <5 条无信号
        assert build_cadence_overrides(self._sources(), stats) == {}
        assert build_cadence_overrides(self._sources(), {}) == {}

    def test_clamp_applies_to_small_base(self):
        stats = {"c": {"avg_quality": 90.0, "count": 10}}  # 0.5× → 400
        assert build_cadence_overrides(self._sources(), stats) == {
            "ai:c": 600.0  # 夹到下限 600
        }


class _FakeCollection:
    async def run_one_source(self, source_id: str) -> dict:
        return {
            "status": "success",
            "fetched_count": 1,
            "accepted_count": 1,
            "duration_ms": 10,
            "error_msg": None,
        }


class TestTickWiring:
    def test_tick_passes_quality_overrides_to_schedulable(self, temp_db, monkeypatch):
        now = datetime.now(timezone.utc)
        _insert_cs(
            "ai:fast",
            name="fast",
            cadence_seconds=3600,
            last_fetch_at=_iso(now - timedelta(seconds=1801)),
        )
        for i in range(5):
            _insert_hotspot(f"fast-{i}", "fast", quality_score=100)

        svc = SourceSchedulerService(concurrency=3)
        captured: dict = {}
        orig = svc.repo.get_schedulable

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        monkeypatch.setattr(svc.repo, "get_schedulable", spy)
        svc.attach_collection_service(_FakeCollection())
        result = asyncio.run(svc.tick())

        assert captured.get("cadence_overrides") == {"ai:fast": 1800.0}
        assert result["scheduled"] == 1


# ---------------------------------------------------------------------------
# 7. density T2: 拒收率乘子 M_r / 关注命中乘子 M_i
# ---------------------------------------------------------------------------
class TestRejectionCadenceMultiplier:
    def test_three_tiers(self):
        assert rejection_cadence_multiplier(0.2, 50) == 1.0, "健康源不降频"
        assert rejection_cadence_multiplier(0.3, 50) == 1.3, "0.3 归警示档 (≥0.3)"
        assert rejection_cadence_multiplier(0.59, 50) == 1.3
        assert rejection_cadence_multiplier(0.6, 50) == 1.8, "0.6 归高危档 (≥0.6)"

    def test_few_attempts_means_no_signal(self):
        assert rejection_cadence_multiplier(0.9, 9) == 1.0, "attempts<10 无信号"
        assert rejection_cadence_multiplier(0.9, 0) == 1.0
        assert rejection_cadence_multiplier(None, 50) == 1.0

    def test_min_attempts_boundary(self):
        assert rejection_cadence_multiplier(0.9, 10) == 1.8, "恰好 10 次有信号"


class TestInterestCadenceMultiplier:
    def test_not_configured_is_neutral(self):
        assert interest_cadence_multiplier(0.9, 20, configured=False) == 1.0
        assert interest_cadence_multiplier(0.0, 20, configured=False) == 1.0, (
            "未配置域 = 用户未表态, M_i 恒中性"
        )

    def test_few_samples_means_no_signal(self):
        assert interest_cadence_multiplier(1.0, 9, configured=True) == 1.0
        assert interest_cadence_multiplier(0.0, 9, configured=True) == 1.0

    def test_tiers(self):
        assert interest_cadence_multiplier(0.5, 20, configured=True) == 0.7, (
            "h≥0.5 加密"
        )
        assert interest_cadence_multiplier(0.49, 20, configured=True) == 1.0
        assert interest_cadence_multiplier(0.2, 20, configured=True) == 1.0, (
            "0<h<0.5 中性"
        )

    def test_zero_hit_defers(self):
        assert interest_cadence_multiplier(0.0, INTEREST_MIN_SAMPLES, configured=True) == 1.4


# ---------------------------------------------------------------------------
# 8. density T2: build_cadence_overrides 三信号复合
# ---------------------------------------------------------------------------
class TestBuildCadenceOverridesComposite:
    def _sources(self) -> list[dict]:
        return [
            {"id": "ai:a", "name": "a", "cadence_seconds": 3600},
            {"id": "ai:b", "name": "b", "cadence_seconds": 3600},
            {"id": "ai:c", "name": "c", "cadence_seconds": 1800},
            {"id": "ai:d", "name": "d", "cadence_seconds": 800},
            {"id": "ai:e", "name": "e", "cadence_seconds": 1800},
        ]

    def test_three_multiplier_matrix(self):
        # M_q=0.5 (avg90) × M_r=1.8 (9拒/6入, r=0.6) × M_i=0.7 (h=0.6) = 0.63
        quality = {"a": {"avg_quality": 90.0, "count": 20, "hit_count": 12}}
        rejection = {"a": {"rejections": 9, "accepted": 6}}
        overrides = build_cadence_overrides(
            self._sources(), quality, rejection, ["vuln_research"]
        )
        assert overrides["ai:a"] == pytest.approx(3600 * 0.63)

    def test_zero_hit_high_quality_exemption(self):
        """裁决②: 零命中 1.4 × 高质量 0.5 = 0.7 仍加密 — 复合结构自然给出。"""
        quality = {"b": {"avg_quality": 90.0, "count": 20, "hit_count": 0}}
        overrides = build_cadence_overrides(
            self._sources(), quality, None, ["pentest"]
        )
        assert overrides["ai:b"] == pytest.approx(3600 * 0.7)
        assert overrides["ai:b"] < 3600, "质量豁免后仍加密采集"

    def test_high_rejection_defers(self):
        # M_q=1.0 × M_r=1.8 (12拒/3入, r=0.8) × M_i=1.0 (未配置) = 1.8
        quality = {"c": {"avg_quality": 60.0, "count": 20}}
        rejection = {"c": {"rejections": 12, "accepted": 3}}
        overrides = build_cadence_overrides(self._sources(), quality, rejection)
        assert overrides["ai:c"] == pytest.approx(1800 * 1.8)

    def test_clamp_floor_still_applies(self):
        # M_q=0.5 × M_i=0.7 (h=1.0) = 0.35 → 800×0.35=280 → 夹下限 600
        quality = {"d": {"avg_quality": 90.0, "count": 20, "hit_count": 20}}
        overrides = build_cadence_overrides(
            self._sources(), quality, None, ["vuln_research"]
        )
        assert overrides["ai:d"] == 600.0

    def test_insufficient_samples_all_neutral_absent(self):
        # M_q 无信号 (count=4) + M_r 无信号 (attempts=9) + M_i 无信号 (count<10)
        quality = {"e": {"avg_quality": 10.0, "count": 4, "hit_count": 0}}
        rejection = {"e": {"rejections": 5, "accepted": 4}}
        assert (
            build_cadence_overrides(
                self._sources(), quality, rejection, ["vuln_research"]
            )
            == {}
        )

    def test_unconfigured_domains_mi_neutral(self):
        # stats 带 hit_count 但未配置域 → M_i=1.0, 仅 M_q 生效 (T4 行为)
        quality = {"a": {"avg_quality": 90.0, "count": 20, "hit_count": 0}}
        assert build_cadence_overrides(self._sources(), quality) == {"ai:a": 1800.0}
        assert (
            build_cadence_overrides(self._sources(), quality, None, [])
            == {"ai:a": 1800.0}
        )

    def test_stats_without_hit_count_configured_is_neutral(self):
        # 配置了域但 stats 无 hit_count 键 (repo 未传 domains) → M_i=1.0
        quality = {"a": {"avg_quality": 90.0, "count": 20}}
        assert build_cadence_overrides(
            self._sources(), quality, None, ["vuln_research"]
        ) == {"ai:a": 1800.0}

    def test_rejection_boundary_at_min_attempts(self):
        # attempts 恰好 10 且 r≥0.6 → M_r 生效
        quality = {"a": {"avg_quality": 60.0, "count": 20}}
        rejection = {"a": {"rejections": REJECTION_MIN_ATTEMPTS, "accepted": 0}}
        overrides = build_cadence_overrides(self._sources(), quality, rejection)
        assert overrides["ai:a"] == pytest.approx(3600 * 1.8)


class TestTickWiringDensity:
    def test_tick_composes_three_signals(self, temp_db, monkeypatch):
        """tick 三路信号接线: kv 关注域 + 拒收日志 + 质量窗口 → 复合 override。"""
        now = datetime.now(timezone.utc)
        _insert_cs(
            "ai:fast",
            name="fast",
            cadence_seconds=3600,
            last_fetch_at=_iso(now - timedelta(seconds=3000)),
        )
        # M_q: 10 条 100 分 → 0.5×; M_i: 全命中 vuln_research → h=1.0 → 0.7×
        for i in range(10):
            _insert_hotspot(
                f"fast-{i}",
                "fast",
                quality_score=100,
                title="CVE-2026-1234 漏洞复现",
            )
        # M_r: 15 拒 + 10 入 = 25 attempts, r=0.6 → 1.8×
        for _ in range(15):
            _insert_rejection("fast")
        SettingsRepository().set("interest.practice_domains", ["vuln_research"])

        svc = SourceSchedulerService(concurrency=3)
        captured: dict = {}
        orig = svc.repo.get_schedulable

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        monkeypatch.setattr(svc.repo, "get_schedulable", spy)
        svc.attach_collection_service(_FakeCollection())
        asyncio.run(svc.tick())

        # 0.5 × 1.8 × 0.7 = 0.63 → 3600×0.63
        assert captured.get("cadence_overrides") == {
            "ai:fast": pytest.approx(2268.0)
        }

    def test_tick_without_configured_domains_keeps_t4_behavior(
        self, temp_db, monkeypatch
    ):
        """kv 未配置关注域 → tick 仍拉 hit 信号为空, M_i 中性 (T4 零回归)。"""
        now = datetime.now(timezone.utc)
        _insert_cs(
            "ai:fast",
            name="fast",
            cadence_seconds=3600,
            last_fetch_at=_iso(now - timedelta(seconds=1801)),
        )
        for i in range(5):
            _insert_hotspot(f"fast-{i}", "fast", quality_score=100)

        svc = SourceSchedulerService(concurrency=3)
        captured: dict = {}
        orig = svc.repo.get_schedulable

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        monkeypatch.setattr(svc.repo, "get_schedulable", spy)
        svc.attach_collection_service(_FakeCollection())
        result = asyncio.run(svc.tick())

        assert captured.get("cadence_overrides") == {"ai:fast": 1800.0}
        assert result["scheduled"] == 1


# ---------------------------------------------------------------------------
# 6. stale 对齐: 健康机是次数口径, 倍率拉长间隔不误触 stale
# ---------------------------------------------------------------------------
class TestStaleAlignment:
    def test_stale_is_failure_count_based_not_interval_based(self, temp_db):
        """4× cadence 长间隔源: 成功 run 不进 stale; 连续失败满阈值才 stale。

        锁定"无时间型 stale 判定"口径 — 未来若引入按间隔判 stale 的逻辑,
        本用例失败以提示与 T4 倍率 (最大 4×cadence 间隔) 的交互需重新评估。
        """
        _insert_cs("ai:slow", name="slow", cadence_seconds=600)
        hm = SourceHealthMachine()
        res = hm.apply_run_result(
            "ai:slow",
            {"status": "success", "fetched_count": 3, "accepted_count": 2},
        )
        assert res["new_status"] == "active", "长间隔 + 有产出 → 保持 active"

        for _ in range(STALE_THRESHOLD - 1):
            res = hm.apply_run_result(
                "ai:slow", {"status": "failed", "fetched_count": 0}
            )
        assert res["new_status"] != "stale", "未满连续失败阈值不判 stale"
        res = hm.apply_run_result(
            "ai:slow", {"status": "failed", "fetched_count": 0}
        )
        assert res["new_status"] == "stale", "stale 仅由连续失败次数触发"
