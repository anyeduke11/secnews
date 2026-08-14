"""SecurityGraphEngine + enricher 单测."""
from __future__ import annotations

import json

import pytest

from backend.config import config
from backend.domain.security_models import SecurityEntity
from backend.repository import db
from backend.repository.security_repo import SecurityRepository
from backend.security.enricher import enrich_item
from backend.security.graph import _ATTACK_RE, _CVE_RE, SecurityGraphEngine


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test_security_graph.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db):
    return SecurityRepository()


@pytest.fixture
def engine(repo):
    return SecurityGraphEngine(repo)


# ---------------------------------------------------------------------------
# Regex extraction
# ---------------------------------------------------------------------------
def test_cve_regex():
    assert _CVE_RE.findall("CVE-2024-38077") == ["CVE-2024-38077"]
    assert _CVE_RE.findall("CVE-2024-0001 and CVE-2024-0002") == ["CVE-2024-0001", "CVE-2024-0002"]
    assert _CVE_RE.findall("no match here") == []


def test_attack_regex():
    assert _ATTACK_RE.findall("T1059") == ["T1059"]
    assert _ATTACK_RE.findall("T1059.001") == ["T1059.001"]
    assert _ATTACK_RE.findall("no match") == []


# ---------------------------------------------------------------------------
# enrich_item
# ---------------------------------------------------------------------------
def test_enrich_item_finds_cve():
    item = {"id": "test-1", "title": "CVE-2024-38077 Windows RCE", "summary": ""}
    result = enrich_item(item)
    assert "cve_ids" in result
    assert "CVE-2024-38077" in result["cve_ids"]


def test_enrich_item_finds_attack():
    item = {"id": "test-2", "title": "T1059.001 execution technique", "summary": ""}
    result = enrich_item(item)
    assert "attack_techniques" in result
    assert "T1059.001" in result["attack_techniques"]


def test_enrich_item_finds_compliance():
    item = {"id": "test-3", "title": "等保2.0-三级要求", "summary": "关键信息基础设施安全保护"}
    result = enrich_item(item)
    assert "compliance_refs" in result
    data = json.loads(result["compliance_refs"])
    assert "等保" in data or "等保2.0-三级" in data


def test_enrich_item_empty_item():
    item = {"id": "test-4", "title": "无关内容", "summary": ""}
    result = enrich_item(item)
    assert result == {}


# ---------------------------------------------------------------------------
# build_security_graph
# ---------------------------------------------------------------------------
def test_build_graph_empty_returns_stats(engine):
    result = engine.build_security_graph("full")
    assert "nodes" in result
    assert "edges" in result
    assert "stats" in result
    assert result["stats"]["techniques"] == 0


def test_build_graph_attack_view(engine, repo):
    repo.upsert_entity(SecurityEntity(
        id="T1059", entity_type="technique", name="Command and Scripting Interpreter",
    ))
    result = engine.build_security_graph("attack")
    assert result["stats"]["techniques"] == 1
    assert len(result["nodes"]) == 1


def test_build_graph_views_are_distinct(engine, repo):
    repo.upsert_entity(SecurityEntity(
        id="T1059", entity_type="technique", name="Test Technique",
    ))
    repo.upsert_entity(SecurityEntity(
        id="等保2.0-三级", entity_type="compliance", name="等保三级",
    ))
    attack = engine.build_security_graph("attack")
    compliance = engine.build_security_graph("compliance")
    assert attack["stats"]["techniques"] == 1
    assert attack["stats"]["compliance_items"] == 0
    assert compliance["stats"]["compliance_items"] == 1
    assert compliance["stats"]["techniques"] == 0


# ---------------------------------------------------------------------------
# enrich_batch
# ---------------------------------------------------------------------------
def test_enrich_batch_returns_enriched_only(engine):
    items = [
        {"id": "1", "title": "CVE-2024-0001 test", "summary": ""},
        {"id": "2", "title": "normal news", "summary": ""},
    ]
    enriched = engine.enrich_batch(items)
    assert len(enriched) == 1
    assert enriched[0]["id"] == "1"
