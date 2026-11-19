"""v1.7 Phase 2 — 端到端验收测试 (3 项验收标准).

验收标准 (来自 docs/v1.7_development_plan.md Task 2.6):
  1. 新学概念创建后 24h 出现在复习队列
  2. 评分后间隔按 SM-2 延长
  3. 笔记 CRUD 正常

原验收 4 (FastAPI 漏洞文章匹配到使用 FastAPI 的项目) 依赖 CodeGarden 域
(codegarden_repo + /api/tech-stack/impact), 已随工坊域整体删除退役
(2026-11-19)。

本文件是端到端验收: 通过 FastAPI TestClient 走完整 HTTP 链路,
不直接调用 service/repo, 确保从 API → service → repo → DB 全链路正确.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_phase2_acceptance.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # v1.8: feature flag 已接线到 router 注册, 测试需显式开启实验功能
    monkeypatch.setattr(config, "feature_review", True)
    monkeypatch.setattr(config, "feature_alert", True)
    monkeypatch.setattr(config, "feature_recommendation", True)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 验收 1: 新学概念创建后 24h 出现在复习队列
# ---------------------------------------------------------------------------
class TestAcceptance1NewConceptInQueue:
    """验收 1: 新学概念创建后 24h 出现在复习队列.

    流程:
      1. POST /api/reviews/{type}/{id} 创建首条复习 (默认 interval_days=1)
      2. GET /api/reviews/due 检查是否在队列
      3. 验证 due_at 落在 24h 窗口内 (0 < delta <= 24h)
    """

    def test_new_concept_appears_in_due_queue_within_24h(self, client):
        # 1. 创建首条复习 (默认 interval_days=1, due_at = now + 1d)
        r = client.post("/api/reviews/concept/sm2-concept-1")
        assert r.status_code in (200, 201), f"create failed: {r.text}"
        item = r.json()["item"]
        assert item["entity_type"] == "concept"
        assert item["entity_id"] == "sm2-concept-1"

        # 2. due_at 应在 24h 内
        due_at = datetime.fromisoformat(item["due_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = due_at - now
        assert 0 < delta.total_seconds() <= 24 * 3600, (
            f"due_at 应在 24h 内, 实际 delta={delta}"
        )

        # 3. 立即到期版本 (interval_days=0) 应出现在 due 队列
        client.post("/api/reviews/concept/sm2-concept-2?interval_days=0")
        r = client.get("/api/reviews/due")
        assert r.status_code == 200
        due_items = r.json()["items"]
        entity_ids = {it["entity_id"] for it in due_items}
        assert "sm2-concept-2" in entity_ids, (
            f"interval_days=0 的概念应立即出现在队列, got {entity_ids}"
        )

    def test_stats_reflects_new_concept(self, client):
        """创建后 stats.total 应增加."""
        r_before = client.get("/api/reviews/stats").json()["stats"]
        client.post("/api/reviews/concept/stats-test-1?interval_days=0")
        r_after = client.get("/api/reviews/stats").json()["stats"]
        assert r_after["total"] == r_before["total"] + 1


# ---------------------------------------------------------------------------
# 验收 2: 评分后间隔按 SM-2 延长
# ---------------------------------------------------------------------------
class TestAcceptance2SM2IntervalExtends:
    """验收 2: 评分后间隔按 SM-2 延长.

    SM-2 规则 (grade >= 3):
      - repetitions=0 → interval=1
      - repetitions=1 → interval=6
      - repetitions>=2 → interval=round(interval × easiness)
      - grade<3 重置: repetitions=0, interval=1

    流程:
      1. 创建复习 (interval=0 立即到期)
      2. 评分 grade=5 → interval 应从 0 → 1, repetitions 0 → 1
      3. 再评分 grade=5 → interval 应从 1 → 6, repetitions 1 → 2
      4. 再评分 grade=5 → interval 应从 6 → round(6 × easiness)
    """

    def test_interval_progresses_through_sm2_schedule(self, client):
        # 1. 创建立即到期复习
        client.post("/api/reviews/knowledge/sm2-prog?interval_days=0")

        # 2. 第一次评分 grade=5 → interval=1, reps=1, easiness 2.5→2.6
        r = client.post(
            "/api/reviews/knowledge/sm2-prog/grade",
            json={"grade": 5},
        )
        assert r.status_code == 200, f"grade 1 failed: {r.text}"
        item1 = r.json()["item"]
        assert item1["interval"] == 1, f"第一次 grade=5 后 interval 应=1, got {item1['interval']}"
        assert item1["repetitions"] == 1

        # 3. 第二次评分 grade=5 → interval=6, reps=2, easiness→2.7
        r = client.post(
            "/api/reviews/knowledge/sm2-prog/grade",
            json={"grade": 5},
        )
        item2 = r.json()["item"]
        assert item2["interval"] == 6, f"第二次 grade=5 后 interval 应=6, got {item2['interval']}"
        assert item2["repetitions"] == 2
        easiness_after_2 = item2["easiness"]

        # 4. 第三次评分 grade=5 → interval=round(6 × 旧easiness), reps=3
        # SM-2 规范: interval 用评分前的 easiness 计算, easiness 在 interval 之后更新
        r = client.post(
            "/api/reviews/knowledge/sm2-prog/grade",
            json={"grade": 5},
        )
        item3 = r.json()["item"]
        expected = round(6 * easiness_after_2)  # 用第二次评分后的 easiness (即第三次评分前的)
        assert item3["interval"] == expected, (
            f"第三次 interval 应=round(6×{easiness_after_2})={expected}, "
            f"got {item3['interval']}"
        )
        assert item3["repetitions"] == 3
        # easiness 应持续增长 (grade=5 时 +0.1)
        assert item3["easiness"] > easiness_after_2
        # interval 单调递增 (验收 2 核心: 间隔延长)
        assert item3["interval"] > item2["interval"] > item1["interval"]

    def test_low_grade_resets_interval(self, client):
        """grade < 3 应重置 interval=1, repetitions=0."""
        # 先评分到 interval=6
        client.post("/api/reviews/knowledge/sm2-reset?interval_days=0")
        client.post("/api/reviews/knowledge/sm2-reset/grade", json={"grade": 5})  # → 1
        client.post("/api/reviews/knowledge/sm2-reset/grade", json={"grade": 5})  # → 6

        # grade=2 (< 3) 重置
        r = client.post(
            "/api/reviews/knowledge/sm2-reset/grade",
            json={"grade": 2},
        )
        item = r.json()["item"]
        assert item["interval"] == 1, f"grade<3 应重置 interval=1, got {item['interval']}"
        assert item["repetitions"] == 0, f"grade<3 应重置 repetitions=0, got {item['repetitions']}"

    def test_invalid_grade_rejected(self, client):
        """grade 越界 (0-5 之外) 应被拒绝."""
        client.post("/api/reviews/knowledge/sm2-invalid?interval_days=0")
        r = client.post(
            "/api/reviews/knowledge/sm2-invalid/grade",
            json={"grade": 6},
        )
        assert r.status_code == 400 or r.status_code == 422


# ---------------------------------------------------------------------------
# 验收 3: 笔记 CRUD 正常
# ---------------------------------------------------------------------------
class TestAcceptance3AnnotationCRUD:
    """验收 3: 笔记 CRUD 正常.

    流程: Create → Read → Update → Delete, 每步校验状态.
    """

    def test_full_crud_cycle(self, client):
        # Create
        r = client.post(
            "/api/annotations",
            json={
                "entity_type": "knowledge",
                "entity_id": "crud-acc",
                "content": "初始笔记内容",
                "range_start": 0,
                "range_end": 10,
            },
        )
        assert r.status_code == 201
        created = r.json()["item"]
        aid = created["id"]
        assert created["content"] == "初始笔记内容"

        # Read (列表)
        r = client.get(
            "/api/annotations",
            params={"entity_type": "knowledge", "entity_id": "crud-acc"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == aid

        # Read (单条)
        r = client.get(f"/api/annotations/{aid}")
        assert r.status_code == 200
        assert r.json()["item"]["content"] == "初始笔记内容"

        # Update
        r = client.put(
            f"/api/annotations/{aid}",
            json={"content": "更新后的笔记"},
        )
        assert r.status_code == 200
        assert r.json()["item"]["content"] == "更新后的笔记"

        # Delete
        r = client.delete(f"/api/annotations/{aid}")
        assert r.status_code == 200
        # 再查应 404
        assert client.get(f"/api/annotations/{aid}").status_code == 404

    def test_multiple_notes_per_entity(self, client):
        """同一 entity 可有多条笔记."""
        for i in range(3):
            client.post(
                "/api/annotations",
                json={
                    "entity_type": "concept",
                    "entity_id": "multi-note",
                    "content": f"笔记 {i}",
                },
            )
        r = client.get(
            "/api/annotations",
            params={"entity_type": "concept", "entity_id": "multi-note"},
        )
        assert r.json()["count"] == 3


