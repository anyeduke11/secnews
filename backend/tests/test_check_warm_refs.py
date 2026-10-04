"""check_warm_refs.py 门禁自身测试 (v0.8.6 P1-8)。

WHY (Rule 9): 门禁的失效模式有两种 — ① 白名单漂移 (把运行时消费方加进
豁免表, 门禁永不红 = 失明) ② 规则漏匹配 (跨行 f-string 拼接的 SQL 体内
裸 warm. 漏抓)。本测试锁: 扫描器的抓/放语义 + 白名单表内容审计。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import check_warm_refs as cwr


def test_scan_returns_zero_violations_on_current_repo():
    """基线: 仓内 warm.X 裸引用 = 0 (存量已随本批清零)。

    若此测试红, 说明有人新增了运行时裸引用 — 修法是改走 accessor,
    不是放宽白名单。
    """
    assert cwr.scan() == []


def test_scanner_catches_bare_warm_sql(tmp_path: Path):
    """抓违规: FROM warm.x 形态必须命中 (门禁不失明)。"""
    f = tmp_path / "bad.py"
    f.write_text(
        'def f(conn):\n'
        '    return conn.execute("SELECT 1 FROM warm.hotspots").fetchone()\n',
        encoding="utf-8",
    )
    # 直接对 tmp 文件跑正则 (scan() 只扫 repo 根, 这里验证规则本身)
    m = cwr.SQL_REF_RE.search(f.read_text(encoding="utf-8"))
    assert m is not None and m.group(0).lower().startswith("from warm")


def test_scanner_catches_join_update_into_forms(tmp_path: Path):
    for sql in (
        "LEFT JOIN warm.knowledge_items ON 1",
        "INSERT INTO warm.t SELECT 1",
        "UPDATE warm.t SET x=1",
    ):
        assert cwr.SQL_REF_RE.search(sql), sql


def test_whitelist_semantics_frozen():
    """白名单审计: 治理文件 = accessor 本体; 一次性脚本直连 warm.db 文件。

    若需新增豁免, 必须满足: 该文件 sqlite3.connect(warm.db) 直连 (非运行时
    ATTACH 路径)。运行时消费方加豁免 = 门禁失明, 禁止。
    """
    assert {"backend/repository/db.py"} == cwr.WARM_SCHEMA_GOVERNORS
    assert {
        "scripts/audit_dead_source_triage.py",
        "scripts/migrate_temp_layers.py",
    } == cwr._ONEOFF_MAINTENANCE_SCRIPTS


def test_governor_file_is_actual_accessor_owner():
    """防白名单漂移: db.py 必须真实包含 accessor 定义 (文件移动即红)。"""
    gov = cwr.REPO_ROOT / "backend/repository/db.py"
    text = gov.read_text(encoding="utf-8")
    assert "def warm_table(" in text
    assert "def knowledge_items_table(" in text
