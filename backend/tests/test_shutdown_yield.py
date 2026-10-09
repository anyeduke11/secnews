"""DEV-0308 R14 — 停机协作让出契约测试。

批循环 (classify / semantic / intake) 跑在 worker 线程, 主线程 executor
join 等待; 哨兵置位后继续烧 LLM/写库 = 拉长停机 + 白耗算力。本文件锁定:
1. 探针与 core/events 哨兵联动 (fail-open);
2. 三批循环在条目边界让出 + 各自自愈语义 (semantic 下轮重判 / intake 游标冻结)。
哨兵状态 autouse 复位 (test_sse_shutdown 泄漏教训)。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.core import events as core_events
from backend.utils.shutdown import shutdown_yield_requested


@pytest.fixture(autouse=True)
def _reset_shutdown_sentinel():
    core_events._shutdown_requested = False
    yield
    core_events._shutdown_requested = False


# ---------------------------------------------------------------------------
# 探针联动
# ---------------------------------------------------------------------------
def test_probe_tracks_sentinel():
    assert shutdown_yield_requested() is False
    core_events._shutdown_requested = True
    assert shutdown_yield_requested() is True


# ---------------------------------------------------------------------------
# classify_items_with_ai: 条目边界让出
# ---------------------------------------------------------------------------
def _classify_items(n: int) -> list[dict]:
    return [
        {"id": f"c{i}", "title": f"title {i}", "tags": ["python"]}
        for i in range(n)
    ]


def test_classify_yields_immediately_when_flagged(monkeypatch):
    from backend.services import auto_classifier as ac

    monkeypatch.setattr(ac, "_ai_classify_enabled", lambda: False)
    core_events._shutdown_requested = True
    results, llm_used = ac.classify_items_with_ai(_classify_items(5))
    assert results == [] and llm_used == 0  # 首条目即让出, 零调用零处理


def test_classify_processes_all_when_no_shutdown(monkeypatch):
    """回归: 未停机时行为不变 (全量处理)。"""
    from backend.services import auto_classifier as ac

    monkeypatch.setattr(ac, "_ai_classify_enabled", lambda: False)
    results, llm_used = ac.classify_items_with_ai(_classify_items(3))
    assert len(results) == 3 and llm_used == 0


def test_classify_yields_midway_after_2_items(monkeypatch):
    from backend.services import auto_classifier as ac

    monkeypatch.setattr(ac, "_ai_classify_enabled", lambda: False)
    seq = iter([False, False, True, True, True])
    monkeypatch.setattr(
        "backend.utils.shutdown.shutdown_yield_requested", lambda: next(seq)
    )
    results, _ = ac.classify_items_with_ai(_classify_items(5))
    assert len(results) == 2  # 前 2 条处理, 第 3 条起让出


# ---------------------------------------------------------------------------
# post_ingest_semantic_filter: 让出 + skipped_reason 诚实可见
# ---------------------------------------------------------------------------
def test_semantic_filter_yields_before_first_llm(temp_db, monkeypatch):
    from backend.repository.db import get_connection
    from backend.services import info_filter_gate as ifg

    conn = get_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        conn.execute(
            "INSERT INTO hotspots (id, title, summary, url, source, category, "
            "quality_score, published_at, fetched_at, is_hidden, quality_flags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '[]')",
            (
                f"sem{i}", f"t{i}", f"s{i}", f"http://x/{i}", "src", "security",
                80, now_iso, now_iso,
            ),
        )
    calls: list = []
    monkeypatch.setattr(
        "backend.services.ai_hub.tasks.semantic_verdict",
        lambda *a, **k: calls.append(1) or {"verdict": "keep", "reason": "stub"},
    )
    monkeypatch.setattr(ifg, "_is_enabled", lambda: True)
    monkeypatch.setattr(ifg, "_semantic_enabled", lambda: True)
    core_events._shutdown_requested = True

    summary = ifg.post_ingest_semantic_filter()
    assert summary["skipped_reason"] == "shutdown_yield"
    assert summary["judged"] == 0
    assert calls == [], "让出后不得烧 LLM 调用"
    # 未判别条目不打标 → 下轮窗口重扫自愈
    rows = conn.execute(
        "SELECT quality_flags FROM hotspots WHERE id LIKE 'sem%'"
    ).fetchall()
    assert all("semantic_checked" not in r["quality_flags"] for r in rows)


# ---------------------------------------------------------------------------
# run_auto_intake: 让出 → 游标冻结 (不吞低时间戳未处理项)
# ---------------------------------------------------------------------------
def test_auto_intake_yield_freezes_cursor(monkeypatch):
    from backend.services import auto_intake_service as ais

    cursor_writes: list[str] = []
    monkeypatch.setattr(
        ais, "get_auto_intake_config", lambda: {
            "enabled": True, "daily_limit": 10,
            "min_quality_score": 50, "require_domain_hit": False,
        }
    )
    monkeypatch.setattr(ais, "today_intaken_count", lambda: 0)
    monkeypatch.setattr(
        ais.SettingsRepository, "get",
        lambda self, k, default=None: "2020-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        ais.SettingsRepository, "set",
        lambda self, k, v: cursor_writes.append(v),
    )
    monkeypatch.setattr(
        ais.HotspotRepository, "candidates_for_auto_intake",
        lambda self, **kw: [
            {"id": f"a{i}", "title": f"t{i}", "url": f"http://x/{i}",
             "summary": "s", "category": "security", "ingested_at": f"2024-0{i+1}-01T00:00:00+00:00"}
            for i in range(3)
        ],
    )
    promoted: list = []
    monkeypatch.setattr(
        "backend.services.sag_service.promote_favorite_to_knowledge",
        lambda **kw: promoted.append(kw["url"]),
    )
    core_events._shutdown_requested = True

    result = ais.run_auto_intake()
    assert result["evaluated"] == 3
    assert promoted == [], "让出后不得继续入管"
    assert cursor_writes == [], "让出轮次游标必须冻结 (候选处理序与时间戳无关, 推进即吞项)"
