"""DeepRead API 路由层回归测试.

为什么需要这个文件
------------------
``GET /api/deep-read/{type}/{id}`` 此前**恒定 500**: ``svc.fetch`` 是 async 方法,
却被 ``asyncio.to_thread`` 包了一层, 拿到的是从未 await 的协程对象, 下一行
``item.to_dict()`` 抛 ``AttributeError: 'coroutine' object has no attribute 'to_dict'``。

只有 service 层测试的话永远看不见这类 bug —— 服务层直接 ``asyncio.run(svc.run(...))``
是正常的, 崩的是路由的调用方式。所以本文件专门用 TestClient 打真实路由。

覆盖:
  A1 已存解读 → 200, sections 是**有序数组**且每项带 key/title/tone/body
  A2 不同 category 落库 → 分节集合不同 (按文章类型给不同视角)
  A3 不存在的实体 → 404 (不是 500)
  A4 旧格式扁平行 (无 v1 envelope) → 仍可读, 回落中文标题, 不崩
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.config import config
from backend.main import app
from backend.repository import db
from backend.repository.deepread_repo import DeepReadRepository


@pytest.fixture
def client(temp_db):
    return TestClient(app)


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test_deep_read_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _seed(entity_id: str, category: str, profile_cat: str) -> None:
    """按 v1 envelope 落一行解读 (不调 LLM)。"""
    from backend.services.ai_hub.prompts import deep_read_sections

    defs = deep_read_sections(profile_cat)
    sections = {d["key"]: f"正文-{d['title']}" for d in defs}
    ordered = [{**d, "body": sections[d["key"]]} for d in defs]
    DeepReadRepository().upsert(
        entity_type="hotspot",
        entity_id=entity_id,
        content_md="\n".join(f"## {d['title']}\n\n{sections[d['key']]}" for d in defs),
        sections_json=json.dumps(
            {"schema": 1, "category": category, "profile_version": "v1", "sections": ordered},
            ensure_ascii=False,
        ),
        provider="sensenova",
        model="sensenova-6.8-flash-lite",
        tokens_in=200,
        tokens_out=150,
        cost_usd=0.0,
        latency_ms=12000,
    )


def _keys(payload: dict) -> list[str]:
    return [s["key"] for s in payload["sections"]]


def test_get_returns_sections_as_ordered_array(client):
    """A1: 曾经 500 的路径现在必须 200, 且分节是数组不是固定 4 字段对象。"""
    _seed("h-array", "security", "security")

    r = client.get("/api/deep-read/hotspot/h-array")

    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["sections"], list)
    assert _keys(body) == _keys(json.loads(body["sections_json"]))
    for s in body["sections"]:
        assert set(s) >= {"key", "title", "tone", "body"}
        assert s["body"].startswith("正文-")
    assert body["category"] == "security"


def test_security_and_bid_categories_yield_different_section_sets(client):
    """A2: 同一套路由, 不同文章类型必须给出不同分节集合。"""
    _seed("h-sec", "security", "security")
    _seed("h-bid", "bid", "bid")

    sec = client.get("/api/deep-read/hotspot/h-sec").json()
    bid = client.get("/api/deep-read/hotspot/h-bid").json()

    assert "impact_ioc" in _keys(sec) and "qualification" not in _keys(sec)
    assert "qualification" in _keys(bid) and "impact_ioc" not in _keys(bid)
    # 跨类可比的固定骨架
    assert _keys(sec)[0] == _keys(bid)[0] == "key_takeaways"
    assert _keys(sec)[-2:] == _keys(bid)[-2:] == ["next_actions", "evidence_gaps"]
    # red 只出现在漏洞语境
    assert any(s["tone"] == "red" for s in sec["sections"])
    assert not any(s["tone"] == "red" for s in bid["sections"])


def test_missing_entity_is_404_not_500(client):
    """A3: 读不到必须是 404 —— 500 会让前端无法区分"没有"与"坏了"。"""
    r = client.get("/api/deep-read/hotspot/nope-missing")
    assert r.status_code == 404
    assert "nope-missing" in r.text


def test_legacy_flat_row_still_readable(client):
    """A4: v1 envelope 之前的扁平行必须仍能渲染, 标题回落中文表。"""
    DeepReadRepository().upsert(
        entity_type="hotspot",
        entity_id="h-legacy",
        content_md="## 摘要\n\n旧内容",
        sections_json=json.dumps(
            {"summary": "旧摘要", "impact": "旧影响", "relations": "", "risks": "旧风险"},
            ensure_ascii=False,
        ),
        provider="preset",
        model="preset-model",
        tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1,
    )

    r = client.get("/api/deep-read/hotspot/h-legacy")

    assert r.status_code == 200, r.text
    body = r.json()
    titles = {s["key"]: s["title"] for s in body["sections"]}
    assert titles["summary"] == "摘要"
    assert titles["risks"] == "风险"
    got = {s["key"]: s["body"] for s in body["sections"]}
    assert got["summary"] == "旧摘要"
