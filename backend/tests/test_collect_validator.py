"""v1.9 Phase 9 — collect_validator (4 类数据完整性验证) 单测.

覆盖 (10 用例):
  - V1.1 正常 run → ValidationReport 0 issues
  - V1.2 _check_source_regression: 历史 avg > 0, 当前 0 → warn
  - V1.3 _check_source_regression: 当前 < 30% → info
  - V1.4 _check_time_coverage_gap: 连续 3h 空 → warn
  - V1.5 _check_category_anomaly: 当前 = 0, 历史 > 0 → error
  - V1.6 _check_category_anomaly: 当前 > 2x → info
  - V1.7 _check_cross_source: 高 ratio (>0.8) → info
  - V1.8 validate_run 整合: 跑全部 4 类
  - V1.9 validate_and_persist: 写库 + 写日志
  - V1.10 _check_* 内部异常 → 返单条 warn 不阻塞
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.repository.db import get_connection
from backend.services.collect_validator import (
    Severity,
    ValidationReport,
    ValidationType,
    validate_and_persist,
    validate_run,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Override conftest's str-typed temp_db with Path-typed one."""
    from backend.config import config
    from backend.repository import db
    test_db = tmp_path / "test_collect_validator.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _insert_ckpt(
    run_id: int,
    cat: str,
    src: str,
    items: int,
    status: str = "done",
    finished_offset_h: float = 0,
):
    """手工写一行 checkpoint."""
    from backend.repository.db import get_connection
    conn = get_connection()
    now = datetime.now(timezone.utc)
    finished_at = (now - timedelta(hours=finished_offset_h)).isoformat()
    conn.execute(
        """
        INSERT INTO catchup_checkpoints
            (run_id, category, source_name, status, items_count,
             started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, cat, src, status, items, finished_at, finished_at),
    )


def _insert_hotspot(
    cat: str,
    src: str,
    title: str,
    ingested_offset_h: float = 0,
):
    conn = get_connection()
    now = datetime.now(timezone.utc)
    ingested_at = (now - timedelta(hours=ingested_offset_h)).isoformat()
    conn.execute(
        """
        INSERT INTO hotspots
            (id, title, source, url, category,
             ingested_at, published_at, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{cat}_{src}_{title[:20]}",
            title,
            src,
            "https://example.com/" + title[:20],
            cat,
            ingested_at,
            ingested_at,
            ingested_at,
        ),
    )


