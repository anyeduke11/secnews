"""采集闭环 T1/T3 — source_prober 探测口径 + 失效源自动退役闭环测试.

覆盖:
- T1: 探测 alive 零产出不抬 last_yield_at / 有产出才抬 / last_error NULL
- T3: dead>14d 探测失败自动退役 / 13d 不退役 / retired 低频探测 /
      探测成功复活 / source_alerts 去重 bump
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection

# ---------------------------------------------------------------------------
# Fixtures — 隔离 DB 到 tmp_path (真实 migration schema, 同 test_source_alerter)
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path."""
    test_db = tmp_path / "test_source_prober.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def head_status(monkeypatch: pytest.MonkeyPatch):
    """可控的 _head_status 桩: responses dict 映射 source_id → (code, err)."""
    import backend.services.source_prober as prober_mod

    responses: dict[str, tuple[int, str | None]] = {}

    def _fake_head(url: str, t: int) -> tuple[int, str | None]:
        return responses.get(_url_owner(url), (200, None))

    monkeypatch.setattr(prober_mod, "_head_status", _fake_head)

    class _Stub:
        def set(self, source_id: str, code: int, err: str | None = None) -> None:
            responses[source_id] = (code, err)

    return _Stub()


_URL_OWNERS: dict[str, str] = {}


def _url_owner(url: str) -> str:
    return _URL_OWNERS.get(url, "unknown")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source(
    source_id: str,
    *,
    status: str = "dead",
    enabled: int = 1,
    name: str = "",
    last_success_at: str | None = None,
    last_yield_at: str | None = None,
    cooldown_until: str | None = None,
    url: str = "",
) -> None:
    """插入 crawler_sources 行 (探测域), 并登记 URL→id 映射供 HEAD 桩路由."""
    if not name:
        name = source_id
    probe_url = url or f"https://example.com/{source_id}/feed"
    _URL_OWNERS[probe_url] = source_id
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, url, feed_url, status, enabled,
             consecutive_failures, health_score, last_success_at, last_yield_at,
             cooldown_until, created_at, updated_at)
        VALUES (?, 'ai', ?, 'rss', ?, ?, ?, ?,
                5, 0.1, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (source_id, name, probe_url, probe_url, status, enabled,
         last_success_at, last_yield_at, cooldown_until),
    )


def _get_source(source_id: str) -> dict:
    row = get_connection().execute(
        "SELECT * FROM crawler_sources WHERE id = ?", (source_id,)
    ).fetchone()
    assert row is not None, f"source {source_id} missing"
    return dict(row)


