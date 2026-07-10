"""Phase 9 招标源质量门禁 测试

覆盖：
- :class:`SourceStatsRepository` CRUD + 状态升级 (active → stale → dead)
- :class:`CoverageRunRepository` 快照写入
- :func:`evaluate_source_coverage` 整体评估
- 覆盖度告警逻辑
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.domain.collection import CollectionReport, CollectionResult, SourceResult
from backend.domain.enums import Category
from backend.quality.source_coverage import evaluate_source_coverage
from backend.repository import db
from backend.repository.source_stats_repo import (
    CoverageRunRepository,
    SourceStatsRepository,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test_source_stats.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


def _make_result(
    category: Category,
    sources: list[tuple[str, str, int, str | None]],
) -> CollectionResult:
    """构造 1 个 CollectionResult.

    sources: [(source_name, source_url, item_count, error_msg), ...]
    """
    src_results = [
        SourceResult(
            source_name=n,
            source_url=u,
            item_count=c,
            error_msg=err,
        )
        for (n, u, c, err) in sources
    ]
    return CollectionResult(
        category=category,
        items=[],
        item_count=sum(c for (_, _, c, _) in sources),
        source_results=src_results,
        started_at=datetime.now(timezone.utc),
    )


def _make_report(results: list[CollectionResult]) -> CollectionReport:
    return CollectionReport(
        total=sum(r.item_count for r in results),
        success_count=len(results),
        failed_count=0,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        results=results,
    )


# ---------------------------------------------------------------------------
# SourceStatsRepository 测试
# ---------------------------------------------------------------------------
class TestSourceStatsRepository:
    def test_upsert_first_time_with_yield(self, temp_db):
        repo = SourceStatsRepository()
        repo.upsert_after_run(
            category="bid",
            source_name="中国政府采购网",
            source_url="https://www.ccgp.gov.cn/",
            item_count=5,
        )
        row = repo.get_one("bid", "中国政府采购网")
        assert row is not None
        assert row["total_runs"] == 1
        assert row["zero_yield_runs"] == 0
        assert row["total_items"] == 5
        assert row["status"] == "active"
        assert row["last_seen_at"] is not None
        assert row["last_checked_at"] is not None

    def test_upsert_first_time_zero_yield(self, temp_db):
        repo = SourceStatsRepository()
        repo.upsert_after_run(
            category="bid",
            source_name="中国政府采购网",
            source_url="https://www.ccgp.gov.cn/",
            item_count=0,
            error_msg="HTTP 503",
        )
        row = repo.get_one("bid", "中国政府采购网")
        assert row["zero_yield_runs"] == 1
        assert row["status"] == "active"  # 首次连 0 不升级
        assert row["last_error"] == "HTTP 503"

    def test_zero_yield_increments_until_stale(self, temp_db):
        repo = SourceStatsRepository()
        # 跑 3 次 0 → status 升级 stale (threshold=3)
        for _ in range(3):
            repo.upsert_after_run("bid", "源A", "https://a/", 0, "err")
        row = repo.get_one("bid", "源A")
        assert row["zero_yield_runs"] == 3
        assert row["status"] == "stale"

    def test_zero_yield_increments_until_dead(self, temp_db):
        repo = SourceStatsRepository()
        # 跑 6 次 0 → status 升级 dead
        for _ in range(6):
            repo.upsert_after_run("bid", "源B", "https://b/", 0, "err")
        row = repo.get_one("bid", "源B")
        assert row["zero_yield_runs"] == 6
        assert row["status"] == "dead"

    def test_yield_resets_zero_yield_runs(self, temp_db):
        repo = SourceStatsRepository()
        # 2 次 0
        for _ in range(2):
            repo.upsert_after_run("bid", "源C", "https://c/", 0, "err")
        assert repo.get_one("bid", "源C")["zero_yield_runs"] == 2
        # 1 次有产出
        repo.upsert_after_run("bid", "源C", "https://c/", 3, None)
        row = repo.get_one("bid", "源C")
        assert row["zero_yield_runs"] == 0
        assert row["status"] == "active"  # 不主动降级 stale → active
        assert row["total_items"] == 3

    def test_dead_status_persists_after_yield(self, temp_db):
        """标 dead 后即使有产出也不会自动恢复为 active。"""
        repo = SourceStatsRepository()
        for _ in range(6):
            repo.upsert_after_run("bid", "源D", "https://d/", 0, "err")
        assert repo.get_one("bid", "源D")["status"] == "dead"
        repo.upsert_after_run("bid", "源D", "https://d/", 1, None)
        # status 仍为 dead (运维需手动 reset)
        assert repo.get_one("bid", "源D")["status"] == "dead"
        assert repo.get_one("bid", "源D")["zero_yield_runs"] == 0

    def test_mark_dead_manual(self, temp_db):
        repo = SourceStatsRepository()
        repo.upsert_after_run("bid", "源E", "https://e/", 5)
        repo.mark_dead("bid", "源E")
        assert repo.get_one("bid", "源E")["status"] == "dead"

    def test_reset_clears_zero_yield(self, temp_db):
        repo = SourceStatsRepository()
        for _ in range(5):
            repo.upsert_after_run("bid", "源F", "https://f/", 0, "err")
        assert repo.get_one("bid", "源F")["status"] == "stale"
        repo.reset("bid", "源F")
        row = repo.get_one("bid", "源F")
        assert row["zero_yield_runs"] == 0
        assert row["status"] == "active"

    def test_list_by_category(self, temp_db):
        repo = SourceStatsRepository()
        for cat, name in [
            ("bid", "A"), ("bid", "B"), ("ai", "C"),
        ]:
            repo.upsert_after_run(cat, name, f"https://{name}", 3)
        rows = repo.list_by_category("bid")
        assert len(rows) == 2
        assert {r["source_name"] for r in rows} == {"A", "B"}

    def test_list_by_status(self, temp_db):
        repo = SourceStatsRepository()
        for _ in range(6):
            repo.upsert_after_run("bid", "Z", "https://z/", 0, "err")
        assert len(repo.list_by_status("dead")) == 1
        assert len(repo.list_by_status("stale")) == 0

    def test_summary_by_category(self, temp_db):
        repo = SourceStatsRepository()
        for name in ["X", "Y"]:
            repo.upsert_after_run("bid", name, f"https://{name}", 3)
        for _ in range(6):
            repo.upsert_after_run("ai", "Z", "https://z/", 0, "err")
        summary = repo.summary_by_category()
        assert summary["bid"]["active"] == 2
        assert summary["bid"]["total"] == 2
        assert summary["ai"]["dead"] == 1
        assert summary["ai"]["total"] == 1


# ---------------------------------------------------------------------------
# CoverageRunRepository 测试
# ---------------------------------------------------------------------------
class TestCoverageRunRepository:
    def test_write_and_read_latest(self, temp_db):
        repo = CoverageRunRepository()
        rid = repo.write_run(
            run_id="run-001",
            category="bid",
            total_sources=10,
            active_sources=7,
            zero_sources=3,
            details=[{"source_name": "A", "item_count": 5}],
        )
        assert rid > 0
        latest = repo.latest_for_category("bid", limit=5)
        assert len(latest) == 1
        assert latest[0]["run_id"] == "run-001"
        assert latest[0]["total_sources"] == 10
        assert latest[0]["active_sources"] == 7
        assert latest[0]["coverage_ratio"] == pytest.approx(0.7)
        assert latest[0]["details"][0]["source_name"] == "A"

    def test_write_with_zero_total(self, temp_db):
        repo = CoverageRunRepository()
        repo.write_run(
            run_id="run-002",
            category="bid",
            total_sources=0,
            active_sources=0,
            zero_sources=0,
            details=[],
        )
        latest = repo.latest_for_category("bid", limit=5)
        assert latest[0]["coverage_ratio"] == 0.0

    def test_latest_orders_by_created_at(self, temp_db):
        repo = CoverageRunRepository()
        for i in range(3):
            repo.write_run(
                run_id=f"run-{i:03d}",
                category="bid",
                total_sources=5,
                active_sources=i + 1,
                zero_sources=5 - (i + 1),
                details=[],
            )
        latest = repo.latest_for_category("bid", limit=5)
        assert len(latest) == 3


# ---------------------------------------------------------------------------
# evaluate_source_coverage 集成测试
# ---------------------------------------------------------------------------
class TestEvaluateSourceCoverage:
    def test_happy_path_no_alert(self, temp_db):
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [
                        ("A", "https://a/", 5, None),
                        ("B", "https://b/", 3, None),
                        ("C", "https://c/", 2, None),
                    ],
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="run-happy")
        assert len(cov.alerts) == 0
        assert cov.has_alert is False
        cat = cov.categories[0]
        assert cat.total_sources == 3
        assert cat.active_sources == 3
        assert cat.coverage_ratio == 1.0
        # DB 写入
        repo = SourceStatsRepository()
        for name in ["A", "B", "C"]:
            row = repo.get_one("bid", name)
            assert row is not None
            assert row["status"] == "active"

    def test_low_active_triggers_alert(self, temp_db):
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [
                        ("A", "https://a/", 5, None),
                        ("B", "https://b/", 0, "timeout"),
                        ("C", "https://c/", 0, "503"),
                    ],
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="run-low")
        assert cov.has_alert is True
        assert "active_sources=1 < min=3" in cov.alerts[0]
        assert len(cov.stale_sources) == 0  # 首次连 0 不升级
        cat = cov.categories[0]
        assert cat.active_sources == 1
        assert cat.zero_sources == 2
        assert cat.coverage_ratio == pytest.approx(1 / 3)

    def test_repeated_zero_promotes_to_dead(self, temp_db):
        # 跑 6 次 collect，每次 B 源 0 产出
        for run_i in range(6):
            report = _make_report(
                [
                    _make_result(
                        Category.BID,
                        [
                            ("A", "https://a/", 5, None),
                            ("B", "https://b/", 0, "err"),
                        ],
                    ),
                ]
            )
            cov = evaluate_source_coverage(report, run_id=f"run-{run_i}")
        # B 源应升级 dead
        assert any(d.source_name == "B" for d in cov.dead_sources)
        repo = SourceStatsRepository()
        row = repo.get_one("bid", "B")
        assert row["status"] == "dead"
        assert row["zero_yield_runs"] == 6

    def test_repeated_zero_promotes_to_stale_then_dead(self, temp_db):
        # 跑 3 次连 0 → stale; 后续 3 次 → dead
        for run_i in range(3):
            report = _make_report(
                [
                    _make_result(
                        Category.BID,
                        [
                            ("X", "https://x/", 0, "err"),
                            ("Y", "https://y/", 3, None),
                        ],
                    ),
                ]
            )
            cov = evaluate_source_coverage(report, run_id=f"run-s{run_i}")
        # X 应 stale
        assert any(d.source_name == "X" for d in cov.stale_sources)
        # 再跑 3 次
        for run_i in range(3):
            report = _make_report(
                [
                    _make_result(
                        Category.BID,
                        [
                            ("X", "https://x/", 0, "err"),
                            ("Y", "https://y/", 3, None),
                        ],
                    ),
                ]
            )
            cov = evaluate_source_coverage(report, run_id=f"run-d{run_i}")
        # X 应 dead
        assert any(d.source_name == "X" for d in cov.dead_sources)
        assert all(d.source_name != "X" for d in cov.stale_sources)

    def test_multi_category_coverage(self, temp_db):
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [
                        ("BA", "https://ba/", 5, None),
                        ("BB", "https://bb/", 0, "err"),
                    ],
                ),
                _make_result(
                    Category.AI,
                    [
                        ("AA", "https://aa/", 3, None),
                        ("AB", "https://ab/", 2, None),
                        ("AC", "https://ac/", 1, None),
                    ],
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="run-multi")
        cats = {c.category: c for c in cov.categories}
        assert cats["bid"].active_sources == 1
        assert cats["bid"].alert is True
        assert cats["ai"].active_sources == 3
        assert cats["ai"].alert is False

    def test_coverage_runs_written_for_each_category(self, temp_db):
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [("B1", "https://b1/", 5, None)],
                ),
                _make_result(
                    Category.AI,
                    [("A1", "https://a1/", 3, None)],
                ),
            ]
        )
        evaluate_source_coverage(report, run_id="run-cov")
        cov_repo = CoverageRunRepository()
        assert len(cov_repo.latest_for_category("bid")) == 1
        assert len(cov_repo.latest_for_category("ai")) == 1

    def test_to_dict_shape(self, temp_db):
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [
                        ("A", "https://a/", 5, None),
                        ("B", "https://b/", 0, "err"),
                    ],
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="run-dict")
        d = cov.to_dict()
        assert d["run_id"] == "run-dict"
        assert len(d["categories"]) == 1
        c0 = d["categories"][0]
        assert c0["category"] == "bid"
        assert c0["total_sources"] == 2
        assert c0["active_sources"] == 1
        assert c0["min_active_sources"] == 3
        assert c0["alert"] is True
        assert c0["alert_reason"]
        assert len(c0["details"]) == 2
        assert "dead_sources" in d
        assert "stale_sources" in d
        assert "alerts" in d
        assert d["has_alert"] is True

    def test_empty_source_results_no_alert(self, temp_db):
        """没有 source_results 的空 report：不触发告警。"""
        report = _make_report(
            [
                CollectionResult(
                    category=Category.BID,
                    items=[],
                    item_count=0,
                    source_results=[],
                    started_at=datetime.now(timezone.utc),
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="run-empty")
        assert len(cov.alerts) == 0
        assert len(cov.categories) == 1
        assert cov.categories[0].total_sources == 0

    def test_resume_after_yield_resets_status(self, temp_db):
        """X 累计 3 次 0 → stale; 之后 1 次有产出 → zero_yield=0 但 status
        仍为 stale（不自动降级，需要运维 reset）。"""
        for i in range(3):
            report = _make_report(
                [
                    _make_result(
                        Category.BID,
                        [("Z", "https://z/", 0, "err")],
                    ),
                ]
            )
            evaluate_source_coverage(report, run_id=f"r{i}")
        # 第 4 次有产出
        report = _make_report(
            [
                _make_result(
                    Category.BID,
                    [("Z", "https://z/", 5, None)],
                ),
            ]
        )
        cov = evaluate_source_coverage(report, run_id="r-yield")
        repo = SourceStatsRepository()
        row = repo.get_one("bid", "Z")
        assert row["zero_yield_runs"] == 0
        assert row["status"] == "stale"  # 不自动降级
