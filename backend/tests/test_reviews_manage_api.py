"""复习栈能力丰富 (migration 120) — 管理面 API + enrich + undo 测试。

2026-09-21 设计稿 §5 验收口径:
- enrich 解析命中 (hotspot/knowledge_item) 与未命中兜底 (title=None)
- undo 正常恢复 (含 prev_last_grade/prev_last_reviewed_at) + 无活跃 log → 409
- undo 首评撤销 = 删除记录; 链式可重复调用逐级回退
- forecast 聚合 (含今日, 恒 N 条, 排除 suspended)
- suspended 影响 due 队列与预报; PATCH/DELETE 端点
- submit_grade 写 review_log 断言; stats 扩展字段
- migration 120 幂等 (init_db 可重复执行)
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.reviews_log_repo import ReviewLogRepository
from backend.services import review_service


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_reviews_manage.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db, monkeypatch) -> TestClient:
    monkeypatch.setattr(config, "feature_review", True)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


def _insert_hotspot(item_id: str, title: str = "CVE-2026-12345 在野利用分析") -> None:
    db.get_connection().execute(
        """
        INSERT INTO hotspots (id, title, summary, source, url, category,
            published_at, fetched_at, is_fallback, quality_score, quality_flags)
        VALUES (?, ?, ?, 'test', 'https://example.com/a', 'security',
            '2026-09-20T00:00:00', '2026-09-20T00:00:00', 0, 100, '[]')
        """,
        (item_id, title, "某漏洞已出现在野利用"),
    )


def _insert_knowledge(item_id: str, title: str = "SM-2 间隔重复算法笔记") -> None:
    db.get_connection().execute(
        """
        INSERT INTO knowledge_items (id, title, source, source_url, domain,
            ingested_at, updated_at)
        VALUES (?, ?, 'test', 'https://example.com/k', 'method',
            '2026-09-20T00:00:00', '2026-09-20T00:00:00')
        """,
        (item_id, title),
    )


class TestEnrich:
    def test_enrich_hit_hotspot_and_knowledge(self, client):
        """enrich=1 → 命中源表的卡带真实 title/url/category/excerpt。"""
        _insert_hotspot("h-hit")
        _insert_knowledge("k-hit")
        client.post("/api/reviews/hotspot/h-hit", params={"interval_days": 0})
        client.post("/api/reviews/knowledge_item/k-hit", params={"interval_days": 0})

        r = client.get("/api/reviews/due", params={"enrich": 1, "limit": 200})
        assert r.status_code == 200
        by_key = {(i["entity_type"], i["entity_id"]): i for i in r.json()["items"]}

        h = by_key[("hotspot", "h-hit")]
        assert h["title"] == "CVE-2026-12345 在野利用分析"
        assert h["url"] == "https://example.com/a"
        assert h["category"] == "security"
        assert h["excerpt"] == "某漏洞已出现在野利用"

        k = by_key[("knowledge_item", "k-hit")]
        assert k["title"] == "SM-2 间隔重复算法笔记"
        assert k["url"] == "https://example.com/k"
        assert k["category"] == "method"
        assert k["excerpt"] is None  # knowledge_items 无摘要列

    def test_enrich_miss_falls_back_to_raw_id(self, client):
        """未注册类型/源行已删除 → 四键置 None, 前端如实渲染裸 id。"""
        client.post("/api/reviews/concept/ghost-1", params={"interval_days": 0})
        r = client.get("/api/reviews/due", params={"enrich": 1})
        item = next(
            i for i in r.json()["items"] if i["entity_id"] == "ghost-1"
        )
        assert item["title"] is None
        assert item["url"] is None
        assert item["category"] is None
        assert item["excerpt"] is None
        # entity 字段保持原样
        assert item["entity_type"] == "concept"

    def test_no_enrich_omits_keys(self, client):
        """缺省 (enrich=0) 保持旧契约, 不附四键。"""
        client.post("/api/reviews/concept/plain-1", params={"interval_days": 0})
        r = client.get("/api/reviews/due")
        item = r.json()["items"][0]
        assert "title" not in item


class TestSubmitGradeWritesLog:
    def test_grade_writes_review_log_snapshot(self, temp_db):
        """submit_grade → review_log 写一条 旧→新 全量快照。"""
        review_service.create_review("concept", "lg-1", initial_interval_days=0)
        before = review_service.list_due(limit=10)[0]
        review_service.submit_grade("concept", "lg-1", grade=4)

        logs = ReviewLogRepository().list_recent(limit=10)
        assert len(logs) == 1
        log = logs[0]
        assert log["entity_id"] == "lg-1"
        assert log["grade"] == 4
        assert log["prev_due_at"] == before["due_at"]
        assert log["prev_last_grade"] == -1  # create_review 的未评标记
        assert log["new_interval"] == 1
        assert log["new_repetitions"] == 1
        assert log["reverted"] == 0

    def test_stats_extension_fields(self, temp_db):
        """stats 增 retention_30d / grade_distribution / suspended_count。"""
        review_service.submit_grade("concept", "st-1", grade=5)
        review_service.submit_grade("concept", "st-2", grade=1)
        s = review_service.stats()
        assert s["retention_30d"] == 0.5  # 1 / 2 通过
        assert s["grade_distribution"] == {"5": 1, "1": 1}
        assert s["suspended_count"] == 0

    def test_stats_retention_null_when_no_logs(self, temp_db):
        s = review_service.stats()
        assert s["retention_30d"] is None
        assert s["grade_distribution"] == {}


class TestUndo:
    def test_undo_restores_prev_state(self, client):
        """undo → 恢复最新活跃 log 的 prev 状态 (含 last_grade/last_reviewed_at)。"""
        client.post("/api/reviews/concept/u-1", params={"interval_days": 3})
        first = client.get("/api/reviews/concept/u-1").json()["item"]
        client.post("/api/reviews/concept/u-1/grade", json={"grade": 4})

        r = client.post("/api/reviews/concept/u-1/undo")
        assert r.status_code == 200
        item = r.json()["item"]
        assert item["interval"] == first["interval"]
        assert item["repetitions"] == first["repetitions"]
        assert item["due_at"] == first["due_at"]
        assert item["last_grade"] == first["last_grade"]
        assert item["last_reviewed_at"] == first["last_reviewed_at"]

    def test_undo_first_grade_deletes_record(self, client):
        """首评撤销 (prev 为空) = 删除记录。"""
        client.post("/api/reviews/concept/u-2/grade", json={"grade": 5})
        r = client.post("/api/reviews/concept/u-2/undo")
        assert r.status_code == 200
        assert r.json()["item"] is None
        assert client.get("/api/reviews/concept/u-2").status_code == 404

    def test_undo_chained_walks_back_level_by_level(self, client):
        """链式 undo 逐级回退; log 耗尽 → 409。"""
        client.post("/api/reviews/concept/u-3", params={"interval_days": 0})
        client.post("/api/reviews/concept/u-3/grade", json={"grade": 4})  # log1
        client.post("/api/reviews/concept/u-3/grade", json={"grade": 4})  # log2

        r1 = client.post("/api/reviews/concept/u-3/undo")
        assert r1.json()["item"]["repetitions"] == 1  # 回到 grade1 后
        r2 = client.post("/api/reviews/concept/u-3/undo")
        assert r2.json()["item"]["repetitions"] == 0  # 回到建卡原始态
        assert r2.json()["item"]["last_grade"] == -1

        r3 = client.post("/api/reviews/concept/u-3/undo")
        assert r3.status_code == 409  # 无活跃 log (扁平 envelope 契约)
        assert "无可撤销" in r3.json()["message"]


class TestSuspend:
    def test_suspend_removes_from_due_and_forecast(self, client):
        """暂停卡 → due 队列与预报同步消失; 恢复后回来。"""
        client.post("/api/reviews/concept/su-1", params={"interval_days": 0})
        assert any(
            i["entity_id"] == "su-1"
            for i in client.get("/api/reviews/due").json()["items"]
        )
        assert client.get("/api/reviews/forecast").json()["items"][0]["count"] >= 1

        r = client.patch("/api/reviews/concept/su-1", json={"suspended": True})
        assert r.status_code == 200
        assert not any(
            i["entity_id"] == "su-1"
            for i in client.get("/api/reviews/due").json()["items"]
        )
        assert client.get("/api/reviews/forecast").json()["items"][0]["count"] == 0
        assert client.get("/api/reviews/stats").json()["stats"]["suspended_count"] == 1
        # 管理视图仍可见 (含 suspended 状态)
        card = next(
            c for c in client.get("/api/reviews/cards").json()["items"]
            if c["entity_id"] == "su-1"
        )
        assert card["suspended"] == 1

        # 恢复
        client.patch("/api/reviews/concept/su-1", json={"suspended": False})
        assert any(
            i["entity_id"] == "su-1"
            for i in client.get("/api/reviews/due").json()["items"]
        )

    def test_suspend_missing_card_404(self, client):
        r = client.patch("/api/reviews/concept/nope", json={"suspended": True})
        assert r.status_code == 404


class TestForecastAndDelete:
    def test_forecast_shape_contains_today(self, client):
        """恒返回 N 条, 含今日, 空缺日补 0。"""
        client.post("/api/reviews/concept/f-1", params={"interval_days": 0})
        r = client.get("/api/reviews/forecast", params={"days": 7})
        items = r.json()["items"]
        assert len(items) == 7
        assert items[0]["count"] >= 1  # interval_days=0 → 今日到期
        assert sum(i["count"] for i in items) >= 1
        assert all(set(i) == {"date", "count"} for i in items)

    def test_delete_endpoint(self, client):
        client.post("/api/reviews/concept/d-1", params={"interval_days": 0})
        r = client.delete("/api/reviews/concept/d-1")
        assert r.status_code == 200
        assert r.json()["deleted"] == 1
        assert client.get("/api/reviews/concept/d-1").status_code == 404
        # 幂等性: 再删 → 404
        assert client.delete("/api/reviews/concept/d-1").status_code == 404


class TestCardsAndHistory:
    def test_cards_enriched_full_list(self, client):
        _insert_hotspot("h-card")
        client.post("/api/reviews/hotspot/h-card", params={"interval_days": 0})
        r = client.get("/api/reviews/cards")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(i["title"] == "CVE-2026-12345 在野利用分析" for i in items)

    def test_history_returns_reverted_flag(self, client):
        client.post("/api/reviews/concept/hh-1/grade", json={"grade": 3})
        client.post("/api/reviews/concept/hh-1/undo")
        r = client.get("/api/reviews/history")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["grade"] == 3
        assert items[0]["reverted"] == 1


class TestMigrationIdempotent:
    def test_init_db_twice_is_safe(self, temp_db):
        """migration 120 幂等: ALTER 仅随 schema_version 执行一次, 重复 init 不炸。"""
        db.init_db()  # 第二次调用
        # suspended 列可用
        cols = {
            r[1] for r in db.get_connection()
            .execute("PRAGMA table_info(sm2_reviews)").fetchall()
        }
        assert "suspended" in cols
        log_cols = {
            r[1] for r in db.get_connection()
            .execute("PRAGMA table_info(review_log)").fetchall()
        }
        assert {"reverted", "prev_last_grade", "new_due_at"} <= log_cols
