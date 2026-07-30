"""TerminologyService — security term normalization + synonym/taxonomy lookup.

Design
------
- Canonical terms are stored in security_terms + security_synonyms tables.
- normalize() uses a 4-stage pipeline: exact → synonym → regex → fuzzy.
- All operations are local SQLite, no external API calls.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Optional

from backend.repository.security_repo import SecurityRepository

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")
_ATTACK_RE = re.compile(r"T\d{4}(?:\.\d{3})?")

_log = logging.getLogger("hotspot.security.terminology")


class TerminologyService:
    """Security term normalization and search."""

    def __init__(self, repo: Optional[SecurityRepository] = None):
        self._repo = repo or SecurityRepository()

    def normalize(self, text: str) -> dict:
        """Normalize a free-text term to canonical form.

        Pipeline:
        1. Exact match on canonical → return immediately
        2. Exact match on synonym → resolve to canonical
        3. Regex extraction (CVE / ATT&CK ID) → create entity on-the-fly
        4. Fuzzy match (difflib) → best guess with confidence
        5. No match → return text as-is with match_type='none'

        Returns:
            {"canonical": str, "term_type": str, "match_type": str, "confidence": float}
        """
        text = text.strip()
        if not text:
            return {"canonical": "", "term_type": "generic", "match_type": "none", "confidence": 0.0}

        # 1. Exact match on canonical
        term = self._repo.get_term_by_canonical(text)
        if term:
            return {
                "canonical": term["canonical"],
                "term_type": term["term_type"],
                "match_type": "canonical",
                "confidence": 1.0,
            }

        # 2. Synonym lookup via security_synonyms
        # Search all terms' synonyms for a match
        all_terms = self._repo.search_terms("", limit=500)
        for t in all_terms:
            synonyms = self._repo.get_synonyms(t["id"])
            if text in synonyms:
                return {
                    "canonical": t["canonical"],
                    "term_type": t["term_type"],
                    "match_type": "synonym",
                    "confidence": 0.95,
                }

        # 3. Regex extraction
        cve_match = _CVE_RE.match(text)
        if cve_match:
            return {
                "canonical": cve_match.group(0),
                "term_type": "cve",
                "match_type": "regex",
                "confidence": 1.0,
            }
        attack_match = _ATTACK_RE.match(text)
        if attack_match:
            return {
                "canonical": attack_match.group(0),
                "term_type": "attack_technique",
                "match_type": "regex",
                "confidence": 1.0,
            }

        # 4. Fuzzy match on canonical terms
        all_canonicals = [
            t["canonical"] for t in self._repo.search_terms("", limit=500)
        ]
        if all_canonicals:
            matches = difflib.get_close_matches(text, all_canonicals, n=1, cutoff=0.6)
            if matches:
                term = self._repo.get_term_by_canonical(matches[0])
                if term:
                    return {
                        "canonical": term["canonical"],
                        "term_type": term["term_type"],
                        "match_type": "fuzzy",
                        "confidence": 0.7,
                    }

        # 5. No match
        return {
            "canonical": text,
            "term_type": "generic",
            "match_type": "none",
            "confidence": 0.0,
        }

    def get_synonyms(self, canonical: str) -> list[str]:
        """Get all synonyms for a canonical term."""
        term = self._repo.get_term_by_canonical(canonical)
        if not term:
            return []
        return self._repo.get_synonyms(term["id"])

    def search(self, query: str, term_type: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Search canonical terms."""
        return self._repo.search_terms(query, term_type=term_type, limit=limit)

    def suggest_tags(self, title: str, content: str = "") -> list[dict]:
        """Suggest security terms from title and content text."""
        text = f"{title} {content}"

        # Extract CVE IDs
        cves = list(set(_CVE_RE.findall(text)))
        # Extract ATT&CK IDs
        attacks = list(set(_ATTACK_RE.findall(text)))

        # Keyword-based compliance matching
        compliance_keywords = {
            "等保": "等保2.0-三级",
            "等级保护": "等保2.0-三级",
            "关基": "关基条例",
            "关键信息基础设施": "关基条例",
            "数据安全法": "数安法",
            "网络安全法": "网安法",
            "个人信息保护法": "个人信息保护法",
            "个保法": "个人信息保护法",
        }
        compliance_refs = []
        for kw, canonical in compliance_keywords.items():
            if kw in text:
                term = self._repo.get_term_by_canonical(canonical)
                if term:
                    compliance_refs.append(term)

        suggestions = []
        for cve in cves:
            suggestions.append({"canonical": cve, "term_type": "cve", "confidence": 1.0})
        for attack in attacks:
            suggestions.append({"canonical": attack, "term_type": "attack_technique", "confidence": 1.0})
        for c in compliance_refs:
            suggestions.append({
                "canonical": c["canonical"],
                "term_type": "compliance",
                "confidence": 0.9,
            })

        return suggestions

    def normalize_tags(self, tags: list[str]) -> list[str]:
        """Normalize a list of tags, returning canonical forms."""
        normalized = []
        for tag in tags:
            result = self.normalize(tag)
            if result["match_type"] != "none":
                normalized.append(result["canonical"])
            else:
                normalized.append(tag)
        return list(set(normalized))


__all__ = ["TerminologyService"]
