"""Phase 13 — PlanningService + Compounding API 单元测试.

覆盖 8 个测试用例:
1.  test_planning_generate_raw_read       — kl:raw 生成 'read' 动作
2.  test_planning_generate_refine_link    — kl:refine + link_count<3 生成 'link' 动作
3.  test_planning_generate_link_refine    — kl:link + score<8.0 生成 'refine' 动作
4.  test_planning_generate_structure_publish — kl:structure + stable>24h 生成 'publish' 动作
5.  test_planning_no_duplicate            — 同 item+action_type+pending 不重复
6.  test_planning_update_status           — update_action_status 状态流转
7.  test_planning_get_actions             — get_actions 过滤与排序
8.  test_compounding_api                  — GET /api/kl/compounding 返回必需字段
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.metrics.kl_metrics import kl_metrics
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.planning_service import PlanningService

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_phase13_planning.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    # 重置 kl_metrics 计数器, 避免跨测试干扰
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    yield test_db
    db_module.close_db()


@pytest.fixture
def client(temp_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 关闭旧 API 以避免路由冲突
    monkeypatch.setattr(config, "feature_reviews", True)
    monkeypatch.setattr(config, "feature_alerts", False)
    monkeypatch.setattr(config, "feature_recommendations", True)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ===========================================================================
# Helpers — 数据准备
# ===========================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=n)).isoformat()


def _insert_knowledge_item(
    conn,
    item_id: str,
    title: str,
    lifecycle: str = "kl:raw",
    concepts: list[str] | None = None,
    mastery: int = 0,
    ingested_ago_hours: int = 48,
    updated_ago_hours: int | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    ingested = (now - timedelta(hours=ingested_ago_hours)).isoformat()
    updated = (
        (now - timedelta(hours=updated_ago_hours)).isoformat()
        if updated_ago_hours is not None
        else ingested
    )
    conn.execute(
        """INSERT OR REPLACE INTO knowledge_items
               (id, title, source, source_url, lifecycle, concepts, mastery,
                ingested_at, updated_at)
           VALUES (?, ?, 'test', ?, ?, ?, ?, ?, ?)""",
        (
            item_id,
            title,
            f"https://example.com/{item_id}",
            lifecycle,
            json.dumps(concepts or []),
            mastery,
            ingested,
            updated,
        ),
    )


def _insert_hotspot(conn, hid: str) -> None:
    """Insert a minimal hotspot row (needed by ai_scores FK)."""
    now = _now_iso()
    conn.execute(
        """INSERT OR REPLACE INTO hotspots
               (id, title, summary, source, url, category, published_at, score, fetched_at)
           VALUES (?, ?, ?, 'test', ?, 'ai', ?, 50, ?)""",
        (hid, hid, f"Summary of {hid}", f"https://example.com/{hid}", now, now),
    )


def _insert_ai_score(conn, hotspot_id: str, score: float) -> None:
    now = _now_iso()
    conn.execute(
        """INSERT OR REPLACE INTO ai_scores
               (hotspot_id, score, reason, scorer, scored_at)
           VALUES (?, ?, ?, ?, ?)""",
        (hotspot_id, score, f"Score {score}", "test", now),
    )


def _insert_knowledge_link(conn, from_id: str, to_id: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO knowledge_links
               (from_item_id, to_item_id, link_type, created_by)
           VALUES (?, ?, 'similar', 'manual')""",
        (from_id, to_id),
    )


