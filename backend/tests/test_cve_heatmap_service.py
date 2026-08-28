"""S4-3 CVE heatmap service tests.

覆盖:
1. test_weekly_heatmap_empty — 空表返回空矩阵
2. test_weekly_heatmap_counts — 正确按周 + severity 聚合
3. test_weekly_heatmap_cvss_none — metadata 无 cvss → none bucket
4. test_weekly_heatmap_respects_weeks_param — weeks 参数截断
5. test_weekly_heatmap_invalid_date_skipped — 非法 created_at 被跳过
"""
from __future__ import annotations

import datetime
import json
import sqlite3

from backend.repository.db import get_connection
from backend.services.cve_heatmap_service import weekly_heatmap


def _get_conn() -> sqlite3.Connection:
    return get_connection()


def _insert_cve(conn: sqlite3.Connection, cve_id: str, cvss: float | None, created_iso: str) -> None:
    conn.execute(
        """INSERT INTO security_entities
               (id, entity_type, name, description, metadata, created_at, updated_at)
           VALUES (?, 'cve', ?, ?, ?, ?, ?)""",
        (
            cve_id,
            cve_id,
            f"Description for {cve_id}",
            json.dumps({"cvss": cvss}),
            created_iso,
            created_iso,
        ),
    )


class TestWeeklyHeatmap:
    def test_empty_returns_empty_matrix(self, temp_db):
        result = weekly_heatmap(weeks=4)
        assert result["weeks"] == []
        assert result["matrix"] == []

    def test_counts_by_week_and_severity(self, temp_db):
        conn = _get_conn()
        now = datetime.datetime.now(datetime.timezone.utc)
        # 本周: 2 critical + 1 high
        w1 = now.isoformat()
        # 上周: 1 medium
        w2 = (now - datetime.timedelta(days=7)).isoformat()
        # 2 周前: 1 low (cvss=3.0) + 1 none (cvss=None)
        w3 = (now - datetime.timedelta(days=14)).isoformat()

        _insert_cve(conn, "CVE-A", 9.8, w1)
        _insert_cve(conn, "CVE-B", 9.5, w1)
        _insert_cve(conn, "CVE-C", 8.2, w1)
        _insert_cve(conn, "CVE-D", 5.0, w2)
        _insert_cve(conn, "CVE-E", 3.0, w3)
        _insert_cve(conn, "CVE-F", None, w3)
        conn.commit()

        result = weekly_heatmap(weeks=3)
        assert len(result["weeks"]) == 3
        assert result["severities"] == ["critical", "high", "medium", "low", "none"]

        # 按周查找
        week_map = {w: result["matrix"][i] for i, w in enumerate(result["weeks"])}
        w1_key = w1[:10]
        w2_key = w2[:10]
        w3_key = w3[:10]

        assert week_map[w1_key][0] == 2  # critical
        assert week_map[w1_key][1] == 1  # high
        assert week_map[w2_key][2] == 1  # medium
        assert week_map[w3_key][3] == 1  # low
        assert week_map[w3_key][4] == 1  # none

    def test_respects_weeks_param(self, temp_db):
        conn = _get_conn()
        now = datetime.datetime.now(datetime.timezone.utc)
        for i in range(20):
            created = (now - datetime.timedelta(days=i * 7)).isoformat()
            _insert_cve(conn, f"CVE-W{i}", 7.5, created)
        conn.commit()

        result = weekly_heatmap(weeks=4)
        assert len(result["weeks"]) <= 4
        assert len(result["matrix"]) <= 4

    def test_invalid_date_skipped(self, temp_db):
        conn = _get_conn()
        now = datetime.datetime.now(datetime.timezone.utc)
        _insert_cve(conn, "CVE-OK", 7.0, now.isoformat())
        conn.execute(
            "INSERT INTO security_entities (id, entity_type, name, description, metadata, created_at, updated_at) "
            "VALUES (?, 'cve', ?, ?, ?, ?, ?)",
            ("CVE-BAD", "CVE-BAD", "bad", "{}", "not-a-date", "not-a-date"),
        )
        conn.commit()

        result = weekly_heatmap(weeks=4)
        assert len(result["weeks"]) == 1
        assert sum(result["matrix"][0]) == 1
