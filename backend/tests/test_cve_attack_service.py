"""S4-3 CVE → ATT&CK attack service tests.

覆盖:
1. test_cves_to_attack_techniques_empty_input — 空列表返回空
2. test_cves_to_attack_techniques_no_cwe — CVE 无 cwe_ids → matched=0
3. test_cves_to_attack_techniques_maps_cwes — 正常映射 + 聚合计数
4. test_cves_to_attack_techniques_multiple_cves — 多 CVE 聚合
5. test_cves_to_attack_techniques_unknown_cve_skipped — 不存在的 CVE 被跳过
"""
from __future__ import annotations

import json
import sqlite3

from backend.repository.db import get_connection
from backend.services.attack_loader import load_attack_data
from backend.services.cve_attack_service import cves_to_attack_techniques


def _get_conn() -> sqlite3.Connection:
    return get_connection()


def _insert_cve(conn: sqlite3.Connection, cve_id: str, cwe_ids: list[str]) -> None:
    conn.execute(
        """INSERT INTO security_entities
               (id, entity_type, name, description, metadata, created_at, updated_at)
           VALUES (?, 'cve', ?, ?, ?, ?, ?)""",
        (
            cve_id,
            cve_id,
            f"Description for {cve_id}",
            json.dumps({"cwe_ids": cwe_ids}),
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )


class TestCvesToAttackTechniques:
    def test_empty_input(self, temp_db):
        result = cves_to_attack_techniques([])
        assert result["techniques"] == []
        assert result["total_cves"] == 0
        assert result["matched_cves"] == 0

    def test_no_cwe_ids(self, temp_db):
        load_attack_data()
        conn = _get_conn()
        _insert_cve(conn, "CVE-NO-CWE", [])
        conn.commit()

        result = cves_to_attack_techniques(["CVE-NO-CWE"])
        assert result["techniques"] == []
        assert result["matched_cves"] == 0
        assert result["total_cves"] == 1

    def test_maps_cwes_and_counts(self, temp_db):
        load_attack_data()
        conn = _get_conn()
        # CWE-89 (SQL Injection) 通常映射到 T1190 (Exploit Public-Facing Application)
        _insert_cve(conn, "CVE-1", ["CWE-89"])
        conn.commit()

        result = cves_to_attack_techniques(["CVE-1"])
        assert result["total_cves"] == 1
        assert result["matched_cves"] == 1
        assert len(result["techniques"]) >= 1
        # 所有 technique_id 以 T 开头
        for t in result["techniques"]:
            assert t["technique_id"].startswith("T")
            assert t["count"] >= 1
            assert "name" in t
            assert "tactic" in t

    def test_multiple_cves_aggregate(self, temp_db):
        load_attack_data()
        conn = _get_conn()
        _insert_cve(conn, "CVE-1", ["CWE-89", "CWE-79"])
        _insert_cve(conn, "CVE-2", ["CWE-89"])
        conn.commit()

        result = cves_to_attack_techniques(["CVE-1", "CVE-2"])
        assert result["total_cves"] == 2
        assert result["matched_cves"] == 2
        assert len(result["techniques"]) >= 1
        # 聚合后各 technique 的 count 总和应 >= 2 (至少一个 CWE 命中)
        total_counts = sum(t["count"] for t in result["techniques"])
        assert total_counts >= 2

    def test_unknown_cve_skipped(self, temp_db):
        load_attack_data()
        result = cves_to_attack_techniques(["CVE-DOES-NOT-EXIST"])
        assert result["techniques"] == []
        assert result["matched_cves"] == 0
        assert result["total_cves"] == 1
