# backend/tests/test_pipeline_ner.py
"""pipeline_ner gate — t1 score 成功后 extract_entities 落 knowledge_items.entities。

契约: gate 关零改动; 实体为空不写; gate 关闭时 t1 不调 LLM;
迁移后 entities 列存在 (JSON 数组字符串, 可空)。
"""
import json

import pytest

from backend.extensions import reset_gates
from backend.repository.db import get_connection, knowledge_items_table
from backend.services.triggers import t1_raw_to_refine as t1


@pytest.fixture(autouse=True)
def _restore():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"pipeline_ner": true}}'
    )
    reset_gates()


def _insert_item(item_id: str = "it_ner_1") -> None:
    # ingested_at / updated_at NOT NULL 无 DEFAULT — 缺列会被 OR IGNORE 静默吞掉。
    now = "2026-09-18T00:00:00+00:00"
    conn = get_connection()
    conn.execute(
        f"INSERT OR IGNORE INTO {knowledge_items_table()} "
        f"(id, title, source, lifecycle, ingested_at, updated_at) "
        f"VALUES (?, ?, ?, ?, ?, ?)",
        (item_id, "测试标题", "测试源", "kl:raw", now, now),
    )


def test_migration_entities_column_exists():
    _insert_item()
    cols = {
        row["name"] for row in
        get_connection().execute(f"PRAGMA table_info({knowledge_items_table()})").fetchall()
    }
    assert "entities" in cols


def test_write_entities_roundtrip():
    _insert_item("it_ner_2")
    t1.write_entities("it_ner_2", ["CVE-2026-1234", "ATT&CK T1059"])
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_2",)
    ).fetchone()
    assert json.loads(row["entities"]) == ["CVE-2026-1234", "ATT&CK T1059"]


def test_enrich_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
    reset_gates()
    called = {"n": 0}

    async def fake_ents(content):
        called["n"] += 1
        return ["x"]

    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_3")
    trig = t1.T1Trigger()
    content = "标题 概念"
    trig._score_with_llm({"id": "it_ner_3", "title": "标题", "concepts": None})
    assert called["n"] == 0  # gate 关 → 不调 NER


def test_enrich_called_when_enabled(monkeypatch):
    _enable(monkeypatch)
    # ai_scores.hotspot_id FK → hotspots(id), 测试 item 不在 hotspots — 打分落库 no-op。
    monkeypatch.setattr(t1, "write_score", lambda *a, **kw: None)
    captured = {}
    async def fake_score(content, item_id=""):
        return 7.5
    async def fake_ents(content):
        captured["content"] = content
        return ["CVE-2026-9999"]
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "score", fake_score)
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_4")
    trig = t1.T1Trigger()
    score = trig._score_with_llm({"id": "it_ner_4", "title": "OpenAI 漏洞", "concepts": None})
    assert score == 7.5
    assert "OpenAI 漏洞" in captured["content"]
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_4",)
    ).fetchone()
    assert json.loads(row["entities"]) == ["CVE-2026-9999"]


def test_enrich_empty_entities_no_write(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(t1, "write_score", lambda *a, **kw: None)
    async def fake_score(content, item_id=""):
        return 6.0
    async def fake_ents(content):
        return []
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "score", fake_score)
    monkeypatch.setattr(llm_service, "extract_entities", fake_ents)
    _insert_item("it_ner_5")
    trig = t1.T1Trigger()
    trig._score_with_llm({"id": "it_ner_5", "title": "标题", "concepts": None})
    row = get_connection().execute(
        f"SELECT entities FROM {knowledge_items_table()} WHERE id = ?", ("it_ner_5",)
    ).fetchone()
    assert row["entities"] is None
