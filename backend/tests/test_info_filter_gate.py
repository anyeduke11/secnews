"""info_filter_gate — 三层 hook 单元测试.

覆盖:
- Layer 1 filter_source: collect 入口源级 allow/deny
- Layer 2 filter_items: item 落库前过滤 (HotspotItem + raw dict 兼容)
- cache 行为: 5s TTL + invalidate_cache 立即失效
- feature gate: 关闭时全部 pass-through (零开销)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from backend.repository.db import apply_migrations
from backend.services.info_filter_gate import (
    filter_items,
    filter_source,
    invalidate_cache,
)
from backend.services.info_filter_service import create_rule


@pytest.fixture()
def gate_db(tmp_path, monkeypatch):
    """临时 DB: 跑 migration 090 + monkeypatch get_connection."""
    db_file = tmp_path / "info_filter_gate.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)

    # 把 backend.repository.db.get_connection 替换成返回这个临时 conn.
    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", lambda: conn)
            except (AttributeError, TypeError):
                pass
    yield conn
    conn.close()


# ===== feature gate 行为 =====


def test_filter_source_pass_through_when_gate_off(gate_db, monkeypatch):
    """feature gate off → filter_source 直接放行, 不查 DB."""
    # 不写任何规则
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: False
    )
    allowed, reason = filter_source({"name": "X", "category": "tech"})
    assert allowed is True
    assert reason is None


def test_filter_source_deny_when_rule_matches(gate_db, monkeypatch):
    """deny 规则命中 → filter_source 拒绝 + reason 含 rule_id."""
    create_rule(gate_db, "deny", "source_name", "华尔街见闻", note="noise")
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: True
    )
    invalidate_cache()  # 立即生效
    allowed, reason = filter_source(
        {"name": "华尔街见闻", "category": "finance"}
    )
    assert allowed is False
    assert reason is not None
    assert "info_filter_deny" in reason
    assert "华尔街见闻" in reason


def test_filter_source_allow_when_no_match(gate_db, monkeypatch):
    """规则存在但未命中 → 放行."""
    create_rule(gate_db, "deny", "source_name", "A")
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: True
    )
    invalidate_cache()
    allowed, reason = filter_source({"name": "B", "category": "tech"})
    assert allowed is True
    assert reason is None


# ===== Layer 2 item 过滤 =====


def test_filter_items_drops_deny_source(gate_db, monkeypatch):
    """filter_items: 命中 deny 规则的源对应 item 丢弃."""
    create_rule(gate_db, "deny", "source_name", "noise_src")
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: True
    )
    invalidate_cache()
    items = [
        {"title": "a", "source": "noise_src", "category": "tech"},
        {"title": "b", "source": "good_src", "category": "tech"},
        {"title": "c", "source": "noise_src", "category": "tech"},
    ]
    kept = filter_items(items)
    assert len(kept) == 1
    assert kept[0]["title"] == "b"


def test_filter_items_handles_hotspot_item(gate_db, monkeypatch):
    """filter_items 兼容 HotspotItem 对象 (用 .source 字段)."""
    from backend.domain.models import HotspotItem
    from backend.domain.enums import Category

    create_rule(gate_db, "deny", "source_name", "denied")
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: True
    )
    invalidate_cache()

    now = datetime.now(timezone.utc)
    item_denied = HotspotItem(
        id="d1", title="denied news", url="https://x.com/1",
        source="denied", category=Category.TECH,
        published_at=now, fetched_at=now,
    )
    item_ok = HotspotItem(
        id="d2", title="ok news", url="https://y.com/2",
        source="ok_src", category=Category.TECH,
        published_at=now, fetched_at=now,
    )
    kept = filter_items([item_denied, item_ok])
    assert len(kept) == 1
    assert kept[0].id == "d2"


# ===== cache 行为 =====


def test_invalidate_cache_forces_reload(gate_db, monkeypatch):
    """invalidate_cache 后下一次 evaluate 立即读新规则."""
    monkeypatch.setattr(
        "backend.services.info_filter_gate._is_enabled", lambda: True
    )
    invalidate_cache()
    # 第一轮: 无规则 → 放行
    allowed, _ = filter_source({"name": "X", "category": "tech"})
    assert allowed is True
    # 加规则 + invalidate
    create_rule(gate_db, "deny", "source_name", "X")
    invalidate_cache()
    # 第二轮: 应被拒
    allowed, reason = filter_source({"name": "X", "category": "tech"})
    assert allowed is False
    assert "info_filter_deny" in reason
