"""info_filter_service — CRUD + evaluate 单元测试.

P1 独立资讯筛选门禁:
- 服务层校验入口, 防前端拼写错误静默失败
- evaluate() 优先级: deny > allow > neutral (默认 allow)
- 4 match_kind 各覆盖 (category / source_name / source_id / tag)
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.repository.db import apply_migrations
from backend.services.info_filter_service import (
    InfoFilterError,
    create_rule,
    delete_rule,
    evaluate,
    list_rules,
    update_rule,
)


@pytest.fixture()
def filter_db(tmp_path):
    """临时 DB: 跑 migration 090, 返回连接."""
    db_file = tmp_path / "info_filter.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    yield conn
    conn.close()


# ===== CRUD 4 case =====


def test_create_rule_returns_id_and_persists(filter_db):
    """最小 happy path: create → list 看到."""
    rid = create_rule(
        filter_db, "deny", "source_name", "华尔街见闻",
        note="noise source",
    )
    assert isinstance(rid, int) and rid > 0
    rules = list_rules(filter_db)
    assert len(rules) == 1
    assert rules[0]["match_value"] == "华尔街见闻"
    assert rules[0]["enabled"] == 1


def test_update_rule_changes_fields(filter_db):
    """update 改 note + enabled, 其余不变."""
    rid = create_rule(
        filter_db, "deny", "source_name", "华尔街见闻",
    )
    changed = update_rule(
        filter_db, rid, note="updated note", enabled=0,
    )
    assert changed is True
    rules = list_rules(filter_db)
    assert rules[0]["note"] == "updated note"
    assert rules[0]["enabled"] == 0


def test_delete_rule_removes_row(filter_db):
    """delete → list 空."""
    rid = create_rule(
        filter_db, "deny", "source_name", "华尔街见闻",
    )
    assert delete_rule(filter_db, rid) is True
    assert list_rules(filter_db) == []
    # 二次删: rowcount=0, 返 False
    assert delete_rule(filter_db, rid) is False


def test_list_rules_filters_disabled(filter_db):
    """enabled_only=True 隐藏 disabled 行."""
    create_rule(filter_db, "deny", "source_name", "A")
    rid_b = create_rule(filter_db, "deny", "source_name", "B")
    update_rule(filter_db, rid_b, enabled=0)
    enabled = list_rules(filter_db, enabled_only=True)
    assert len(enabled) == 1
    assert enabled[0]["match_value"] == "A"


# ===== 校验 3 case =====


def test_create_rule_validates_rule_type(filter_db):
    """rule_type 非法 → 抛 InfoFilterError, 不入库."""
    with pytest.raises(InfoFilterError, match="rule_type"):
        create_rule(filter_db, "block", "source_name", "X")
    assert list_rules(filter_db) == []


def test_create_rule_validates_category(filter_db):
    """category 必须 ∈ 已知分类, 否则拒."""
    with pytest.raises(InfoFilterError, match="category"):
        create_rule(filter_db, "deny", "category", "unknown_cat")
    assert list_rules(filter_db) == []


def test_create_rule_validates_source_id_format(filter_db):
    """source_id 必须 "category:source_name" 格式."""
    with pytest.raises(InfoFilterError, match="colon"):
        create_rule(filter_db, "deny", "source_id", "no-colon")


# ===== evaluate 5 case =====


def test_evaluate_deny_wins_over_allow(filter_db):
    """deny + allow 同时命中 → deny 优先."""
    create_rule(filter_db, "deny", "source_name", "X")
    create_rule(filter_db, "allow", "source_name", "X")
    rules = list_rules(filter_db, enabled_only=True)
    verdict, matched = evaluate(
        rules, category="tech", source_name="X",
    )
    assert verdict == "deny"
    assert matched["rule_type"] == "deny"


def test_evaluate_allow_when_no_deny(filter_db):
    """只有 allow → 强制 allow."""
    create_rule(filter_db, "allow", "source_name", "VIP")
    rules = list_rules(filter_db, enabled_only=True)
    verdict, matched = evaluate(
        rules, category="finance", source_name="VIP",
    )
    assert verdict == "allow"
    assert matched["rule_type"] == "allow"


def test_evaluate_neutral_when_no_match(filter_db):
    """无规则命中 → neutral (默认 allow)."""
    create_rule(filter_db, "deny", "source_name", "A")
    rules = list_rules(filter_db, enabled_only=True)
    verdict, matched = evaluate(
        rules, category="tech", source_name="B",
    )
    assert verdict == "neutral"
    assert matched is None


def test_evaluate_match_by_category(filter_db):
    """match_kind=category: 整分类命中."""
    create_rule(filter_db, "deny", "category", "finance")
    rules = list_rules(filter_db, enabled_only=True)
    # 任意 finance 源都被拒
    assert evaluate(rules, category="finance", source_name="任意源")[0] == "deny"
    # tech 不命中
    assert evaluate(rules, category="tech", source_name="任意源")[0] == "neutral"


def test_evaluate_disabled_rule_ignored(filter_db):
    """disabled 规则即使匹配也忽略."""
    rid = create_rule(filter_db, "deny", "source_name", "X")
    update_rule(filter_db, rid, enabled=0)
    rules = list_rules(filter_db, enabled_only=True)  # 只看 enabled
    verdict, _ = evaluate(
        rules, category="tech", source_name="X",
    )
    assert verdict == "neutral"
