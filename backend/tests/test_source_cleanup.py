"""fix_source_stats_cleanup 脚本核心逻辑测试 (数据源治理 T2).

锁定的契约 (与 scripts/fix_source_stats_cleanup.py docstring 同源):
1. dry-run (默认, 无 --execute): 只报告变更面, 零写入零审计
2. --execute: 仅清 status='dead' AND total_items=0 的空壳行 (从未产出),
   逐行先写 source_cleanup_log(never_yielded_dead_cleanup) 再 DELETE
3. 幂等: 第二次 execute 零变更、审计不重复积累、退出码 0
4. 不匹配的行原样保留: 有产出 dead (复活探测覆盖) / stale / active

执行:
    python -m pytest backend/tests/test_source_cleanup.py -v
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fix_source_stats_cleanup.py"


def _load_script():
    """以独立模块名加载脚本 (scripts/ 不在包路径, standalone 约定)。"""
    spec = importlib.util.spec_from_file_location(
        "fix_source_stats_cleanup", SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path (全量 migration, 与 test_fix_source_registry_cleanup 同模式)。"""
    test_db = tmp_path / "test_stats_cleanup.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_stat(
    name: str,
    *,
    status: str = "dead",
    total_items: int = 0,
    category: str = "security",
    source_url: str | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO source_stats
            (category, source_name, source_url, status, total_items, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (category, name, source_url or f"https://example.com/{name}", status, total_items),
    )


def _seed_all() -> None:
    """变更面: 空壳 dead+0 ×2 (含 1 个跨类目同名场景) + 保留行 ×3。"""
    _insert_stat("空壳源A")
    _insert_stat("空壳源B", category="ai")
    _insert_stat("有产出死源", total_items=1377)  # 12 个有产出 dead 的代表
    _insert_stat("滞后源", status="stale")
    _insert_stat("活跃源", status="active", total_items=42)


def _counts() -> dict:
    conn = get_connection()
    return {
        "shell_rows": conn.execute(
            "SELECT COUNT(*) FROM source_stats WHERE status='dead' AND total_items=0"
        ).fetchone()[0],
        "total_stats": conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0],
        "audit_rows": conn.execute(
            "SELECT COUNT(*) FROM source_cleanup_log "
            "WHERE reason='never_yielded_dead_cleanup'"
        ).fetchone()[0],
    }


class TestDryRun:
    def test_default_dry_run_reports_but_never_writes(self, temp_db):
        mod = _load_script()
        _seed_all()
        before = _counts()

        rc = mod.main([])  # 无 --execute → dry-run

        assert rc == 0
        assert _counts() == before, "dry-run 不得改变任何行 (含审计表)"


class TestExecute:
    def test_execute_deletes_shells_with_audit(self, temp_db):
        mod = _load_script()
        _seed_all()

        rc = mod.main(["--execute"])

        assert rc == 0
        c = _counts()
        assert c["shell_rows"] == 0, "空壳行必须清零"
        assert c["total_stats"] == 3, "只删 2 个空壳, 保留行不动"
        assert c["audit_rows"] == 2, "逐行审计, 不批量一条"

        conn = get_connection()
        # 保留行原样: 有产出 dead / stale / active
        kept = {
            r["source_name"]: (r["status"], r["total_items"])
            for r in conn.execute("SELECT source_name, status, total_items FROM source_stats")
        }
        assert kept["有产出死源"] == ("dead", 1377)
        assert kept["滞后源"] == ("stale", 0)
        assert kept["活跃源"] == ("active", 42)

        # 审计内容契约: layer/ident/reason/executed_by
        logs = conn.execute(
            "SELECT source_layer, source_ident, reason, executed_by "
            "FROM source_cleanup_log ORDER BY source_ident"
        ).fetchall()
        idents = {r["source_ident"] for r in logs}
        assert idents == {"空壳源A", "空壳源B"}
        for r in logs:
            assert r["source_layer"] == "source_stats"
            assert r["reason"] == "never_yielded_dead_cleanup"
            assert r["executed_by"] == "fix_source_stats_cleanup"

    def test_ident_falls_back_to_url_when_name_empty(self, temp_db):
        mod = _load_script()
        conn = get_connection()
        conn.execute(
            "INSERT INTO source_stats (category, source_name, source_url, status, total_items, updated_at) "
            "VALUES ('security', '', 'https://example.com/noname', 'dead', 0, datetime('now'))"
        )

        rc = mod.main(["--execute"])

        assert rc == 0
        log = conn.execute("SELECT source_ident FROM source_cleanup_log").fetchone()
        assert log["source_ident"] == "https://example.com/noname"


class TestIdempotency:
    def test_second_execute_is_zero_change(self, temp_db):
        mod = _load_script()
        _seed_all()
        mod.main(["--execute"])
        after_first = _counts()

        rc = mod.main(["--execute"])

        assert rc == 0
        assert _counts() == after_first, "重复执行必须零变更"
        assert after_first["audit_rows"] == 2, "审计不重复积累"

    def test_clean_db_is_noop(self, temp_db):
        mod = _load_script()
        rc = mod.main(["--execute"])
        assert rc == 0
        assert _counts() == {"shell_rows": 0, "total_stats": 0, "audit_rows": 0}