def _days_ago_iso(days: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()


def _probe(source_id: str, **kwargs):
    from backend.services.source_prober import probe_one

    return probe_one(source_id, **kwargs)


# ===================================================================
# T1 — yield 口径
# ===================================================================


class TestProbeYieldSemantics:
    def test_probe_alive_zero_yield_keeps_last_yield_at(self, temp_db, head_status):
        """探测连通但零产出 → 回 grace 但不动 last_yield_at (病灶: 探测污染 yield)."""
        _insert_source(
            "p-zero", status="dead",
            last_yield_at="2020-01-01T00:00:00+00:00",
            last_success_at="2020-01-01T00:00:00+00:00",
        )
        head_status.set("p-zero", 200, None)
        result = _probe("p-zero")
        assert result.status == "alive"
        assert result.new_status == "grace"
        row = _get_source("p-zero")
        assert row["status"] == "grace"
        assert row["consecutive_failures"] == 0
        assert row["last_yield_at"] == "2020-01-01T00:00:00+00:00"
        assert row["last_success_at"] == "2020-01-01T00:00:00+00:00"

    def test_probe_alive_with_items_bumps_yield(self, temp_db, head_status):
        """探测运行有真实条目入库 (produced_items>0) → 抬 yield/success。"""
        _insert_source("p-yield", status="dead", last_yield_at=None)
        head_status.set("p-yield", 200, None)
        result = _probe("p-yield", produced_items=5)
        assert result.status == "alive"
        row = _get_source("p-yield")
        assert row["last_yield_at"] is not None
        assert row["last_success_at"] is not None

    def test_probe_alive_clears_last_error_to_null(self, temp_db, head_status):
        """探测成功 → last_error 存 NULL 而非空字符串。"""
        _insert_source("p-err", status="dead")
        get_connection().execute(
            "UPDATE crawler_sources SET last_error = 'HTTP 503' WHERE id = 'p-err'"
        )
        head_status.set("p-err", 200, None)
        _probe("p-err")
        row = _get_source("p-err")
        assert row["last_error"] is None

    def test_probe_dead_keeps_error(self, temp_db, head_status):
        """探测失败 → 保留 dead + 写真实错误。"""
        _insert_source("p-dead", status="dead")
        head_status.set("p-dead", 0, "URLError: conn refused")
        result = _probe("p-dead")
        assert result.status == "dead"
        assert result.new_status == "dead"
        row = _get_source("p-dead")
        assert row["status"] == "dead"
        assert "conn refused" in (row["last_error"] or "")


# ===================================================================
# T3 — 失效源自动退役闭环 (owner 裁决②)
# ===================================================================


def _alert_count(source_id: str, alert_type: str) -> int:
    row = get_connection().execute(
        "SELECT COUNT(*) AS cnt FROM source_alerts "
        "WHERE source_id = ? AND alert_type = ?",
        (source_id, alert_type),
    ).fetchone()
    return int(row["cnt"])


def _get_alert(source_id: str, alert_type: str) -> dict:
    row = get_connection().execute(
        "SELECT * FROM source_alerts "
        "WHERE source_id = ? AND alert_type = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (source_id, alert_type),
    ).fetchone()
    assert row is not None, f"no {alert_type} alert for {source_id}"
    return dict(row)


class TestAutoRetirement:
    def test_dead_13d_not_retired(self, temp_db, head_status):
        """13d (< 14d) 死亡 + 探测失败 → 保持 dead, 不退役无告警。"""
        _insert_source("r-13d", status="dead", last_success_at=_days_ago_iso(13))
        head_status.set("r-13d", 0, "URLError: refused")
        result = _probe("r-13d")
        row = _get_source("r-13d")
        assert result.new_status == "dead"
        assert row["status"] == "dead"
        assert row["enabled"] == 1
        assert _alert_count("r-13d", "source_retired") == 0

    def test_dead_15d_probe_fail_retires(self, temp_db, head_status):
        """15d (> 14d) 死亡 + 探测失败 → enabled=0, status='retired' + P1 告警。"""
        _insert_source(
            "r-15d", status="dead", name="僵尸源",
            last_success_at=_days_ago_iso(15),
        )
        head_status.set("r-15d", 0, "URLError: refused")
        result = _probe("r-15d")
        assert result.new_status == "retired"
        row = _get_source("r-15d")
        assert row["status"] == "retired"
        assert row["enabled"] == 0
        assert row["cooldown_until"] is not None  # 下次可复探时刻已武装
        alert = _get_alert("r-15d", "source_retired")
        assert alert["level"] == "P1"
        assert "僵尸源" in alert["message"]
        assert "15" in alert["message"]  # 死亡时长入 message

    def test_dead_never_succeeded_falls_back_to_created_at(self, temp_db, head_status):
        """从未产出 (last_success_at NULL) → 死亡起点回退 created_at 口径。"""
        conn = get_connection()
        _insert_source("r-never", status="dead")
        # created_at 设为 30 天前 (覆盖 INSERT 的 datetime('now'))
        conn.execute(
            "UPDATE crawler_sources "
            "SET created_at = datetime('now', '-30 days') WHERE id = 'r-never'"
        )
        head_status.set("r-never", 0, "URLError: refused")
        result = _probe("r-never")
        assert result.new_status == "retired"
        assert _get_source("r-never")["status"] == "retired"


class TestRetiredRevival:
    def test_retired_probe_success_revives(self, temp_db, head_status):
        """retired 探测成功 → enabled=1, 回 grace, 冷却清空 + source_revived。"""
        _insert_source(
            "rev-1", status="retired", enabled=0,
            last_success_at=_days_ago_iso(30),
            cooldown_until=_days_ago_iso(1),  # 复探期已到
        )
        head_status.set("rev-1", 200, None)
        result = _probe("rev-1")
        assert result.status == "alive"
        row = _get_source("rev-1")
        assert row["status"] == "grace"
        assert row["enabled"] == 1
        assert row["cooldown_until"] is None
        alert = _get_alert("rev-1", "source_revived")
        assert alert["source_id"] == "rev-1"

    def test_retired_reprobe_fail_rearms_cooldown(self, temp_db, head_status):
        """retired 复探仍失败 → 保持退役 + 重新武装 7 天冷却。"""
        _insert_source(
            "rev-2", status="retired", enabled=0,
            last_success_at=_days_ago_iso(30),
            cooldown_until=_days_ago_iso(1),
        )
        head_status.set("rev-2", 0, "URLError: refused")
        result = _probe("rev-2")
        assert result.new_status == "retired"
        row = _get_source("rev-2")
        assert row["status"] == "retired"
        assert row["enabled"] == 0
        # 冷却被重新武装到未来 (≈ +7d)
        due = datetime.fromisoformat(row["cooldown_until"])
        assert due > datetime.now(timezone.utc) + timedelta(days=6)


class TestRetiredLowFrequency:
    def test_retired_within_reprobe_window_excluded(self, temp_db):
        """retired 且复探冷却未到 → 不在探测清单 (每周一次而非每日)。"""
        _insert_source(
            "lf-1", status="retired", enabled=0,
            cooldown_until=_days_ago_iso(-3),  # 未来 3 天
        )
        _insert_source("lf-2", status="dead", enabled=1)
        from backend.services.source_prober import list_dead_sources

        ids = {s["id"] for s in list_dead_sources()}
        assert "lf-1" not in ids
        assert "lf-2" in ids

    def test_retired_due_included(self, temp_db):
        """retired 且复探冷却已过 → 重新纳入探测清单 (曾服役源)。"""
        _insert_source(
            "lf-3", status="retired", enabled=0,
            cooldown_until=_days_ago_iso(1),
            last_success_at=_days_ago_iso(20),
        )
        from backend.services.source_prober import list_dead_sources

        assert "lf-3" in {s["id"] for s in list_dead_sources()}

    def test_retired_never_served_not_probed(self, temp_db):
        """归档残留 (retired 但从未成功抓取, last_success_at NULL) 不得被
        复探自动复活 — 终审 Important 修复: 探测只复活曾服役源。"""
        _insert_source(
            "lf-5", status="retired", enabled=0,
            cooldown_until=_days_ago_iso(1),
        )
        from backend.services.source_prober import list_dead_sources

        assert "lf-5" not in {s["id"] for s in list_dead_sources()}

    def test_probe_all_dead_skips_fresh_retired(self, temp_db, head_status):
        """端到端: 退役当轮 → probe_all_dead 立即重跑不再触碰该源 (低频生效)。"""
        _insert_source(
            "lf-4", status="dead", last_success_at=_days_ago_iso(20),
        )
        head_status.set("lf-4", 0, "URLError: refused")
        from backend.services.source_prober import probe_all_dead

        first = probe_all_dead()
        assert any(r["source_id"] == "lf-4" and r["new_status"] == "retired"
                   for r in first)
        error_after_retire = _get_source("lf-4")["last_error"]
        second = probe_all_dead()
        assert all(r["source_id"] != "lf-4" for r in second)
        assert _get_source("lf-4")["last_error"] == error_after_retire


# ===================================================================
# T3 — 同 host 探测节拍 (2026-09-27 论文源限流根因修复)
# ===================================================================


class TestSameHostProbePacing:
    def test_probe_all_dead_paces_same_host(self, temp_db, head_status, monkeypatch):
        """同 host 相邻探测强制 ≥3.1s 节拍, 不同 host 不等待。

        病灶: probe_all_dead 对 14 条 arXiv dead 源零节拍连发 HEAD,
        违反 arXiv "单请求 ≥3s" 约束遭 Fastly 间歇性拒绝 (400/406),
        源永久卡死 dead, paper 采集从未生效。"""
        import backend.services.source_prober as prober_mod

        sleeps: list[float] = []
        monkeypatch.setattr(prober_mod.time, "sleep", sleeps.append)

        _insert_source("px-1", url="https://api.arxiv.org/a/feed")
        _insert_source("px-2", url="https://api.arxiv.org/b/feed")
        _insert_source("py-1", url="https://other.example.org/c/feed")
        head_status.set("px-1", 200, None)
        head_status.set("px-2", 200, None)
        head_status.set("py-1", 200, None)

        from backend.services.source_prober import probe_all_dead

        results = probe_all_dead()
        assert {r["status"] for r in results} == {"alive"}
        # 恰好一次节拍等待 (同 host 第 2/3... 跳), 且间隔值符合 arXiv 约束
        assert len(sleeps) == 1, f"expected 1 pacing sleep, got {sleeps}"
        assert sleeps[0] > 3.0


# ===================================================================
# T3 — 告警去重 (upsert_dedup)
# ===================================================================


class TestAlertDedup:
    def test_dedup_bumps_existing_instead_of_insert(self, temp_db):
        """同 source_id+alert_type 存在 → 不新插, bump detail/created_at。"""
        from backend.repository.source_alert_repo import SourceAlertRepository

        repo = SourceAlertRepository()
        action, id1 = repo.upsert_dedup({
            "source_id": "dup-1", "alert_type": "source_retired",
            "level": "P1", "message": "第一次", "detail": '{"n": 1}',
        })
        assert action == "inserted"
        action, id2 = repo.upsert_dedup({
            "source_id": "dup-1", "alert_type": "source_retired",
            "level": "P1", "message": "第二次", "detail": '{"n": 2}',
        })
        assert action == "bumped"
        assert id1 == id2
        assert _alert_count("dup-1", "source_retired") == 1
        alert = _get_alert("dup-1", "source_retired")
        assert alert["message"] == "第二次"
        assert alert["detail"] == '{"n": 2}'

    def test_dedup_different_type_inserts_separately(self, temp_db):
        from backend.repository.source_alert_repo import SourceAlertRepository

        repo = SourceAlertRepository()
        repo.upsert_dedup({
            "source_id": "dup-2", "alert_type": "source_retired",
            "message": "retired",
        })
        action, _ = repo.upsert_dedup({
            "source_id": "dup-2", "alert_type": "source_revived",
            "message": "revived",
        })
        assert action == "inserted"
        assert _alert_count("dup-2", "source_retired") == 1
        assert _alert_count("dup-2", "source_revived") == 1

    def test_repeated_probe_failure_keeps_single_alert(self, temp_db, head_status):
        """端到端: retired 源两轮复探失败 → source_retired 仅 1 行 (bump)。"""
        _insert_source(
            "dup-3", status="retired", enabled=0,
            last_success_at=_days_ago_iso(30),
            cooldown_until=_days_ago_iso(1),
        )
        head_status.set("dup-3", 0, "URLError: refused")
        _probe("dup-3")
        _probe("dup-3")
        assert _alert_count("dup-3", "source_retired") == 1
