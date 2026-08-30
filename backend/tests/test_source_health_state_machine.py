"""信源健康状态机回归测试.

为什么需要这个文件 (第一性原理: status 必须是"最近是否有产出"的事实函数)
--------------------------------------------------------------------
生产实测: 16 个源当轮仍有产出却永久停在 ``dead`` —— 其中 FreeBuf
``total_items=66968``、``last_seen_at`` 距写入不足 1 分钟、``zero_yield_runs=0``,
前端因此显示"119 离线"。根因是 ``source_stats_repo`` 的 ``new_status =
prev_status`` 单向棘轮: 产出使 ``new_zr=0`` 后两个分支都不再命中。

另一侧, 判死只用"连续零产出轮次"(阈值 6), 而 bid 类约 17 分钟一轮 → 1.7 小时
无新内容即判死, 实测 bid 类 64/64 全 dead (政府招标站夜间/周末本就不发布)。

覆盖:
  H1 dead 源当轮有产出 → 必须回 active (棘轮回归)
  H2 连续零产出但距上次产出不足时间下限 → 不判死 (至多 stale)
  H3 连续零产出且距上次产出超过时间下限 → 判死
  H4 从未产出过的源 → 不受时间下限保护, 按轮次判死
  H5 阈值可被 settings 热更新
  R1 复活门禁必须用 last_seen_at 度量"死了多久"
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.source_stats_repo import SourceStatsRepository
from backend.services.source_revival_service import list_dead_sources


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_source_health.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _status_of(source_name: str) -> tuple[str, int, int]:
    row = db.get_connection().execute(
        "SELECT status, zero_yield_runs, total_items FROM source_stats "
        "WHERE source_name = ?",
        (source_name,),
    ).fetchone()
    assert row is not None, f"{source_name} 未写入 source_stats"
    return str(row["status"]), int(row["zero_yield_runs"]), int(row["total_items"])


def _set_last_seen(source_name: str, hours_ago: float | None) -> None:
    """把 last_seen_at 拨到 N 小时前; None = 从未产出 (NULL)。"""
    val = None if hours_ago is None else (_now() - timedelta(hours=hours_ago)).isoformat()
    db.get_connection().execute(
        "UPDATE source_stats SET last_seen_at = ? WHERE source_name = ?",
        (val, source_name),
    )


def _run(repo: SourceStatsRepository, name: str, item_count: int, url: str) -> None:
    repo.upsert_after_run(
        category="bid", source_name=name, source_url=url, item_count=item_count,
    )


# ---------------------------------------------------------------------------
# H1 — 棘轮回归: 有产出必须复活
# ---------------------------------------------------------------------------
def test_dead_source_with_output_returns_to_active(temp_db):
    """dead 源在下一轮拿到内容后必须回到 active, 而不是永久停在 dead。"""
    repo = SourceStatsRepository()
    name, url = "ratchet-src", "https://example.com/ratchet"

    _run(repo, name, item_count=5, url=url)          # 首次有产出 → active
    _set_last_seen(name, hours_ago=100)              # 假装已沉默 100h
    for _ in range(8):
        _run(repo, name, item_count=0, url=url)      # 连续零产出 → dead
    assert _status_of(name)[0] == "dead", "前置条件: 应已判死"

    _run(repo, name, item_count=3, url=url)          # 当轮恢复产出
    status, zr, total = _status_of(name)
    assert status == "active", f"有产出仍停在 {status} —— 单向棘轮未修复"
    assert zr == 0
    assert total == 8


# ---------------------------------------------------------------------------
# H2 — 时间下限保护低频发布源
# ---------------------------------------------------------------------------
def test_recent_producer_not_killed_by_round_threshold_only(temp_db):
    """距上次产出不足 dead_min_hours 时, 零产出轮次再高也不判死。"""
    repo = SourceStatsRepository()
    name, url = "slow-publisher", "https://example.com/slow"

    _run(repo, name, item_count=2, url=url)
    _set_last_seen(name, hours_ago=1)                # 1 小时前刚有产出
    for _ in range(10):
        _run(repo, name, item_count=0, url=url)

    status = _status_of(name)[0]
    assert status != "dead", "低频发布源被轮次阈值误杀 (bid 64/64 全死的机制)"
    assert status == "stale"                          # 需注意, 但不是死


# ---------------------------------------------------------------------------
# H3 — 沉默足够久才判死
# ---------------------------------------------------------------------------
def test_long_idle_zero_yield_is_dead(temp_db):
    repo = SourceStatsRepository()
    name, url = "silent-src", "https://example.com/silent"

    _run(repo, name, item_count=2, url=url)
    _set_last_seen(name, hours_ago=200)              # 沉默 200h > 72h
    for _ in range(8):
        _run(repo, name, item_count=0, url=url)

    assert _status_of(name)[0] == "dead"


# ---------------------------------------------------------------------------
# H4 — 从未产出过的源不受时间下限保护
# ---------------------------------------------------------------------------
def test_never_produced_source_goes_dead(temp_db):
    """last_seen_at 为 NULL: 没有产出节奏可依, 退回按轮次判死。"""
    repo = SourceStatsRepository()
    name, url = "never-yielded", "https://example.com/never"

    for _ in range(8):
        _run(repo, name, item_count=0, url=url)

    assert _status_of(name)[1] == 8
    assert _status_of(name)[0] == "dead"
    assert _status_of(name)[2] == 0


# ---------------------------------------------------------------------------
# H5 — 阈值可热更新
# ---------------------------------------------------------------------------
def test_dead_min_hours_setting_is_honored(temp_db):
    """把时间下限调到 1h 后, 沉默 5h 的零产出源应能判死。"""
    db.get_connection().execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("quality.coverage_dead_min_hours", "1", _now().isoformat()),
    )
    repo = SourceStatsRepository()
    name, url = "tuned-src", "https://example.com/tuned"

    _run(repo, name, item_count=2, url=url)
    _set_last_seen(name, hours_ago=5)
    for _ in range(8):
        _run(repo, name, item_count=0, url=url)

    assert _status_of(name)[0] == "dead"


# ---------------------------------------------------------------------------
# R1 — 复活门禁必须度量"沉默多久"而非"上次尝试多久"
# ---------------------------------------------------------------------------
def test_revival_gate_uses_last_seen_not_last_checked(temp_db):
    """每轮采集都会刷新 last_checked_at → 以它做门禁会让复活回路恒假。

    构造真实场景: 源已沉默 10 天 (last_seen_at), 但刚刚还被采集尝试过
    (last_checked_at = now)。旧实现会跳过它, 复活探测恰好漏掉唯一该救的源。
    """
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO source_stats (category, source_name, source_url, status,"
        " total_runs, zero_yield_runs, total_items, last_seen_at,"
        " last_checked_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "security", "silent-but-tried", "https://example.com/sbt", "dead",
            50, 40, 900,
            (_now() - timedelta(days=10)).isoformat(),   # 沉默 10 天
            _now().isoformat(),                          # 刚刚尝试过
            _now().isoformat(),
        ),
    )

    names = {r["source_name"] for r in list_dead_sources(dead_for_days=7)}
    assert "silent-but-tried" in names, (
        "复活门禁仍在用 last_checked_at: 只要源还在被采集就永不入选"
    )
