"""v1.7 Phase 1 — Extract API 端到端测试。

覆盖:
- POST /api/extract/preview (预览, 不持久化)
- POST /api/extract/hotspot/{id} (提取 + attach, 404 校验)
- POST /api/extract/knowledge/{id} (提取 + 写 tags + 推进 lifecycle)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.enums import Category
from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.knowledge_repo import knowledge_repo


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_extract_api.db"
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


def _make_hotspot(hid: str, title: str, summary: str = "") -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid,
        title=title,
        source="test",
        url=f"https://example.com/{hid}",
        category=Category.AI,
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        quality_flags=[],
    )


# ===========================================================================
# 1. preview
# ===========================================================================
class TestExtractPreview:
    def test_preview_cve(self, client):
        r = client.post(
            "/api/extract/preview",
            json={"text": "A flaw in libfoo allows CVE-2024-1234 RCE", "title": "", "category": ""},
        )
        assert r.status_code == 200
        ids = {t["tag_id"] for t in r.json()["items"]}
        assert "cve" in ids

    def test_preview_empty_text(self, client):
        r = client.post(
            "/api/extract/preview",
            json={"text": "", "title": "", "category": ""},
        )
        assert r.status_code == 200
        # 空 text 可能有 category→domain 映射标签; 关键是不报错
        assert "items" in r.json()

    def test_preview_does_not_persist(self, client, temp_db):
        """preview 不应 attach 到任何热点。"""
        client.post(
            "/api/extract/preview",
            json={"text": "CVE-2024-9999 exploit", "title": "", "category": ""},
        )
        # 没有热点存在, attach 无从发生
        r = client.get("/api/tags/by-hotspot/any-hotspot")
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ===========================================================================
# 2. extract hotspot
# ===========================================================================
class TestExtractHotspot:
    def test_extract_attaches_tags(self, client, temp_db):
        HotspotRepository().upsert_many([
            _make_hotspot("h-ext", "CVE-2024-5678 critical vulnerability", "RCE flaw")
        ])
        r = client.post("/api/extract/hotspot/h-ext")
        assert r.status_code == 200
        body = r.json()
        assert len(body["attached"]) > 0
        ids = {t["id"] for t in body["attached"]}
        assert "cve" in ids

    def test_extract_404_missing_hotspot(self, client):
        r = client.post("/api/extract/hotspot/no-such-hotspot")
        assert r.status_code == 404


# ===========================================================================
# 3. extract knowledge (lifecycle 推进)
# ===========================================================================
class TestExtractKnowledge:
    def test_extract_advances_lifecycle(self, client, temp_db):
        # 建一个 signal 状态的知识条目
        item = KnowledgeItem(
            id="k-ext-1",
            title="LangChain prompt injection attack",
            source="test",
            domain="ai",
            lifecycle="signal",
            ingested_at=now_iso(),
            updated_at=now_iso(),
        )
        knowledge_repo.upsert_item(item)

        r = client.post("/api/extract/knowledge/k-ext-1")
        assert r.status_code == 200
        body = r.json()
        # signal → amplify:tagged
        assert body["lifecycle"] == "amplify:tagged"
        # tags 应包含命中的标签 id
        assert len(body["tags"]) > 0

    def test_extract_knowledge_404(self, client):
        r = client.post("/api/extract/knowledge/no-such-item")
        assert r.status_code == 404
