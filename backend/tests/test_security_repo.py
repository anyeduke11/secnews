"""SecurityRepository 单测 — 022_security_graph 迁移 + CRUD + search + synonyms."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from backend.config import config
from backend.domain.security_models import SecurityEdge, SecurityEntity, SecurityTerm
from backend.exceptions import InternalException
from backend.repository import db
from backend.repository.security_repo import SecurityRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_security.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db) -> Iterator[SecurityRepository]:
    yield SecurityRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _entity(repo, **overrides):
    defaults = {
        "id": "CVE-2024-0001",
        "entity_type": "cve",
        "name": "Test Vulnerability",
        "description": "Test desc",
        "external_ref": "https://example.com",
        "metadata": {"cvss": 7.5},
    }
    defaults.update(overrides)
    entity = SecurityEntity(**defaults)
    repo.upsert_entity(entity)
    return entity


def _term(repo, **overrides):
    defaults = {
        "canonical": "等保2.0-三级",
        "term_type": "compliance",
        "category": "security",
        "definition": "三级要求",
    }
    defaults.update(overrides)
    term = SecurityTerm(**defaults)
    repo.upsert_term(term)
    return term


# ---------------------------------------------------------------------------
# security_entities CRUD
# ---------------------------------------------------------------------------
def test_upsert_and_get_entity(repo):
    _entity(repo)
    row = repo.get_entity("CVE-2024-0001")
    assert row is not None
    assert row["id"] == "CVE-2024-0001"
    assert row["entity_type"] == "cve"
    assert row["metadata"]["cvss"] == 7.5


def test_upsert_entity_updates_existing(repo):
    _entity(repo, metadata={"cvss": 5.0})
    _entity(repo, metadata={"cvss": 9.0})
    row = repo.get_entity("CVE-2024-0001")
    assert row["metadata"]["cvss"] == 9.0


def test_list_entities_filters_by_type(repo):
    _entity(repo, entity_type="cve")
    _entity(repo, id="T1059", entity_type="technique", name="Test Technique")
    items, total = repo.list_entities(entity_type="cve")
    assert total == 1
    assert items[0]["id"] == "CVE-2024-0001"


def test_search_entities_by_name(repo):
    _entity(repo, name="Windows RCE Vulnerability")
    results = repo.search_entities("Windows")
    assert len(results) >= 1
    assert results[0]["id"] == "CVE-2024-0001"


# ---------------------------------------------------------------------------
# security_edges CRUD
# ---------------------------------------------------------------------------
def test_upsert_and_get_edges(repo):
    _entity(repo, id="T1059")
    _entity(repo, id="CVE-2024-0001")
    edge = SecurityEdge(source_id="T1059", target_id="CVE-2024-0001", edge_type="uses")
    repo.upsert_edge(edge)
    rows = repo.get_edges(entity_id="T1059")
    assert len(rows) == 1
    assert rows[0]["edge_type"] == "uses"


def test_get_edges_filters_by_type(repo):
    _entity(repo, id="T1059")
    _entity(repo, id="CVE-2024-0001")
    _entity(repo, id="T1068")
    repo.upsert_edge(SecurityEdge(source_id="T1059", target_id="CVE-2024-0001", edge_type="uses"))
    repo.upsert_edge(SecurityEdge(source_id="T1068", target_id="CVE-2024-0001", edge_type="causes"))
    rows = repo.get_edges(entity_id="CVE-2024-0001", edge_type="causes")
    assert len(rows) == 1
    assert rows[0]["source_id"] == "T1068"


# ---------------------------------------------------------------------------
# security_terms + synonyms + taxonomy
# ---------------------------------------------------------------------------
def test_upsert_and_get_term(repo):
    term = _term(repo)
    row = repo.get_term_by_canonical("等保2.0-三级")
    assert row is not None
    assert row["canonical"] == "等保2.0-三级"
    assert row["term_type"] == "compliance"


def test_add_and_get_synonyms(repo):
    term = _term(repo)
    repo.add_synonym(term.id, "等保三级")
    repo.add_synonym(term.id, "等级保护2.0-三级")
    synonyms = repo.get_synonyms(term.id)
    assert "等保三级" in synonyms
    assert "等级保护2.0-三级" in synonyms


def test_search_terms(repo):
    _term(repo)
    results = repo.search_terms("等保")
    assert len(results) >= 1
    assert results[0]["canonical"] == "等保2.0-三级"


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------
def test_invalid_entity_type_rejected(repo):
    with pytest.raises(InternalException):
        _entity(repo, entity_type="invalid_type")
