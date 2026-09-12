"""quality_query_service 单测 (Batch 2 SQL 下沉).

覆盖:
  - list_source_reputation: 排序 + blacklist bool 转换
  - query_rejection_log: 全量 / gate 筛选 / 分页 total
  - rejection_stats: by_gate 聚合 + trend 按日
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.services import quality_query_service as qqs


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_quality_query_service.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_rejection(gate: str, source_id: str, created_at: str) -> None:
    db.get_connection().execute(
        "INSERT INTO quality_rejection_log "
        "(source_id, item_title, item_url, rejected_by, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, f"title-{created_at}", "https://example.com/x", gate,
         "test", created_at),
    )


def test_list_source_reputation_sorted_and_bool(temp_db):
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO source_reputation (source, score, blacklist, pass_count, "
        "fail_count, last_updated) VALUES (?, ?, ?, ?, ?, ?)",
        ("b-src", 50, 1, 10, 5, "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO source_reputation (source, score, blacklist, pass_count, "
        "fail_count, last_updated) VALUES (?, ?, ?, ?, ?, ?)",
        ("a-src", 90, 0, 20, 0, "2026-01-02T00:00:00+00:00"),
    )
    conn.commit()

    sources = qqs.list_source_reputation()
    by_source = {s["source"]: s for s in sources}
    # 迁移 002 会 seed 基线行, 只断言插入的两行按 score 倒序排列
    assert by_source["a-src"]["score"] == 90
    assert by_source["b-src"]["score"] == 50
    assert sources.index(by_source["a-src"]) < sources.index(by_source["b-src"])
    assert by_source["a-src"]["blacklist"] is False
    assert by_source["b-src"]["blacklist"] is True
    for field in ("source", "score", "blacklist", "pass_count", "fail_count", "last_updated"):
        assert field in by_source["a-src"]


def test_query_rejection_log_filters_and_pagination(temp_db):
    _insert_rejection("recency", "cat:src-a", "2026-01-01T10:00:00")
    _insert_rejection("score", "cat:src-b", "2026-01-02T10:00:00")
    db.get_connection().commit()

    all_rows = qqs.query_rejection_log()
    assert all_rows["total"] == 2
    assert all_rows["page"] == 1
    assert all_rows["page_size"] == 50
    assert len(all_rows["items"]) == 2
    # created_at 倒序
    assert all_rows["items"][0]["created_at"] > all_rows["items"][1]["created_at"]

    gated = qqs.query_rejection_log(gate_name="recency")
    assert gated["total"] == 1
    assert gated["items"][0]["rejected_by"] == "recency"

    paged = qqs.query_rejection_log(page=1, page_size=1)
    assert paged["total"] == 2
    assert len(paged["items"]) == 1


def test_rejection_stats_by_gate_and_trend(temp_db):
    _insert_rejection("recency", "cat:src-a", "2026-01-01T10:00:00")
    _insert_rejection("recency", "cat:src-b", "2026-01-01T11:00:00")
    _insert_rejection("score", "cat:src-c", "2026-01-02T10:00:00")
    db.get_connection().commit()

    stats = qqs.rejection_stats()
    by_gate = {r["gate_name"]: r["count"] for r in stats["by_gate"]}
    assert by_gate == {"recency": 2, "score": 1}
    trend = {r["day"]: r["count"] for r in stats["trend"]}
    assert trend == {"2026-01-01": 2, "2026-01-02": 1}

    # date 筛选只统计区间内
    filtered = qqs.rejection_stats(date_from="2026-01-02T00:00:00")
    assert {r["gate_name"]: r["count"] for r in filtered["by_gate"]} == {"score": 1}
