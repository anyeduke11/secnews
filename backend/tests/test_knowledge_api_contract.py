"""Contract tests for ``/api/knowledge/*`` — 锁定响应形状 (Batch 2 任务 A)。

目的: 在把单文件 ``backend/api/knowledge.py`` (711 行) 拆分为多个子 router
文件前后, 用同一套逐字断言锁定 URL/method/响应形状不变:

- status code
- JSON 顶层键集合
- 分页字段语义 (items/total, limit/offset 生效)

本文件不关心 handler 所在物理文件 — 拆分只允许改变 import 结构。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(temp_db):
    """Standalone FastAPI + knowledge router, temp DB (conftest 隔离 env)。"""
    from backend.api.knowledge import router as knowledge_router

    app = FastAPI()
    app.include_router(knowledge_router)
    return TestClient(app)


def _seed_item(item_id: str = "k_item_1", *, domain: str | None = "sec",
               topic: str | None = "tls") -> dict:
    from backend.domain.knowledge_models import KnowledgeItem
    from backend.repository.knowledge_repo import knowledge_repo

    item = KnowledgeItem(
        id=item_id, title="TLS fingerprinting basics", source="cubox",
        domain=domain, topic=topic, type="news", difficulty="beginner",
        tags=["tls", "fingerprint"], concepts=["tls"],
        ingested_at="2026-09-01T00:00:00", updated_at="2026-09-01T00:00:00",
    )
    knowledge_repo.upsert_item(item)
    return item.to_dict()


def _seed_items(n: int) -> None:
    for i in range(n):
        _seed_item(f"k_item_{i}")


def _seed_concept(slug: str = "tls", *, source_items: list[str] | None = None) -> None:
    from backend.domain.knowledge_models import KnowledgeConcept
    from backend.repository.knowledge_repo import knowledge_repo

    knowledge_repo.upsert_concept(KnowledgeConcept(
        slug=slug, title="TLS", domain="sec",
        source_items=source_items or [], updated_at="2026-09-01T00:00:00",
    ))


# ── GET /items (含分页) ─────────────────────────────────────────

def test_list_items_shape(client):
    _seed_items(3)
    r = client.get("/api/knowledge/items")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"items", "total"}
    assert body["total"] == 3
    assert len(body["items"]) == 3
    first = body["items"][0]
    assert first["id"] == "k_item_0"
    assert first["title"] == "TLS fingerprinting basics"


def test_list_items_pagination_semantics(client):
    _seed_items(5)
    r = client.get("/api/knowledge/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"items", "total"}
    # limit 截断返回条数; total 仍是全量计数 (不受 limit/offset 影响)
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert [i["id"] for i in body["items"]] == ["k_item_1", "k_item_2"]


def test_list_items_domain_filter(client):
    _seed_item("k_sec", domain="sec")
    _seed_item("k_cloud", domain="cloud")
    r = client.get("/api/knowledge/items", params={"domain": "cloud"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"items", "total"}
    assert body["total"] == 1
    assert body["items"][0]["id"] == "k_cloud"


# ── GET/PATCH/DELETE /items/{id} ────────────────────────────────

def test_get_item_detail(client):
    _seed_item()
    r = client.get("/api/knowledge/items/k_item_1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "k_item_1"
    assert "content" in body  # markdown 正文键始终存在
    assert isinstance(body["content"], str)


def test_get_item_404(client):
    r = client.get("/api/knowledge/items/no_such_item")
    assert r.status_code == 404
    assert r.json()["detail"] == "Item not found"


def test_patch_item_updates_fields(client):
    _seed_item()
    r = client.patch("/api/knowledge/items/k_item_1",
                     json={"tags": ["tls", "ja3"], "mastery": 40})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "k_item_1"
    assert body["tags"] == ["tls", "ja3"]
    assert body["mastery"] == 40


def test_patch_item_404(client):
    r = client.patch("/api/knowledge/items/no_such_item", json={"tags": []})
    assert r.status_code == 404


def test_delete_item(client):
    _seed_item()
    r = client.delete("/api/knowledge/items/k_item_1")
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": "k_item_1"}
    assert client.get("/api/knowledge/items/k_item_1").status_code == 404


def test_delete_item_404(client):
    r = client.delete("/api/knowledge/items/no_such_item")
    assert r.status_code == 404


# ── GET /topics ─────────────────────────────────────────────────

def test_list_topics(client):
    _seed_item("k_a", topic="tls")
    _seed_item("k_b", topic="sast")
    r = client.get("/api/knowledge/topics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"topics"}
    assert sorted(body["topics"]) == ["sast", "tls"]


# ── GET /concepts ───────────────────────────────────────────────

def test_list_concepts(client):
    _seed_concept()
    r = client.get("/api/knowledge/concepts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"concepts"}
    assert body["concepts"][0]["slug"] == "tls"


# ── GET /graph ──────────────────────────────────────────────────

def test_graph_shape(client):
    _seed_item()
    _seed_concept(source_items=["k_item_1"])
    r = client.get("/api/knowledge/graph")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"nodes", "edges"}
    assert isinstance(body["nodes"], list)
    assert isinstance(body["edges"], list)


# ── GET /search ─────────────────────────────────────────────────

def test_search_shape(client):
    # search 走 wiki md 文件扫描 (federation), 不查 SQLite — 这里只锁形状
    r = client.get("/api/knowledge/search", params={"q": "fingerprint"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"results", "total"}
    assert isinstance(body["results"], list)
    assert isinstance(body["total"], int)


def test_search_requires_q(client):
    r = client.get("/api/knowledge/search")
    assert r.status_code == 422  # q 必填


# ── GET/POST /tasks ─────────────────────────────────────────────

def test_post_task_creates(client):
    r = client.post("/api/knowledge/tasks",
                    json={"task_type": "generate_learning_plan", "params": {"week": "2026-W37"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_type"] == "generate_learning_plan"
    assert "id" in body
    assert body["status"] == "pending"


def test_list_tasks(client):
    client.post("/api/knowledge/tasks", json={"task_type": "t1"})
    r = client.get("/api/knowledge/tasks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"tasks"}
    assert any(t["task_type"] == "t1" for t in body["tasks"])


# ── GET /health ─────────────────────────────────────────────────

def test_health_metrics_shape(client):
    _seed_item()
    r = client.get("/api/knowledge/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "total_items", "total_concepts", "compiled_count", "compiled_ratio",
        "orphan_items", "stale_concepts", "gap_analysis",
    }
    assert body["total_items"] == 1
    assert body["total_concepts"] == 0
    assert isinstance(body["gap_analysis"], list)


# ── GET /skills (Phase 7 deprecated) ────────────────────────────

def test_list_skills_deprecated_empty(client):
    r = client.get("/api/knowledge/skills")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deprecated"] is True
    assert body["skills"] == []
    assert "version" in body


# ── GET /soul ───────────────────────────────────────────────────

def test_get_soul_shape(client):
    r = client.get("/api/knowledge/soul")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"content", "exists"}
    assert isinstance(body["content"], str)
    assert isinstance(body["exists"], bool)
