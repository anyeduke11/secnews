"""S4-3 ATT&CK data loader tests.

覆盖:
1. test_load_attack_data_first_time — 空表 → 灌入 techniques + cwe_mappings
2. test_load_attack_data_idempotent — 已有数据 → 跳过不重复
3. test_cwe_to_techniques_single — 单条 CWE 查询
4. test_cwe_to_techniques_multiple — 多条 CWE 聚合
5. test_cwe_to_techniques_missing — 缺失 CWE 返回空
"""
from __future__ import annotations

import sqlite3

from backend.repository.db import get_connection
from backend.services.attack_loader import cwe_to_techniques, load_attack_data

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    return get_connection()


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadAttackData:
    def test_first_time_loads_data(self, temp_db):
        """空表首次调用 → 灌入 attack_techniques + attack_cwe_map。"""
        conn = _get_conn()
        tech_count = _count_rows(conn, "attack_techniques")
        cwe_count = _count_rows(conn, "attack_cwe_map")
        assert tech_count == 0
        assert cwe_count == 0

        result = load_attack_data()

        assert result["techniques"] > 0
        assert result["cwe_mappings"] > 0
        assert _count_rows(conn, "attack_techniques") == result["techniques"]
        assert _count_rows(conn, "attack_cwe_map") == result["cwe_mappings"]

    def test_idempotent_skips_existing(self, temp_db):
        """已有数据时再次调用 → 跳过, 计数归零。"""
        load_attack_data()  # 首次灌入
        conn = _get_conn()
        first_tech = _count_rows(conn, "attack_techniques")
        first_cwe = _count_rows(conn, "attack_cwe_map")

        result = load_attack_data()  # 二次调用

        assert result["techniques"] == 0
        assert result["cwe_mappings"] == 0
        assert _count_rows(conn, "attack_techniques") == first_tech
        assert _count_rows(conn, "attack_cwe_map") == first_cwe


class TestCweToTechniques:
    def test_single_cwe(self, temp_db):
        """单条 CWE 查询 → 返回对应 technique 计数。"""
        load_attack_data()
        # CWE-79 (XSS) → T1059 (Command and Scripting Interpreter) 等
        result = cwe_to_techniques(["CWE-79"])
        assert isinstance(result, dict)
        # 至少命中一个 technique (具体映射数取决于 cwe-to-technique.json)
        assert len(result) >= 1
        # 所有 key 都是 technique_id 格式
        for k in result:
            assert k.startswith("T")

    def test_multiple_cwes_aggregates(self, temp_db):
        """多条 CWE → 聚合计数。"""
        load_attack_data()
        result = cwe_to_techniques(["CWE-79", "CWE-89", "CWE-787"])
        assert isinstance(result, dict)
        # 多个 CWE 可能映射到同一 technique, count 会聚合
        for k, v in result.items():
            assert k.startswith("T")
            assert v >= 1

    def test_missing_cwe_returns_empty(self, temp_db):
        """不存在的 CWE → 空 dict。"""
        load_attack_data()
        result = cwe_to_techniques(["CWE-99999"])
        assert result == {}

    def test_empty_list_returns_empty(self, temp_db):
        """空列表 → 空 dict (短路)。"""
        load_attack_data()
        assert cwe_to_techniques([]) == {}