def _count_planning_actions(conn, action_type: str | None = None) -> int:
    if action_type:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM planning_actions WHERE action_type = ?",
            (action_type,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM planning_actions").fetchone()
    return row["c"]


def _count_action_log(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM planning_action_log").fetchone()["c"]


# ===========================================================================
# 1. test_planning_generate_raw_read
# ===========================================================================

def test_planning_generate_raw_read(temp_db):
    """kl:raw 且无阅读记录 → 生成 'read' 动作."""
    conn = get_connection()
    _insert_knowledge_item(conn, "item-raw-1", "Raw Article One", lifecycle="kl:raw")
    _insert_knowledge_item(conn, "item-raw-2", "Raw Article Two", lifecycle="kl:raw")
    conn.commit()

    svc = PlanningService()
    counts = svc.generate_actions()

    assert counts["read"] == 2
    assert _count_planning_actions(conn, "read") == 2
    # 验证动作内容
    actions = svc.get_actions(status="pending")
    read_actions = [a for a in actions if a["action_type"] == "read"]
    assert len(read_actions) == 2
    titles = {a["title"] for a in read_actions}
    assert "阅读: Raw Article One" in titles
    assert "阅读: Raw Article Two" in titles
    for a in read_actions:
        assert a["priority"] == 8
        assert a["current_stage"] == "kl:raw"
        assert a["target_stage"] == "kl:refine"
        assert a["status"] == "pending"


# ===========================================================================
# 2. test_planning_generate_refine_link
# ===========================================================================

def test_planning_generate_refine_link(temp_db):
    """kl:refine 且关联数 < 3 → 生成 'link' 动作."""
    conn = get_connection()
    # item-1: 关联数 = 0 (< 3) → 应生成 link 动作
    _insert_knowledge_item(conn, "item-ref-link-1", "Refine Low Link", lifecycle="kl:refine")
    # item-2: 关联数 = 2 (< 3) → 仍应生成 link 动作
    _insert_knowledge_item(conn, "item-ref-link-2", "Refine Mid Link", lifecycle="kl:refine")
    _insert_knowledge_link(conn, "item-ref-link-2", "other-item-a")
    _insert_knowledge_link(conn, "item-ref-link-2", "other-item-b")
    # item-3: 关联数 = 3 (≥ 3) → 不应生成 link 动作
    _insert_knowledge_item(conn, "item-ref-link-3", "Refine Enough Link", lifecycle="kl:refine")
    _insert_knowledge_link(conn, "item-ref-link-3", "other-item-c")
    _insert_knowledge_link(conn, "item-ref-link-3", "other-item-d")
    _insert_knowledge_link(conn, "item-ref-link-3", "other-item-e")
    conn.commit()

    svc = PlanningService()
    counts = svc.generate_actions()

    assert counts["link"] == 2  # 只有前两个满足条件
    assert _count_planning_actions(conn, "link") == 2
    actions = svc.get_actions(status="pending")
    link_items = {a["item_id"] for a in actions if a["action_type"] == "link"}
    assert "item-ref-link-1" in link_items
    assert "item-ref-link-2" in link_items
    assert "item-ref-link-3" not in link_items  # 关联数 ≥ 3, 跳过


# ===========================================================================
# 3. test_planning_generate_link_refine
# ===========================================================================

def test_planning_generate_link_refine(temp_db):
    """kl:link 且评分 < 8.0 → 生成 'refine' 动作."""
    conn = get_connection()
    # item-1: 评分 5.0 (< 8.0) → 应生成 refine
    _insert_hotspot(conn, "item-link-ref-1")
    _insert_knowledge_item(conn, "item-link-ref-1", "Link Low Score", lifecycle="kl:link")
    _insert_ai_score(conn, "item-link-ref-1", 5.0)
    # item-2: 评分 9.0 (≥ 8.0) → 不应生成 refine
    _insert_hotspot(conn, "item-link-ref-2")
    _insert_knowledge_item(conn, "item-link-ref-2", "Link High Score", lifecycle="kl:link")
    _insert_ai_score(conn, "item-link-ref-2", 9.0)
    # item-3: 无评分记录 (COALESCE → 0) → 应生成 refine
    _insert_knowledge_item(conn, "item-link-ref-3", "Link No Score", lifecycle="kl:link")
    conn.commit()

    svc = PlanningService()
    counts = svc.generate_actions()

    assert counts["refine"] == 2  # item-1 和 item-3
    assert _count_planning_actions(conn, "refine") == 2
    actions = svc.get_actions(status="pending")
    refine_items = {a["item_id"] for a in actions if a["action_type"] == "refine"}
    assert "item-link-ref-1" in refine_items
    assert "item-link-ref-2" not in refine_items
    assert "item-link-ref-3" in refine_items


# ===========================================================================
# 4. test_planning_generate_structure_publish
# ===========================================================================

def test_planning_generate_structure_publish(temp_db):
    """kl:structure 且已稳定 24h+ → 生成 'publish' 动作."""
    conn = get_connection()
    # item-1: 更新于 48 小时前 (> 24h) → 应生成 publish
    _insert_knowledge_item(
        conn, "item-pub-1", "Structure Old", lifecycle="kl:structure",
        updated_ago_hours=48,
    )
    # item-2: 更新于 1 小时前 (< 24h) → 不应生成 publish
    _insert_knowledge_item(
        conn, "item-pub-2", "Structure Recent", lifecycle="kl:structure",
        updated_ago_hours=1,
    )
    conn.commit()

    svc = PlanningService()
    counts = svc.generate_actions()

    assert counts["publish"] == 1
    assert _count_planning_actions(conn, "publish") == 1
    actions = svc.get_actions(status="pending")
    publish_items = {a["item_id"] for a in actions if a["action_type"] == "publish"}
    assert "item-pub-1" in publish_items
    assert "item-pub-2" not in publish_items
    # 验证动作属性
    pub_action = next(a for a in actions if a["action_type"] == "publish")
    assert pub_action["priority"] == 5
    assert pub_action["current_stage"] == "kl:structure"
    assert pub_action["target_stage"] == "kl:publish"


# ===========================================================================
# 5. test_planning_no_duplicate
# ===========================================================================

def test_planning_no_duplicate(temp_db):
    """同 item_id + action_type + pending 不重复生成."""
    conn = get_connection()
    _insert_knowledge_item(conn, "item-dup", "Dup Article", lifecycle="kl:raw")
    conn.commit()

    svc = PlanningService()

    # 第一次调用 → 生成 1 条
    counts1 = svc.generate_actions()
    assert counts1["read"] == 1
    assert _count_planning_actions(conn) == 1
    assert _count_action_log(conn) == 1  # 1 条 created 日志

    # 第二次调用 → 不应重复 (counts 反映匹配行数, 不受去重影响;
    # 实际 DB 状态应保持不变)
    counts2 = svc.generate_actions()
    assert _count_planning_actions(conn) == 1  # 仍为 1 条
    assert _count_action_log(conn) == 1  # 无新增日志

    # 将动作标记为 completed 后, 再次调用应生成新的 pending 动作
    action = svc.get_actions(status="pending")[0]
    svc.update_action_status(action["id"], "in_progress")
    svc.update_action_status(action["id"], "completed")

    counts3 = svc.generate_actions()
    assert _count_planning_actions(conn) == 2  # 新生成一条
    assert _count_action_log(conn) == 4  # 新增: created + started + completed + created


# ===========================================================================
# 6. test_planning_update_status
# ===========================================================================

def test_planning_update_status(temp_db):
    """update_action_status 合法流转与拒绝非法流转."""
    conn = get_connection()
    _insert_knowledge_item(conn, "item-status", "Status Test", lifecycle="kl:raw")
    conn.commit()

    svc = PlanningService()
    svc.generate_actions()
    action = svc.get_actions(status="pending")[0]
    action_id = action["id"]

    # pending → in_progress → OK
    assert svc.update_action_status(action_id, "in_progress") is True
    row = conn.execute("SELECT status FROM planning_actions WHERE id = ?", (action_id,)).fetchone()
    assert row["status"] == "in_progress"

    # in_progress → completed → OK
    assert svc.update_action_status(action_id, "completed") is True
    row = conn.execute(
        "SELECT status, completed_at FROM planning_actions WHERE id = ?",
        (action_id,),
    ).fetchone()
    assert row["status"] == "completed"
    assert row["completed_at"] is not None

    # 对不存在的 action_id → False
    assert svc.update_action_status(99999, "in_progress") is False

    # 非法流转: completed → in_progress → False
    assert svc.update_action_status(action_id, "in_progress") is False

    # 查看日志: 应有 3 条事件 (created, started, completed)
    log_count = conn.execute(
        "SELECT COUNT(*) AS c FROM planning_action_log WHERE action_id = ?",
        (action_id,),
    ).fetchone()["c"]
    assert log_count == 3

    # 测试 dismissed 路径
    _insert_knowledge_item(conn, "item-status-2", "Status Test 2", lifecycle="kl:raw")
    conn.commit()
    svc.generate_actions()
    action2 = svc.get_actions(status="pending")[0]
    aid2 = action2["id"]

    assert svc.update_action_status(aid2, "in_progress") is True
    assert svc.update_action_status(aid2, "dismissed") is True
    row = conn.execute(
        "SELECT status, dismissed_at FROM planning_actions WHERE id = ?",
        (aid2,),
    ).fetchone()
    assert row["status"] == "dismissed"
    assert row["dismissed_at"] is not None


# ===========================================================================
# 7. test_planning_get_actions
# ===========================================================================

def test_planning_get_actions(temp_db):
    """get_actions 正确过滤与排序."""
    conn = get_connection()
    _insert_knowledge_item(conn, "item-get-1", "Get Test 1", lifecycle="kl:raw")
    _insert_knowledge_item(conn, "item-get-2", "Get Test 2", lifecycle="kl:raw")
    _insert_knowledge_item(conn, "item-get-3", "Get Test 3", lifecycle="kl:raw")
    conn.commit()

    svc = PlanningService()
    svc.generate_actions()  # 生成 3 条 pending read

    # 全部返回
    all_actions = svc.get_actions()
    assert len(all_actions) == 3
    for a in all_actions:
        assert "id" in a
        assert "item_id" in a
        assert "action_type" in a
        assert "priority" in a
        assert "title" in a
        assert "status" in a
        assert "created_at" in a

    # 按 status 过滤
    pending = svc.get_actions(status="pending")
    assert len(pending) == 3

    completed = svc.get_actions(status="completed")
    assert len(completed) == 0

    # 标记一个为 completed 后重新检查
    svc.update_action_status(all_actions[0]["id"], "in_progress")
    svc.update_action_status(all_actions[0]["id"], "completed")
    completed = svc.get_actions(status="completed")
    assert len(completed) == 1

    # 排序: priority 降序, created_at 升序
    all_actions = svc.get_actions()
    for i in range(len(all_actions) - 1):
        assert all_actions[i]["priority"] >= all_actions[i + 1]["priority"]

    # limit 参数
    limited = svc.get_actions(limit=2)
    assert len(limited) == 2


# ===========================================================================
# 8. test_compounding_api
# ===========================================================================

def test_compounding_api(client, temp_db):
    """GET /api/kl/compounding 返回所有必需字段."""
    conn = get_connection()

    # 准备测试数据
    now = datetime.now(timezone.utc)
    # 插入 3 条 knowledge_items, 分布在不同的生命周期阶段
    items_data = [
        ("c-item-1", "Comp Item 1", "kl:raw", ["concept-a", "concept-b"], 3, 24),
        ("c-item-2", "Comp Item 2", "kl:refine", ["concept-b"], 5, 48),
        ("c-item-3", "Comp Item 3", "kl:link", [], 7, 72),
    ]
    for item_id, title, lifecycle, concepts, mastery, hours_ago in items_data:
        ingested = (now - timedelta(hours=hours_ago)).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO knowledge_items
                   (id, title, source, source_url, lifecycle, concepts, mastery,
                    ingested_at, updated_at)
               VALUES (?, ?, 'test', ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                title,
                f"https://example.com/{item_id}",
                lifecycle,
                json.dumps(concepts),
                mastery,
                ingested,
                ingested,
            ),
        )

    # 插入 knowledge_links (用于 top_concepts)
    _insert_knowledge_link(conn, "c-item-1", "c-item-2")
    conn.commit()

    # 调用 API
    resp = client.get("/api/kl/compounding")
    assert resp.status_code == 200
    data = resp.json()

    # 验证必需字段存在
    assert "daily_trend" in data
    assert "weekly_trend" in data
    assert "monthly_trend" in data
    assert "top_concepts" in data
    assert "trigger_health" in data
    assert "stage_distribution" in data

    # daily_trend 是列表, 每项有 day/count/avg_score
    assert isinstance(data["daily_trend"], list)
    if data["daily_trend"]:
        entry = data["daily_trend"][0]
        assert "day" in entry
        assert "count" in entry
        assert "avg_score" in entry

    # weekly_trend / monthly_trend 同理
    assert isinstance(data["weekly_trend"], list)
    if data["weekly_trend"]:
        w = data["weekly_trend"][0]
        assert "week" in w
        assert "count" in w
        assert "avg_score" in w

    assert isinstance(data["monthly_trend"], list)
    if data["monthly_trend"]:
        m = data["monthly_trend"][0]
        assert "month" in m
        assert "count" in m
        assert "avg_score" in m

    # top_concepts: 列表, 每项有 name/score
    assert isinstance(data["top_concepts"], list)
    for tc in data["top_concepts"]:
        assert "name" in tc
        assert "score" in tc
    # concept-b 出现 2 次 (c-item-1 + c-item-2), concept-a 出现 1 次
    concept_names = {tc["name"] for tc in data["top_concepts"]}
    assert "concept-b" in concept_names
    assert "concept-a" in concept_names

    # trigger_health: 包含 t1_failed/t2_failed/t3_failed/t4_failed/dead_letter_count
    th = data["trigger_health"]
    assert "t1_failed" in th
    assert "t2_failed" in th
    assert "t3_failed" in th
    assert "t4_failed" in th
    assert "dead_letter_count" in th
    # 默认值均为 0
    assert th["t1_failed"] == 0
    assert th["t2_failed"] == 0
    assert th["t3_failed"] == 0
    assert th["t4_failed"] == 0
    assert th["dead_letter_count"] == 0

    # stage_distribution: dict, key 是 lifecycle, value 是计数
    assert isinstance(data["stage_distribution"], dict)
    assert data["stage_distribution"].get("kl:raw", 0) >= 1
    assert data["stage_distribution"].get("kl:refine", 0) >= 1
    assert data["stage_distribution"].get("kl:link", 0) >= 1