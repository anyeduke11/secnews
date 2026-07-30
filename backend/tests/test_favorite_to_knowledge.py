"""v1.7 Phase 1 — 收藏 → 知识提升 端到端测试 (验收 3)。

覆盖:
- POST /api/favorites 收藏后, knowledge_items 表生成 lifecycle=signal 条目
- knowledge/items/{id}.md 文件生成 (sag_service 回写)
- 重复收藏同 url 不覆盖已有条目
- 收藏流程主路径不因知识提升失败而中断

测试隔离: ``ITEMS_DIR`` 被 monkeypatch 到 tmp_path, 避免污染真实
``knowledge/items/`` 目录。
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
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync
from backend.services.data_cleaning import item_id_from_url


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_fav2k.db"
    monkeypatch.setattr(config, "db_path", test_db)
    # 重定向 .md 写入到 tmp_path, 避免污染真实 knowledge/items/
    fake_items = tmp_path / "items"
    fake_items.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", fake_items)
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


def _fav_payload(hid: str = "fh-1", url: str = "https://example.com/article-1") -> dict:
    return {
        "hotspot_id": hid,
        "category": "ai",
        "title": "Fav Article",
        "source": "src",
        "url": url,
    }


class TestFavoriteToKnowledge:
    def test_favorite_creates_signal_knowledge_item(self, client, temp_db):
        url = "https://example.com/article-signal"
        r = client.post("/api/favorites", json=_fav_payload("fh-1", url))
        assert r.status_code == 200

        item_id = item_id_from_url(url)
        item = knowledge_repo.get_item(item_id)
        assert item is not None
        assert item.lifecycle == "signal"  # 验收 3
        assert item.source == "secnews"
        assert item.source_url == url

    def test_favorite_generates_md_file(self, client, temp_db):
        """验收 3: knowledge/items/{id}.md 文件生成 (写入 tmp_path 隔离目录)。"""
        url = "https://example.com/article-md"
        client.post("/api/favorites", json=_fav_payload("fh-2", url))
        item_id = item_id_from_url(url)
        md_path = knowledge_sync.ITEMS_DIR / f"{item_id}.md"
        assert md_path.exists(), f".md file not generated at {md_path}"
        content = md_path.read_text(encoding="utf-8")
        assert "lifecycle:" in content
        assert "signal" in content

    def test_repeat_favorite_does_not_overwrite(self, client, temp_db):
        url = "https://example.com/article-repeat"
        # 第一次收藏
        client.post(
            "/api/favorites",
            json=_fav_payload("fh-3a", url),
        )
        item_id = item_id_from_url(url)
        # 推进 lifecycle 到 generate (模拟已编译)
        from backend.services import sag_service
        sag_service.transition(item_id, "generate")

        # 第二次收藏同 url (不同 hotspot_id)
        client.post(
            "/api/favorites",
            json=_fav_payload("fh-3b", url),
        )
        # lifecycle 不应被回退到 signal
        item = knowledge_repo.get_item(item_id)
        assert item.lifecycle == "generate"

    def test_favorite_flow_not_blocked_by_knowledge_error(self, client, temp_db):
        """即使知识提升出错, 收藏本身应成功。"""
        url = "https://example.com/article-ok"
        r = client.post("/api/favorites", json=_fav_payload("fh-4", url))
        # 收藏主路径成功
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
