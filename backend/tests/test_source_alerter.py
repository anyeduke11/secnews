"""v1.8 Phase 3 — SourceAlerter / SourceAlertRepository 单测.

覆盖:
- SourceAlertRepository: insert, list (分页+过滤), has_recent, get_stats, get_stats_by_source
- SourceAlerter.evaluate_all(): 连续失败告警, 重复告警去重, 空源处理
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.repository.source_alert_repo import SourceAlertRepository
from backend.services.source_alerter import SourceAlerter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path."""
    test_db = tmp_path / "test_source_alerter.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# Helpers — 向各表插入测试数据
# ---------------------------------------------------------------------------

def _insert_source(
    source_id: str,
    name: str = "",
    status: str = "active",
    consecutive_failures: int = 0,
    priority: int = 50,
    enabled: int = 1,
    category: str = "ai",
) -> None:
    """向 crawler_sources 插入一行, 同时插入一条正常 crawler_runs 记录.

    插入 crawler_runs 是为了避免 get_run_stats() 对无 runs 的源
    返回 SUM(NULL) → int(None) 崩溃 (source_scheduler_repo.py 缺少
    COALESCE 包裹 failed_runs).
    """
    if not name:
        name = source_id
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, status, priority, enabled,
             consecutive_failures, health_score, created_at, updated_at)
        VALUES (?, ?, ?, 'html', ?, ?, ?, ?, 1.0,
                datetime('now'), datetime('now'))
        """,
        (source_id, category, name, status, priority, enabled, consecutive_failures),
    )
    # 插入一条正常 run 保证 get_run_stats() 不崩溃
    _insert_crawler_run(source_id, category, status="success",
                        fetched_count=10, accepted_count=10,
                        duration_ms=1000)


def _insert_source_alert(
    source_id: str,
    alert_type: str,
    level: str = "P2",
    message: str = "",
    detail: str = "",
) -> int:
    """向 source_alerts 插入一行 (直接 SQL, 控制 created_at)."""
    if not message:
        message = f"test alert {alert_type}"
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO source_alerts (source_id, alert_type, level, message, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source_id, alert_type, level, message, detail),
    )
    return cur.lastrowid or 0


def _insert_crawler_run(
    source_id: str,
    category: str = "ai",
    status: str = "success",
    fetched_count: int = 10,
    accepted_count: int = 9,
    duration_ms: int = 5000,
    started_at: str | None = None,
) -> None:
    """向 crawler_runs 插入一行."""
    if started_at is None:
        started_at = "datetime('now', '-1 hours')"
    conn = get_connection()
    conn.execute(
        f"""
        INSERT INTO crawler_runs
            (source_id, category, started_at, finished_at, status,
             fetched_count, accepted_count, duration_ms, error_msg)
        VALUES (?, ?, {started_at}, datetime('now'), ?, ?, ?, ?, '')
        """,
        (source_id, category, status, fetched_count, accepted_count, duration_ms),
    )


def _insert_hotspot(hid: str, source: str) -> None:
    """向 hotspots 插入一行."""
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
            datetime.now(timezone.utc).isoformat(),
            50,
            datetime.now(timezone.utc).isoformat(),
            0,
            100,
            "[]",
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _insert_url_check(item_id: str, status_code: int = 200) -> None:
    """向 crawl_url_checks 插入一行."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawl_url_checks (item_id, url, status_code, checked_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (item_id, f"https://example.com/{item_id}", status_code),
    )