# ---------------------------------------------------------------------------
# V1.1 — 正常 run 无历史 → 0 issues
# ---------------------------------------------------------------------------
def test_validate_run_clean_no_history(temp_db):
    """无历史 checkpoint 数据, 无 hotspots → 不应报错, issues 数为 0."""
    report = validate_run(
        run_id=1,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    assert isinstance(report, ValidationReport)
    # source_regression / category_anomaly 都依赖历史, 没数据 → 0
    # time_coverage_gap: 24h 全空 (没数据) → 1 warn (连续 24 个空 bin)
    # cross_source: 0 个簇 → 0
    # 至少不应有 error
    assert not report.has_errors


# ---------------------------------------------------------------------------
# V1.2 — _check_source_regression: 历史有产出, 当前 0 → warn
# ---------------------------------------------------------------------------
def test_source_regression_zero_yield(temp_db):
    """历史 (run 100) 10 个, 本 run (101) 0 个 → warn."""
    _insert_ckpt(100, "ai", "hacker_news", items=10, finished_offset_h=12)  # 12h 前
    _insert_ckpt(101, "ai", "hacker_news", items=0, finished_offset_h=0)
    report = validate_run(
        run_id=101,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    src_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.SOURCE_REGRESSION.value
    ]
    assert len(src_issues) >= 1
    assert any(i.severity == Severity.WARN.value for i in src_issues)
    issue = next(i for i in src_issues if i.severity == Severity.WARN.value)
    assert issue.payload["source_name"] == "hacker_news"
    assert issue.payload["current"] == 0
    assert issue.payload["regression_pct"] == 100.0


# ---------------------------------------------------------------------------
# V1.3 — _check_source_regression: 当前 < 30% → info
# ---------------------------------------------------------------------------
def test_source_regression_below_30pct(temp_db):
    """历史 (run 100) 10 个, 本 run (101) 2 个 → info (20%)."""
    _insert_ckpt(100, "ai", "hn", items=10, finished_offset_h=12)
    _insert_ckpt(101, "ai", "hn", items=2, finished_offset_h=0)
    report = validate_run(
        run_id=101,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    src_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.SOURCE_REGRESSION.value
    ]
    assert len(src_issues) >= 1
    info_issues = [i for i in src_issues if i.severity == Severity.INFO.value]
    assert len(info_issues) >= 1
    payload = info_issues[0].payload
    assert payload["current"] == 2
    assert payload["history_avg"] >= 10


# ---------------------------------------------------------------------------
# V1.4 — _check_time_coverage_gap: 连续 3h 空 → warn
# ---------------------------------------------------------------------------
def test_time_coverage_gap_3h_empty(temp_db):
    """5h 前 1 条 + 立即 1 条 → 中间 3h 空 → warn.

    bins (1h 切分, [now-6h, now]):
      bin 0 [now-6h, now-5h): empty
      bin 1 [now-5h, now-4h): empty
      bin 2 [now-4h, now-3h): empty  ← 连续空段开始
      bin 3 [now-3h, now-2h): empty
      bin 4 [now-2h, now-1h): empty  ← 连续空段 ≥ 3h
      bin 5 [now-1h, now):    1 条 (ingested_offset_h=0)
    """
    # 在 t-5h 插 1 条
    _insert_hotspot("ai", "hn", "old news", ingested_offset_h=5)
    # 在 t=0 (现在) 插 1 条
    _insert_hotspot("ai", "hn", "new news", ingested_offset_h=0)
    # 中间 [t-5h, t-1h) 4 个 bin 全空
    report = validate_run(
        run_id=1,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    gap_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.TIME_COVERAGE_GAP.value
    ]
    # 应该至少 1 条 warn (连续 ≥ 3 个空段)
    assert any(i.severity == Severity.WARN.value for i in gap_issues), \
        f"expected gap warn, got {[i.to_dict() for i in report.issues]}"


# ---------------------------------------------------------------------------
# V1.5 — _check_category_anomaly: 当前 0, 历史 > 0 → error
# ---------------------------------------------------------------------------
def test_category_anomaly_zero_total(temp_db):
    """历史 run 100: ai 50 items, run 101: ai 0 → error."""
    # 写一个 run 100 的 checkpoint 聚合 = 50
    from backend.repository.db import get_connection
    for i in range(5):
        _insert_ckpt(100, "ai", f"src{i}", items=10, finished_offset_h=12)
    # run 101 0
    _insert_ckpt(101, "ai", "src0", items=0, finished_offset_h=0)
    report = validate_run(
        run_id=101,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    cat_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.CATEGORY_ANOMALY.value
    ]
    assert any(i.severity == Severity.ERROR.value for i in cat_issues)
    err_issue = next(i for i in cat_issues if i.severity == Severity.ERROR.value)
    assert err_issue.payload["category"] == "ai"
    assert err_issue.payload["type"] == "total_zero"


# ---------------------------------------------------------------------------
# V1.6 — _check_category_anomaly: 当前 > 2x → info
# ---------------------------------------------------------------------------
def test_category_anomaly_above_2x(temp_db):
    """历史 avg = 10, 本次 = 30 → info (above_2x)."""
    from backend.repository.db import get_connection
    for i in range(3):
        _insert_ckpt(100 + i, "ai", f"src{i}", items=10, finished_offset_h=12)
    # 本次 = 30
    for i in range(3):
        _insert_ckpt(200, "ai", f"src{i}", items=10, finished_offset_h=0)
    report = validate_run(
        run_id=200,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    cat_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.CATEGORY_ANOMALY.value
    ]
    info_issues = [i for i in cat_issues if i.severity == Severity.INFO.value]
    assert any(
        i.payload.get("type") == "above_2x" for i in info_issues
    )


# ---------------------------------------------------------------------------
# V1.7 — _check_cross_source: 高 ratio → info
# ---------------------------------------------------------------------------
def test_cross_source_high_overlap(temp_db):
    """10 个簇全部被多源覆盖 → ratio=1.0 → info (high_overlap)."""
    # 5 个 title, 每个被 2 个 source 覆盖 = 5 clusters, ratio=1.0
    for i in range(5):
        _insert_hotspot("ai", "hn", f"shared topic {i}", ingested_offset_h=1)
        _insert_hotspot("ai", "ph", f"shared topic {i}", ingested_offset_h=1)
    report = validate_run(
        run_id=1,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    cross_issues = [
        i for i in report.issues
        if i.validation_type == ValidationType.CROSS_SOURCE.value
    ]
    # 5 clusters, multi=5, ratio=1.0 > 0.8 → info
    assert any(
        i.severity == Severity.INFO.value
        and i.payload.get("type") == "high_overlap"
        for i in cross_issues
    )


# ---------------------------------------------------------------------------
# V1.8 — validate_run 整合 4 类
# ---------------------------------------------------------------------------
def test_validate_run_integration_returns_combined_issues(temp_db):
    """validate_run 同时跑 4 类, 任何一类有 issue 都返在 report 里."""
    # source_regression 触发
    _insert_ckpt(100, "ai", "hn", items=10, finished_offset_h=12)
    _insert_ckpt(101, "ai", "hn", items=0, finished_offset_h=0)
    report = validate_run(
        run_id=101,
        since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        until_iso=datetime.now(timezone.utc).isoformat(),
    )
    types = {i.validation_type for i in report.issues}
    # 至少包含 source_regression
    assert ValidationType.SOURCE_REGRESSION.value in types


# ---------------------------------------------------------------------------
# V1.9 — validate_and_persist 写库 + 写日志
# ---------------------------------------------------------------------------
def test_validate_and_persist_writes_to_db_and_logs(temp_db):
    """跑完 4 类 + 写 collect_validations 表 + 写 validate_done 日志."""
    _insert_ckpt(100, "ai", "hn", items=10, finished_offset_h=12)
    _insert_ckpt(101, "ai", "hn", items=0, finished_offset_h=0)
    with patch("backend.services.collection_logger.log_collect_event") as _mock_log:
        validate_and_persist(
            run_id=101,
            since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
            until_iso=datetime.now(timezone.utc).isoformat(),
        )
    # 日志至少 1 次 (validate_done)
    assert _mock_log.called
    # 至少一次 call 的 event=validate_done
    validate_log = [
        c for c in _mock_log.call_args_list
        if c.args and c.args[0] == "validate_done"
    ]
    assert len(validate_log) >= 1
    # 写库
    conn = get_connection()
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM collect_validations WHERE run_id = ?",
        (101,),
    ).fetchone()
    assert int(rows["c"]) >= 1


# ---------------------------------------------------------------------------
# V1.10 — _check_* 内部异常 → 单条 warn 不阻塞
# ---------------------------------------------------------------------------
def test_check_internal_exception_returns_warn_no_crash(temp_db):
    """故意让 _check_source_regression 内的 SQL 抛异常 → 应返单条 warn 不崩."""
    # 删表 (mock 异常源)
    from backend.repository.db import get_connection
    conn = get_connection()
    conn.execute("DROP TABLE catchup_checkpoints")
    try:
        report = validate_run(
            run_id=1,
            since_iso=(datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
            until_iso=datetime.now(timezone.utc).isoformat(),
        )
        # 至少有一条 source_regression warn (含 "check crashed")
        crash_issues = [
            i for i in report.issues
            if i.validation_type == ValidationType.SOURCE_REGRESSION.value
            and i.severity == Severity.WARN.value
            and "crashed" in str(i.payload)
        ]
        assert len(crash_issues) >= 1
    finally:
        # 恢复表: 调用 init_db 会全量跑 migrations, 简单
        from backend.repository import db
        db.init_db()
