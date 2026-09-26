"""kl_transition_throughput — 管线吞吐视图 (治理 T3) 回归测试。

为什么需要吞吐口径 (第一性原理: 漏斗必须区分存量与流量)
--------------------------------------------------------
存量快照 (funnel_from_db) 回答"现在各阶段躺了多少条", 但 2026-09 实测
publish 存量 4179 条 vs 近 7 天流动 0 条 — 管线已停摆 13 天, 快照却依然
"看起来很健康"。吞吐口径 (wiki_events kl_transition 按 payload.stage 聚合)
才能暴露"最近到底有没有知识在流动", 是停摆判定的数据面。

契约:
- throughput_7d: 近 7 天 kl_transition 到达量, 按 STAGES 值域收口 (窗口外不计)
- conversion: 阶段间转化率 refine/raw, link/refine, structure/link,
  publish/structure; 前项为 0 时除零 → None (不许编造 0% 或 100%)
- last_transition_at: 最新 transition 时间 (停摆判定依据)
- wiki_events 表缺失等查询失败 → 归零结构, 不炸看板 (与 funnel 回退同哲学)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.services.wiki_stats_service import kl_transition_throughput


def _now_iso(offset_days: float = 0.0) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=offset_days)
    ).isoformat()


@pytest.fixture
def events_conn(tmp_path) -> sqlite3.Connection:
    """最小 wiki_events 替身 — 只带本查询触碰的列 (ts/kind/payload)。"""
    conn = sqlite3.connect(str(tmp_path / "events.db"), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE wiki_events (ts TEXT, kind TEXT, payload TEXT)"
    )
    return conn


def _insert_transition(conn: sqlite3.Connection, stage: str, ts: str) -> None:
    conn.execute(
        "INSERT INTO wiki_events (ts, kind, payload) VALUES (?, 'kl_transition', ?)",
        (ts, f'{{"stage": "{stage}", "next": null}}'),
    )


def test_throughput_counts_only_recent_window(events_conn):
    """吞吐只计窗口内的 transition — 存量快照与流量口径的边界。"""
    _insert_transition(events_conn, "kl:refine", _now_iso(1))
    _insert_transition(events_conn, "kl:refine", _now_iso(2))
    _insert_transition(events_conn, "kl:publish", _now_iso(0.5))
    # 窗口外 (8 天前) — 不计
    _insert_transition(events_conn, "kl:publish", _now_iso(8))

    out = kl_transition_throughput(events_conn)

    assert out["throughput_7d"]["kl:refine"] == 2
    assert out["throughput_7d"]["kl:publish"] == 1
    assert out["throughput_7d"]["kl:raw"] == 0


def test_conversion_rates_and_division_by_zero(events_conn):
    """转化率 = 后阶段到达量 / 前阶段到达量; 前项为 0 → None (不许编造)。"""
    _insert_transition(events_conn, "kl:raw", _now_iso(1))
    _insert_transition(events_conn, "kl:refine", _now_iso(1))
    _insert_transition(events_conn, "kl:refine", _now_iso(2))
    _insert_transition(events_conn, "kl:link", _now_iso(1))

    out = kl_transition_throughput(events_conn)

    conv = out["conversion"]
    assert conv["raw_to_refine"] == pytest.approx(2.0)  # refine 2 / raw 1
    assert conv["refine_to_link"] == pytest.approx(0.5)  # link 1 / refine 2
    # link 有量 → structure 0 / link 1;  structure 前项非零
    assert conv["link_to_structure"] == 0.0
    # structure 前项为 0 → 除零必须 None, 不能编 0% 或 100%
    assert conv["structure_to_publish"] is None


def test_empty_pipeline_all_conversions_null(events_conn):
    """零流动 (停摆现状) 时所有转化率都是 None — 不许把停摆画成 0% 流量。"""
    out = kl_transition_throughput(events_conn)

    assert all(v == 0 for v in out["throughput_7d"].values())
    assert all(v is None for v in out["conversion"].values())
    assert out["last_transition_at"] is None


def test_last_transition_at_ignores_window(events_conn):
    """last_transition_at 不受 7d 窗口限制 — 停摆 13 天也要报出最后心跳。"""
    _insert_transition(events_conn, "kl:publish", _now_iso(13))

    out = kl_transition_throughput(events_conn)

    assert out["throughput_7d"]["kl:publish"] == 0, "窗口外不计吞吐"
    assert out["last_transition_at"] is not None, "但停摆判定需要最后心跳时间"


def test_non_transition_kinds_excluded(events_conn):
    """只聚合 kl_transition — agent_write/kl_error 不许混进吞吐。"""
    events_conn.execute(
        "INSERT INTO wiki_events (ts, kind, payload) VALUES (?, 'agent_write', '{}')",
        (_now_iso(1),),
    )
    events_conn.execute(
        "INSERT INTO wiki_events (ts, kind, payload) "
        "VALUES (?, 'kl_error', '{\"stage\": \"kl:refine\"}')",
        (_now_iso(1),),
    )

    out = kl_transition_throughput(events_conn)

    assert out["throughput_7d"]["kl:refine"] == 0
    assert out["last_transition_at"] is None


def test_missing_wiki_events_table_returns_zeroed(tmp_path):
    """wiki_events 表缺失 → 归零结构, 不炸看板 (kl_queue 空表兼容同哲学)。"""
    conn = sqlite3.connect(str(tmp_path / "no_events.db"), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE marker (x INTEGER)")

    out = kl_transition_throughput(conn)

    assert all(v == 0 for v in out["throughput_7d"].values())
    assert out["last_transition_at"] is None


def test_unknown_stage_values_do_not_leak_into_domain(events_conn):
    """payload.stage 值域外的值不进吞吐域 (与 funnel unknown 语义对齐)。"""
    _insert_transition(events_conn, "kl:weird", _now_iso(1))
    _insert_transition(events_conn, "kl:publish", _now_iso(1))

    out = kl_transition_throughput(events_conn)

    assert out["throughput_7d"]["kl:publish"] == 1
    assert "kl:weird" not in out["throughput_7d"]