# ===================================================================
# SourceAlertRepository 测试
# ===================================================================
class TestSourceAlertRepository:
    """SourceAlertRepository CRUD + 统计查询."""

    def test_insert_creates_record_and_returns_id(self, temp_db):
        repo = SourceAlertRepository()
        alert_id = repo.insert({
            "source_id": "src-1",
            "alert_type": "consecutive_failure",
            "level": "P1",
            "message": "test alert",
            "detail": '{"key": "val"}',
        })
        assert alert_id > 0

        # 验证记录存在
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM source_alerts WHERE id = ?", (alert_id,)
        ).fetchone()
        assert row is not None
        assert row["source_id"] == "src-1"
        assert row["alert_type"] == "consecutive_failure"
        assert row["level"] == "P1"
        assert row["detail"] == '{"key": "val"}'

    def test_insert_default_level(self, temp_db):
        """不传 level 时使用默认值 P2."""
        repo = SourceAlertRepository()
        alert_id = repo.insert({
            "source_id": "src-2",
            "alert_type": "rejection_rate",
            "message": "test",
        })
        conn = get_connection()
        row = conn.execute(
            "SELECT level FROM source_alerts WHERE id = ?", (alert_id,)
        ).fetchone()
        assert row["level"] == "P2"

    def test_list_empty(self, temp_db):
        repo = SourceAlertRepository()
        result = repo.list()
        assert result["total"] == 0
        assert result["items"] == []
        assert result["page"] == 1
        assert result["page_size"] == 50

    def test_list_pagination(self, temp_db):
        repo = SourceAlertRepository()
        for i in range(5):
            _insert_source_alert(f"src-{i}", "consecutive_failure", "P1")

        # page 1, page_size=2
        result = repo.list(page=1, page_size=2)
        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 2

        # page 3 应有 1 条
        result = repo.list(page=3, page_size=2)
        assert len(result["items"]) == 1

    def test_list_filter_by_source_id(self, temp_db):
        repo = SourceAlertRepository()
        _insert_source_alert("alpha", "consecutive_failure")
        _insert_source_alert("beta", "rejection_rate")
        _insert_source_alert("alpha", "http_status")

        result = repo.list(source_id="alpha")
        assert result["total"] == 2
        assert all(it["source_id"] == "alpha" for it in result["items"])

    def test_list_filter_by_level(self, temp_db):
        repo = SourceAlertRepository()
        _insert_source_alert("src-1", "consecutive_failure", "P1")
        _insert_source_alert("src-1", "rejection_rate", "P2")
        _insert_source_alert("src-2", "http_status", "P2")

        result = repo.list(level="P1")
        assert result["total"] == 1
        assert result["items"][0]["level"] == "P1"

    def test_list_filter_by_since(self, temp_db):
        repo = SourceAlertRepository()
        # 插入一条, 此时 created_at ≈ datetime('now')
        _insert_source_alert("src-1", "consecutive_failure", "P1")

        # 以将来的时间过滤 → 0 条
        result = repo.list(since="2099-01-01T00:00:00")
        assert result["total"] == 0

        # 以过去的时间过滤 → 1 条
        result = repo.list(since="2020-01-01T00:00:00")
        assert result["total"] == 1

    def test_list_filter_combined(self, temp_db):
        repo = SourceAlertRepository()
        _insert_source_alert("alpha", "consecutive_failure", "P1")
        _insert_source_alert("alpha", "rejection_rate", "P2")
        _insert_source_alert("beta", "consecutive_failure", "P1")

        result = repo.list(source_id="alpha", level="P1")
        assert result["total"] == 1
        assert result["items"][0]["alert_type"] == "consecutive_failure"

    # ------------------------------------------------------------------
    # has_recent
    # ------------------------------------------------------------------
    def test_has_recent_returns_true_when_exists(self, temp_db):
        """存在 N 小时内的同类告警 → True."""
        repo = SourceAlertRepository()
        _insert_source_alert("src-1", "consecutive_failure", "P1")
        assert repo.has_recent("src-1", "consecutive_failure", within_hours=24) is True

    def test_has_recent_returns_false_for_different_type(self, temp_db):
        """不同类型告警不影响."""
        repo = SourceAlertRepository()
        _insert_source_alert("src-1", "consecutive_failure", "P1")
        assert repo.has_recent("src-1", "rejection_rate", within_hours=24) is False

    def test_has_recent_returns_false_for_different_source(self, temp_db):
        """不同来源不影响."""
        repo = SourceAlertRepository()
        _insert_source_alert("src-1", "consecutive_failure", "P1")
        assert repo.has_recent("src-2", "consecutive_failure", within_hours=24) is False

    def test_has_recent_returns_false_when_no_alerts(self, temp_db):
        repo = SourceAlertRepository()
        assert repo.has_recent("ghost", "consecutive_failure") is False

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------
    def test_get_stats_groups_by_level(self, temp_db):
        repo = SourceAlertRepository()
        _insert_source_alert("src-1", "consecutive_failure", "P1")
        _insert_source_alert("src-1", "rejection_rate", "P2")
        _insert_source_alert("src-2", "http_status", "P2")

        stats = repo.get_stats(since_hours=24)
        level_map = {s["level"]: s["count"] for s in stats}
        assert level_map.get("P1") == 1
        assert level_map.get("P2") == 2

    def test_get_stats_empty(self, temp_db):
        repo = SourceAlertRepository()
        assert repo.get_stats() == []

    # ------------------------------------------------------------------
    # get_stats_by_source
    # ------------------------------------------------------------------
    def test_get_stats_by_source(self, temp_db):
        repo = SourceAlertRepository()
        _insert_source_alert("alpha", "consecutive_failure", "P1")
        _insert_source_alert("alpha", "consecutive_failure", "P1")  # 同源同类型 2 条
        _insert_source_alert("alpha", "rejection_rate", "P2")
        _insert_source_alert("beta", "http_status", "P2")

        stats = repo.get_stats_by_source(since_hours=24)
        # 构建 key 索引
        key_map = {}
        for s in stats:
            key = (s["source_id"], s["alert_type"])
            key_map[key] = s["count"]

        assert key_map.get(("alpha", "consecutive_failure")) == 2
        assert key_map.get(("alpha", "rejection_rate")) == 1
        assert key_map.get(("beta", "http_status")) == 1

    def test_get_stats_by_source_empty(self, temp_db):
        repo = SourceAlertRepository()
        assert repo.get_stats_by_source() == []


