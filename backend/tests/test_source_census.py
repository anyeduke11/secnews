"""源清单普查 (source_census) 与 /health 分母口径回归测试.

为什么需要这个文件 (第一性原理: 分母必须是"当前真实存在的源")
----------------------------------------------------------
"有多少个源、多少个死了" 同时有三套互不相容的答案:

- ``/api/sources/health``       枚举 ``source_stats`` **历史行** → 152
  (实测含 22 个已无任何 collector 抓取的孤儿行 + 2 个跨 category 重名)
- ``/api/sources/health/v2``    枚举 ``crawler_sources`` 调度表 → 130 (含 14 disabled)
- ``/api/sources/health/trend`` 枚举 ``hotspots.source`` 去重名 → 只覆盖有产出记录的源

采集器实际抓取的权威清单是 ``crawler_sources WHERE enabled=1``
(见 ``collectors/base.py:_load_sources_from_registry``), 实测 = **116**。
前端心跳条却拿 152 当分母, 于是"源在线 32/152"两个数都不代表真实情况。

本测试锁三件事:
  C1 普查以注册表为准, 并把孤儿行数算对
  C2 /health 同时给出旧字段 (不打断现有消费者) 与新 registered_* 字段 (正确分母)
  C3 三个端点各自声明自己的 metric 口径, 数字可比较而不是互相打脸
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test_census.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _seed(conn) -> None:
    """注册表 4 个启用 (含 1 个尚无统计行的新源) + 1 个停用; source_stats 多 2 个孤儿行。"""
    for name, cat, enabled in (
        ("活源A", "security", 1), ("活源B", "security", 1), ("活源C", "bid", 1),
        ("新接入源E", "tech", 1),      # 启用但还没有任何 source_stats 行
        ("停用源D", "security", 0),
    ):
        conn.execute(
            "INSERT INTO crawler_sources (category, name, url, enabled, priority)"
            " VALUES (?, ?, ?, ?, 50)",
            (cat, name, f"https://{name}.example.com", enabled),
        )
    for name, cat, status, items in (
        ("活源A", "security", "active", 100),
        ("活源B", "security", "dead", 0),
        ("活源C", "bid", "stale", 5),
        # 孤儿: 已不在注册表, 但历史行还留着, 且其中一个是 active —— 旧口径会把它算进健康分子
        ("孤儿老源", "security", "active", 9999),
        ("孤儿死源", "tech", "dead", 0),
    ):
        conn.execute(
            "INSERT INTO source_stats (category, source_name, source_url, status,"
            " total_runs, zero_yield_runs, total_items, last_checked_at, updated_at)"
            " VALUES (?, ?, ?, ?, 10, 0, ?, datetime('now'), datetime('now'))",
            (cat, name, f"https://{name}.example.com", status, items),
        )
    conn.commit()


# ── C1 普查以注册表为准 ─────────────────────────────────────
def test_census_uses_registry_as_denominator(temp_db):
    from backend.services.source_census_service import build_census

    _seed(db.get_connection())
    c = build_census()

    assert c["registry_total"] == 5
    assert c["registered_enabled"] == 4
    assert c["registered_disabled"] == 1
    assert c["stats_rows"] == 5
    # 2 个 source_stats 行已不在注册表 → 孤儿, 不该进分母
    assert c["orphan_rows"] == 2
    # 分母只数"注册且启用"且已有统计行的源
    assert c["counted_total"] == 3
    assert c["counted_active"] == 1
    assert c["counted_stale"] == 1
    assert c["counted_dead"] == 1
    # 启用但还没有任何统计行 = 新接入源, 只有 census 看得见
    assert c["untracked_count"] == 1
    # 三套状态词汇的等价表必须随响应下发, 否则前端无法比较不同端点的数字
    assert c["status_equivalence"]["failing"]["phase9_liveness"] == "dead"
    assert c["status_equivalence"]["failing"]["phase4_trend"] == "red"


def test_census_accepts_preloaded_registry(temp_db):
    """传入已读好的注册表快照时结果一致 (同一请求不重复查库)。"""
    from backend.services.source_census_service import build_census, registry_snapshot

    _seed(db.get_connection())
    assert build_census(registry_snapshot()) == build_census()


# ── C2 /health 新旧字段并存 ────────────────────────────────
def test_health_payload_exposes_both_scopes(temp_db):
    from backend.api.sources import _build_health_payload

    _seed(db.get_connection())
    payload = _build_health_payload(None)

    # 旧字段保留 (不打断现有消费者): 按 source_stats 全历史行数
    assert payload["active_count"] == 2      # 含 1 个孤儿 active
    assert payload["dead_count"] == 2
    assert len(payload["sources"]) == 5
    # 新字段才是真实分母: 只算注册且启用
    assert payload["registered_total"] == 3
    assert payload["registered_active"] == 1
    assert payload["registered_dead"] == 1
    assert payload["census"]["orphan_rows"] == 2

    by_name = {s["source_name"]: s for s in payload["sources"]}
    assert by_name["活源A"]["registered"] is True
    assert by_name["孤儿老源"]["registered"] is False
    # 口径边界 (如实断言而非掩盖): /health 逐行枚举 source_stats, 所以
    # "在注册表但还没有统计行"的源不会出现在 sources 里 ——
    # 启用态的 (新接入源E) 由 census.untracked_count 兜住; 停用态的 (停用源D)
    # 两处都不可见, 因为它本就不该被采集。
    assert "停用源D" not in by_name
    assert payload["census"]["untracked_count"] == 1   # 只有启用且无统计行的源E
