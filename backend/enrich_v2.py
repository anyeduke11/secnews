"""enrich_v2 — security entity extraction (CVE / ATT&CK / compliance / deadline).

Standalone regex-based extractor for security-relevant entities.
Designed to augment the existing enrich pipeline with structured data.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
CVE_PATTERN = r'CVE-\d{4}-\d{4,7}'
ATTACK_PATTERN = r'\bT\d{4}(?:\.\d{3})?\b'
COMPLIANCE_PATTERN = r'等保|关基|数据安全法|网络安全法|等级保护|GB/T|ISO 27001|SOC 2'
DEADLINE_PATTERN = r'(?:截止|到期|deadline)[^：:\d]{0,10}[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})'
BID_STATUS_PATTERN = r'(?:招标|中标|成交|变更|终止|询价|比选)'

# Compiled versions for performance.
_RE_CVE = re.compile(CVE_PATTERN)
_RE_ATTACK = re.compile(ATTACK_PATTERN)
_RE_COMPLIANCE = re.compile(COMPLIANCE_PATTERN)
_RE_DEADLINE = re.compile(DEADLINE_PATTERN)
_RE_BID_STATUS = re.compile(BID_STATUS_PATTERN)

# ATT&CK context guard — only match T-IDs near security keywords.
_ATTACK_CONTEXT = re.compile(
    r'(?:MITRE|ATT&CK|attack|technique|tactic|sub-technique|'
    r'phishing|lateral|persistence|execution|exfiltration)',
    re.IGNORECASE,
)


def extract_cve(text: str) -> list[str]:
    """Extract all CVE IDs from text."""
    return list(set(_RE_CVE.findall(text)))


def extract_attack(text: str) -> list[str]:
    """Extract MITRE ATT&CK technique IDs with context guard.

    Only returns T-IDs that appear within 200 chars of an ATT&CK
    context keyword, reducing false positives from unrelated T-numbers.
    """
    results: list[str] = []
    for m in _RE_ATTACK.finditer(text):
        start = max(0, m.start() - 200)
        end = min(len(text), m.end() + 200)
        context = text[start:end]
        if _ATTACK_CONTEXT.search(context):
            results.append(m.group())
    return list(set(results))


def extract_compliance(text: str) -> list[str]:
    """Extract compliance framework mentions."""
    return list(set(_RE_COMPLIANCE.findall(text)))


def extract_deadline(text: str) -> list[str]:
    """Extract deadline dates from structured patterns."""
    return _RE_DEADLINE.findall(text)


def extract_bid_status(text: str) -> list[str]:
    """Extract procurement status keywords."""
    return list(set(_RE_BID_STATUS.findall(text)))


def extract_all(title: str = "", summary: str = "", body: str = "") -> dict[str, Any]:
    """Run all extractors on combined text. Returns structured result."""
    combined = f"{title}\n{summary}\n{body}"
    return {
        "cve_ids": extract_cve(combined),
        "attack_ids": extract_attack(combined),
        "compliance": extract_compliance(combined),
        "deadlines": extract_deadline(combined),
        "bid_status": extract_bid_status(combined),
    }
