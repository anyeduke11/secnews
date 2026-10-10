"""C3 (DEV-0191): hub-stats 聚合端点测试 — 空库零值 / 种子聚合 / 响应形状 / 逐源容错。

种子走既有 repo/service (upsert_item + generate_chunks_for_item), 测试内不写裸 SQL。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.knowledge_api import router as knowledge_router
from backend.domain.knowledge_models import KnowledgeItem

EXPECTED_KEYS = {
    "wiki_items", "wiki_chunks", "review_total", "review_due",
    "funnel_total", "queue_pending", "quality_checked_24h",
    "generated_at",
}

_NOW = "2026-09-16T00:00:00+00:00"


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router)
    return TestClient(app)


def test_shape_and_empty_db_zeros(client) -> None:
    r = client.get("/api/knowledge/hub-stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= EXPECTED_KEYS
    assert body["wiki_items"] == 0
    assert body["wiki_chunks"] == 0
    assert body["review_total"] == 0
    assert body["review_due"] == 0
    assert body["funnel_total"] == 0
    assert body["generated_at"]


def test_seed_aggregation_counts(client, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services import chunk_service, knowledge_sync

    knowledge_repo.upsert_item(KnowledgeItem(
        id="k-hub-1", title="聚合测试条目", source="unittest",
        ingested_at=_NOW, updated_at=_NOW,
    ))

    # chunks: 走 generate_chunks_for_item (monkeypatch items 目录, 正文 > MIN_CONTENT_LEN=40)
    items_dir = tmp_path / "items"
    items_dir.mkdir()
    (items_dir / "k-hub-1.md").write_text(
        "# 聚合测试条目\n\n这是用于 chunk 切分的测试正文，包含足够的字符数以超过最小长度阈值，"
        "并且包含句号用于按句切分。这里是第二句话，确保段落切分逻辑正常工作。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", items_dir)
    gen = chunk_service.generate_chunks_for_item("k-hub-1")
    assert gen.get("created", 0) >= 1

    r = client.get("/api/knowledge/hub-stats")
    body = r.json()
    assert body["wiki_items"] == 1
    assert body["wiki_chunks"] == gen["created"]


def test_queue_source_failure_is_isolated(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """队列源抛错 → queue_pending=None, 其余字段正常返回 (逐源容错)。"""

    def boom():
        raise RuntimeError("pipeline not ready")

    monkeypatch.setattr(
        "backend.kl_pipeline.runtime.get_production_pipeline", boom,
    )
    r = client.get("/api/knowledge/hub-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["queue_pending"] is None
    assert body["wiki_items"] == 0
