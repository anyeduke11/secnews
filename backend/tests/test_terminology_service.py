"""TerminologyService 单测 — normalize + search + suggest_tags."""
from __future__ import annotations

import pytest

from backend.config import config
from backend.domain.security_models import SecurityTerm
from backend.repository import db
from backend.repository.security_repo import SecurityRepository
from backend.services.terminology_service import TerminologyService


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "test_terminology.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db):
    return SecurityRepository()


@pytest.fixture
def svc(repo):
    t = TerminologyService(repo)
    # Seed some terms
    repo.upsert_term(SecurityTerm(
        canonical="等保2.0-三级", term_type="compliance", category="security",
        definition="三级要求",
    ))
    repo.add_synonym(1, "等保三级")
    repo.add_synonym(1, "等级保护2.0-三级")
    repo.upsert_term(SecurityTerm(
        canonical="T1059", term_type="attack_technique", category="security",
        definition="Command and Scripting Interpreter",
    ))
    repo.upsert_term(SecurityTerm(
        canonical="CVE-2024-38077", term_type="cve", category="security",
        definition="Test CVE",
    ))
    return t


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------
def test_normalize_canonical_exact(svc):
    result = svc.normalize("等保2.0-三级")
    assert result["match_type"] == "canonical"
    assert result["canonical"] == "等保2.0-三级"
    assert result["confidence"] == 1.0


def test_normalize_synonym(svc):
    result = svc.normalize("等保三级")
    assert result["match_type"] == "synonym"
    assert result["canonical"] == "等保2.0-三级"
    assert result["confidence"] == 0.95


def test_normalize_cve_regex(svc):
    result = svc.normalize("CVE-2024-99999")
    assert result["match_type"] == "regex"
    assert result["canonical"] == "CVE-2024-99999"
    assert result["term_type"] == "cve"


def test_normalize_attack_regex(svc):
    result = svc.normalize("T1059.001")
    assert result["match_type"] == "regex"
    assert result["canonical"] == "T1059.001"
    assert result["term_type"] == "attack_technique"


def test_normalize_no_match(svc):
    result = svc.normalize("未知术语")
    assert result["match_type"] == "none"
    assert result["confidence"] == 0.0


def test_normalize_empty(svc):
    result = svc.normalize("")
    assert result["match_type"] == "none"
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# get_synonyms
# ---------------------------------------------------------------------------
def test_get_synonyms(svc):
    synonyms = svc.get_synonyms("等保2.0-三级")
    assert "等保三级" in synonyms
    assert "等级保护2.0-三级" in synonyms


def test_get_synonyms_nonexistent(svc):
    assert svc.get_synonyms("nonexistent") == []


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def test_search(svc):
    results = svc.search("等保")
    assert len(results) >= 1
    assert results[0]["canonical"] == "等保2.0-三级"


def test_search_filter_by_type(svc):
    results = svc.search("T1059", term_type="attack_technique")
    assert len(results) >= 1
    assert results[0]["term_type"] == "attack_technique"


# ---------------------------------------------------------------------------
# suggest_tags
# ---------------------------------------------------------------------------
def test_suggest_tags_finds_cve(svc):
    suggestions = svc.suggest_tags("CVE-2024-38077 vulnerability", "")
    assert any(s["term_type"] == "cve" for s in suggestions)


def test_suggest_tags_finds_compliance(svc):
    suggestions = svc.suggest_tags("等保2.0 requirements", "")
    assert any(s["term_type"] == "compliance" for s in suggestions)


def test_suggest_tags_no_match(svc):
    suggestions = svc.suggest_tags("random news", "")
    assert suggestions == []


# ---------------------------------------------------------------------------
# normalize_tags
# ---------------------------------------------------------------------------
def test_normalize_tags(svc):
    result = svc.normalize_tags(["等保三级", "普通标签", "CVE-2024-0001"])
    assert "等保2.0-三级" in result
    assert "CVE-2024-0001" in result
    assert "普通标签" in result
