"""Phase 28 历史资讯 API 集成测试.

覆盖场景
--------
- GET /api/history/batches:
  * 首批 (cursor=None): 返回所有有数据的批次 (按 batch_no DESC)
  * 不含当前批次 (current_batch 的数据不出现在列表)
  * 分页 (cursor 传上次 next_cursor)
- GET /api/history/batches/{batch_no}/items:
  * 正常返回该批次内 items
  * 分类筛选
  * 关键词搜索 (FTS5)
  * 异常 batch_no (< 1) → 400
- GET /api/history/batches/{batch_no}/summary:
  * 正常返回分类分布 + Top5 信源
  * 异常 batch_no → 400
- GET /api/history/batches/{batch_no}/range:
  * 正常返回 [start, end)
  * 异常 batch_no → 400
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import reload

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.services import batch_service
from backend.services.batch_service import (
    HISTORY_START_DATE,
    get_batch_range,
)


@pytest.fixture(autouse=True)
def shifted_history_start(monkeypatch):
    """把 HISTORY_START_DATE 往过去推 21 天, 让 current_bn >= 4, 留出历史批次空间."""
    new_start = HISTORY_START_DATE - timedelta(days=21)
    monkeypatch.setattr(batch_service, "HISTORY_START_DATE", new_start)
    # 同步 reload 让 @dataclass / 顶层常量都生效 (此处 HISTORY_START_DATE 是 module-level)
    yield new_start


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_history.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


def _make_item(
    idx: int,
    category: Category,
    source: str,
    ingested_at: datetime,
    title: str | None = None,
) -> HotspotItem:
    return HotspotItem(
        id=f"test_{category.value}_{idx}",
        title=title or f"Test {category.value} item {idx}",
        summary=None,
        source=source,
        url=f"https://example.com/{category.value}/{idx}",
        category=category,
        published_at=ingested_at,
        fetched_at=ingested_at,
        ingested_at=ingested_at,
        quality_score=100,
        quality_flags=[],
    )


def _seed_batch(items_per_batch: int = 3) -> list[HotspotItem]:
    """种 3 个历史批次, 每个 3 条.

    依赖 shifted_history_start fixture: HISTORY_START_DATE 已经被推到 21 天前,
    所以 current_bn >= 4, 批次 1/2/3 都是历史批次.
    """
    repo = HotspotRepository()
    items: list[HotspotItem] = []
    for batch_offset in [1, 2, 3]:  # 比 current 早 1, 2, 3 个批次
        bn = batch_offset
        start, end = get_batch_range(bn)
        mid = start + (end - start) / 2
        for i in range(items_per_batch):
            items.append(
                _make_item(
                    idx=bn * 100 + i,
                    category=Category.SECURITY,
                    source=f"TestSource_{bn}",
                    ingested_at=mid + timedelta(hours=i),
                )
            )
    repo.upsert_many(items)
    return items


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestListBatches:
    def test_empty_db_returns_empty(self, client: TestClient):
        r = client.get("/api/history/batches")
        assert r.status_code == 200
        data = r.json()
        assert data["batches"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_seeded_returns_historical_batches(self, client: TestClient):
        _seed_batch(items_per_batch=3)
        r = client.get("/api/history/batches")
        assert r.status_code == 200
        data = r.json()
        # 种了 3 个历史批次, 每个 3 条
        assert len(data["batches"]) == 3
        assert data["total"] == 9
        # 按 batch_no DESC 排列
        batch_nos = [b["batch_no"] for b in data["batches"]]
        assert batch_nos == sorted(batch_nos, reverse=True)

    def test_current_batch_excluded(self, client: TestClient):
        """当前批次的数据不应出现在历史批次列表中."""
        repo = HotspotRepository()
        today = datetime.now(timezone.utc)
        current_item = _make_item(
            idx=999,
            category=Category.AI,
            source="CurrentBatch",
            ingested_at=today,
        )
        repo.upsert_many([current_item])
        r = client.get("/api/history/batches")
        data = r.json()
        # 没有历史数据 → 空
        assert data["batches"] == []

    def test_pagination_cursor(self, client: TestClient):
        _seed_batch(items_per_batch=3)
        # 拿第 1 页
        r1 = client.get("/api/history/batches", params={"limit": 2})
        d1 = r1.json()
        assert len(d1["batches"]) == 2
        assert d1["has_more"] is True
        assert d1["next_cursor"] is not None

        # 拿第 2 页
        r2 = client.get(
            "/api/history/batches",
            params={"limit": 2, "cursor": d1["next_cursor"]},
        )
        d2 = r2.json()
        assert len(d2["batches"]) == 1
        assert d2["has_more"] is False
        assert d2["next_cursor"] is None

    def test_batch_metadata_fields(self, client: TestClient):
        _seed_batch(items_per_batch=2)
        r = client.get("/api/history/batches")
        b = r.json()["batches"][0]
        assert "batch_no" in b
        assert "start" in b
        assert "end" in b
        assert "item_count" in b
        assert "favorite_count" in b
        assert b["item_count"] == 2


class TestBatchItems:
    def test_returns_items_in_batch(self, client: TestClient):
        _seed_batch(items_per_batch=2)
        bn = 1  # 第一个历史批次

        r = client.get(f"/api/history/batches/{bn}/items")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) == 2

    def test_category_filter(self, client: TestClient):
        repo = HotspotRepository()
        start, _ = get_batch_range(1)
        items = [
            _make_item(1, Category.SECURITY, "s", start + timedelta(hours=1), title="Sec news"),
            _make_item(2, Category.AI, "s", start + timedelta(hours=2), title="AI news"),
        ]
        repo.upsert_many(items)

        r = client.get(
            "/api/history/batches/1/items",
            params={"category": "security"},
        )
        data = r.json()
        assert all(it["category"] == "security" for it in data["items"])

    def test_keyword_filter_fts(self, client: TestClient):
        repo = HotspotRepository()
        start, _ = get_batch_range(1)
        items = [
            _make_item(1, Category.SECURITY, "s", start + timedelta(hours=1), title="CVE-2026-12345 vulnerability"),
            _make_item(2, Category.AI, "s", start + timedelta(hours=2), title="GPT model release"),
        ]
        repo.upsert_many(items)

        r = client.get(
            "/api/history/batches/1/items",
            params={"keyword": "CVE"},
        )
        data = r.json()
        assert len(data["items"]) >= 1
        assert any("CVE" in it["title"] for it in data["items"])

    def test_invalid_batch_no_returns_400(self, client: TestClient):
        r = client.get("/api/history/batches/0/items")
        assert r.status_code == 400

    def test_invalid_category_returns_400(self, client: TestClient):
        r = client.get("/api/history/batches/1/items", params={"category": "invalid"})
        assert r.status_code == 400


class TestBatchSummary:
    def test_summary_structure(self, client: TestClient):
        _seed_batch(items_per_batch=3)
        bn = 1

        r = client.get(f"/api/history/batches/{bn}/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["batch_no"] == bn
        assert "start" in data
        assert "end" in data
        assert "total" in data
        assert "category_breakdown" in data
        assert "top_sources" in data
        assert data["total"] == 3

    def test_invalid_batch_no_returns_400(self, client: TestClient):
        r = client.get("/api/history/batches/-1/summary")
        assert r.status_code == 400


class TestBatchRange:
    def test_returns_range(self, client: TestClient, shifted_history_start):
        r = client.get("/api/history/batches/1/range")
        assert r.status_code == 200
        data = r.json()
        assert data["batch_no"] == 1
        assert data["start"].startswith(shifted_history_start.isoformat())
        assert data["end"].startswith((shifted_history_start + timedelta(days=7)).isoformat())

    def test_invalid_batch_no_returns_400(self, client: TestClient):
        r = client.get("/api/history/batches/0/range")
        assert r.status_code == 400