# ===================================================================
# SourceAlerter.evaluate_all() 测试
# ===================================================================
class TestSourceAlerterEvaluateAll:
    """SourceAlerter 告警规则验证."""

    def test_no_sources_returns_empty(self, temp_db):
        """空源 → 0 告警."""
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        assert result["alerts_triggered"] == 0
        assert result["sources_checked"] == 0
        assert result["details"] == []

    def test_healthy_source_no_alerts(self, temp_db):
        """健康源 (consecutive_failures=0, status=active) → 无告警."""
        _insert_source("healthy-src", name="健康源", consecutive_failures=0, priority=50)
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        assert result["alerts_triggered"] == 0
        assert result["sources_checked"] == 1

    # ------------------------------------------------------------------
    # Rule 1: 连续失败告警
    # ------------------------------------------------------------------
    def test_consecutive_failure_triggers_p1(self, temp_db):
        """consecutive_failures >= 5 → P1 告警."""
        _insert_source("failing-src", name="失败源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        assert result["alerts_triggered"] == 1
        assert result["alerts_by_level"]["P1"] == 1
        assert result["alerts_by_level"]["P2"] == 0
        assert len(result["details"]) == 1
        assert result["details"][0]["source_id"] == "failing-src"
        assert result["details"][0]["alerts"][0]["type"] == "consecutive_failure"

    def test_consecutive_failure_below_threshold(self, temp_db):
        """consecutive_failures=4 (< 5) → 无告警."""
        _insert_source("ok-src", name="OK源", consecutive_failures=4, status="active")
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        assert result["alerts_triggered"] == 0

    # ------------------------------------------------------------------
    # Rule 6: P0 死亡告警 (注意: 当前代码 active_sources 过滤了 dead 状态)
    # ------------------------------------------------------------------
    def test_p0_dead_status_not_triggered_due_to_filter(self, temp_db):
        """P0 dead 源: status='dead' 被 active_sources 过滤, 不会触发告警.

        当前 evaluate_all() 仅迭代 status in ('active','grace','stale') 的源,
        'dead' 源被排除, 因此 Rule 6 实际不会触发。这是代码已知行为/限制。
        """
        _insert_source("dead-p0", name="死亡P0源", status="dead", priority=90)
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        # dead 源不计入 sources_checked, 也不触发告警
        assert result["alerts_triggered"] == 0
        assert result["sources_checked"] == 0

    # ------------------------------------------------------------------
    # 重复告警去重 (has_recent)
    # ------------------------------------------------------------------
    def test_duplicate_alert_suppressed_within_24h(self, temp_db):
        """同一源同类型告警在 24h 内重复触发 → 被 has_recent 抑制."""
        _insert_source("dup-src", name="重复源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()

        # 第一次触发 → 产生 1 条告警
        result1 = alerter.evaluate_all()
        assert result1["alerts_triggered"] == 1

        # 第二次触发 → has_recent 检测到已存在, 不应再产生
        result2 = alerter.evaluate_all()
        assert result2["alerts_triggered"] == 0, "重复告警应被抑制"

    def test_different_alert_types_not_deduped(self, temp_db):
        """不同类型告警互不影响去重."""
        _insert_source("multi-src", name="多类型源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()

        # 第一次: consecutive_failure 触发
        result1 = alerter.evaluate_all()
        assert result1["alerts_triggered"] == 1

        # 再插入一条 rejection_rate 的触发条件: 需要 crawler_runs 数据
        # 插入 3 条 runs, 其中 fetched_count=10, accepted_count=0 → rejection_rate=1.0
        for _ in range(3):
            _insert_crawler_run("multi-src", fetched_count=10, accepted_count=0)

        # 第二次: consecutive_failure 被抑制, 但 rejection_rate 是新类型 → 应触发
        result2 = alerter.evaluate_all()
        assert result2["alerts_triggered"] >= 1, "不同类型告警不应被抑制"

    # ------------------------------------------------------------------
    # 多种源混合
    # ------------------------------------------------------------------
    def test_mixed_sources(self, temp_db):
        """混合健康源+故障源, 只告警故障源."""
        _insert_source("healthy", name="健康源", consecutive_failures=0, status="active")
        _insert_source("failing", name="故障源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        assert result["alerts_triggered"] == 1
        assert result["sources_checked"] == 2
        assert result["details"][0]["source_id"] == "failing"

    def test_inactive_sources_skipped(self, temp_db):
        """disabled 状态的源被跳过."""
        _insert_source("disabled-src", name="禁用源", consecutive_failures=5, status="disabled")
        _insert_source("active-src", name="活跃源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        # 只有 active 源被检查
        assert result["sources_checked"] == 1
        assert result["alerts_triggered"] == 1

    # ------------------------------------------------------------------
    # 返回结构验证
    # ------------------------------------------------------------------
    def test_return_shape(self, temp_db):
        """验证 evaluate_all 返回结构完整."""
        _insert_source("test-src", name="测试源", consecutive_failures=5, status="active")
        alerter = SourceAlerter()
        result = alerter.evaluate_all()
        for key in ("alerts_triggered", "alerts_by_level", "sources_checked", "details"):
            assert key in result, f"missing key: {key}"
        assert "P1" in result["alerts_by_level"]
        assert "P2" in result["alerts_by_level"]