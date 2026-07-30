"""v1.8 Phase 8 — knowledge imported API endpoint 单测.

覆盖 (7 用例):
  - D1  空结果返回空列表
  - D2  分页参数正确
  - D3  type 筛选
  - D4  keyword 搜索
  - D5  时间范围
  - D6  参数校验
  - D7  异常处理
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api import knowledge_imported
from backend.config import config
from backend.repository import db
from backend.services.imported_aggregator import ImportedItem, ImportedResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path, 通过 init_db() 应用全部 migrations."""
    test_db = tmp_path / "test_knowledge_imported_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    """创建 FastAPI TestClient, 隔离 DB."""
    from backend.main import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_item(
    item_id: str = "fav_1",
    title: str = "Test Title",
    url: str = "https://example.com/1",
    source_type: str = "favorites",
    ingested_at: str = "2026-07-28T12:00:00+00:00",
) -> ImportedItem:
    return ImportedItem(
        id=item_id,
        title=title,
        url=url,
        source_type=source_type,
        source_name="手动收藏",
        ingested_at=ingested_at,
        origin="手动收藏",
    )


def _make_result(items: list[ImportedItem], total: int, page: int = 1, page_size: int = 20) -> ImportedResult:
    return ImportedResult(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# D1 — 空结果
# ---------------------------------------------------------------------------
def test_list_imported_empty(client):
    """空结果返回空列表, total=0."""
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.return_value = _make_result([], total=0)

        resp = client.get("/api/knowledge/imported")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


# ---------------------------------------------------------------------------
# D2 — 分页参数
# ---------------------------------------------------------------------------
def test_list_imported_pagination(client):
    """分页参数正确传递到 aggregator."""
    items = [_make_item(item_id=f"fav_{i}") for i in range(3)]
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.return_value = _make_result(items, total=3, page=2, page_size=5)

        resp = client.get("/api/knowledge/imported", params={"page": 2, "page_size": 5})

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 3
    assert len(body["items"]) == 3
    # 验证 aggregator.get_items 被传入正确的分页参数
    mock_agg.get_items.assert_called_once_with(
        source_type=None,
        keyword=None,
        since=None,
        until=None,
        page=2,
        page_size=5,
    )


# ---------------------------------------------------------------------------
# D3 — type 筛选
# ---------------------------------------------------------------------------
def test_list_imported_type_filter(client):
    """type 筛选传递给 aggregator."""
    items = [_make_item(source_type="cubox")]
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.return_value = _make_result(items, total=1)

        resp = client.get("/api/knowledge/imported", params={"type": "cubox"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["source_type"] == "cubox"
    mock_agg.get_items.assert_called_once_with(
        source_type="cubox",
        keyword=None,
        since=None,
        until=None,
        page=1,
        page_size=20,
    )


# ---------------------------------------------------------------------------
# D4 — keyword 搜索
# ---------------------------------------------------------------------------
def test_list_imported_keyword(client):
    """keyword 搜索传递给 aggregator."""
    items = [_make_item(title="AI 安全文章")]
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.return_value = _make_result(items, total=1)

        resp = client.get("/api/knowledge/imported", params={"keyword": "AI"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    mock_agg.get_items.assert_called_once_with(
        source_type=None,
        keyword="AI",
        since=None,
        until=None,
        page=1,
        page_size=20,
    )


# ---------------------------------------------------------------------------
# D5 — 时间范围
# ---------------------------------------------------------------------------
def test_list_imported_time_range(client):
    """since/until 时间范围传递给 aggregator."""
    items = [_make_item(ingested_at="2026-07-25T00:00:00+00:00")]
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.return_value = _make_result(items, total=1)

        resp = client.get(
            "/api/knowledge/imported",
            params={
                "since": "2026-07-01T00:00:00+00:00",
                "until": "2026-07-31T00:00:00+00:00",
            },
        )

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    mock_agg.get_items.assert_called_once_with(
        source_type=None,
        keyword=None,
        since="2026-07-01T00:00:00+00:00",
        until="2026-07-31T00:00:00+00:00",
        page=1,
        page_size=20,
    )


# ---------------------------------------------------------------------------
# D6 — 参数校验
# ---------------------------------------------------------------------------
def test_list_imported_invalid_params(client):
    """非法参数（page<1, page_size>100）返回 422."""
    # page < 1
    resp = client.get("/api/knowledge/imported", params={"page": 0})
    assert resp.status_code == 422

    # page_size > 100
    resp = client.get("/api/knowledge/imported", params={"page_size": 101})
    assert resp.status_code == 422

    # page_size < 1
    resp = client.get("/api/knowledge/imported", params={"page_size": 0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# D7 — 异常处理
# ---------------------------------------------------------------------------
def test_list_imported_error(client):
    """aggregator 抛出异常时返回 500."""
    with patch.object(knowledge_imported, "aggregator") as mock_agg:
        mock_agg.get_items.side_effect = RuntimeError("DB connection failed")

        resp = client.get("/api/knowledge/imported")

    assert resp.status_code == 500
    body = resp.json()
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        assert "message" in detail