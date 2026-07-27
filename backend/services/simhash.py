"""Simhash 64-bit fingerprint + Hamming distance + URL/title normalization.

Designed for Phase 8 deduplication — pure functions, no I/O, no third-party deps.

Functions
---------
- simhash — compute 64-bit simhash fingerprint from text
- hamming_distance — count differing bits between two fingerprints
- canonicalize_url — normalize URL for dedup key
- normalize_title — normalize title for dedup key
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# FNV-1a 64-bit constants
# ---------------------------------------------------------------------------
_FNV_OFFSET_BASIS = 14695981039346656037
_FNV_PRIME = 1099511628211
_FNV_MASK = 0xFFFFFFFFFFFFFFFF


def _fnv1a_64(data: bytes) -> int:
    """Compute FNV-1a 64-bit hash of *data* (deterministic, pure Python)."""
    h = _FNV_OFFSET_BASIS
    for byte in data:
        h ^= byte
        h = (h * _FNV_PRIME) & _FNV_MASK
    return h


# ---------------------------------------------------------------------------
# Simhash
# ---------------------------------------------------------------------------

# Regex: split on runs of non-alphanumeric, non-CJK, non-underscore characters.
# Keeps Chinese characters, letters, digits, and underscores as tokens.
_TOKEN_SPLIT_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def simhash(text: str) -> int:
    """Compute a 64-bit simhash fingerprint for *text*.

    Uses FNV-1a 64-bit as the per-token hash.  Each token is weighted by
    its frequency (term count).  Short texts (< 2 tokens) fall back to the
    FNV-1a hash of the entire text so that single-word inputs still produce
    a meaningful fingerprint.
    """
    if not text or not text.strip():
        return 0

    tokens = _TOKEN_SPLIT_RE.split(text.strip().lower())
    tokens = [t for t in tokens if t]

    if len(tokens) < 2:
        return _fnv1a_64(text.strip().lower().encode("utf-8"))

    # Weighted accumulator: 64-bit signed integer array
    v = [0] * 64

    for token in tokens:
        h = _fnv1a_64(token.encode("utf-8"))
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return fingerprint


# ---------------------------------------------------------------------------
# Hamming distance
# ---------------------------------------------------------------------------

def hamming_distance(a: int, b: int) -> int:
    """Count the number of differing bits between two 64-bit integers.

    Uses the built-in ``bit_count`` (Python 3.8+ ``int.bit_count``)
    for a fast population-count.
    """
    return (a ^ b).bit_count()


# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = re.compile(
    r"^(utm_source|utm_medium|utm_campaign|utm_term|utm_content|"
    r"fbclid|gclid|gclsrc|dclid|msclkid|"
    r"source|si|mc_cid|mc_eid|"
    r"_ga|_gl|_hsenc|_hsmi)$",
    re.IGNORECASE,
)


def canonicalize_url(url: str) -> str:
    """Normalize a URL for use as a deduplication key.

    Steps
    -----
    1. Lowercase the domain (netloc)
    2. Unify protocol to ``https://``
    3. Strip tracking query parameters
    4. Remove fragment (hash)
    5. Remove trailing slash from the path
    """
    if not url or not url.strip():
        return ""

    url = url.strip()

    parsed = urlparse(url)

    # Lowercase domain
    netloc = parsed.netloc.lower()

    # Unify protocol to https
    scheme = "https"

    # Strip tracking params
    query_parts = []
    if parsed.query:
        for param in parsed.query.split("&"):
            param = param.strip()
            if not param:
                continue
            key = param.split("=", 1)[0]
            if _TRACKING_PARAMS.match(key):
                continue
            query_parts.append(param)
    query = "&".join(query_parts)

    # Remove fragment
    fragment = ""

    # Remove trailing slash from path
    path = parsed.path.rstrip("/")
    if not path:
        path = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


# ---------------------------------------------------------------------------
# Title normalization
# ---------------------------------------------------------------------------

# Keep Chinese characters, letters, digits, and whitespace; remove punctuation
_TITLE_CLEAN_RE = re.compile(r"[^\w\u4e00-\u9fff\s]")


def normalize_title(title: str) -> str:
    """Normalize a title for deduplication comparison.

    Steps
    -----
    1. Lowercase
    2. Remove punctuation (keep CJK, letters, digits, whitespace)
    3. Strip leading/trailing whitespace
    4. Collapse runs of whitespace into a single space
    """
    if not title or not title.strip():
        return ""

    s = title.strip().lower()
    s = _TITLE_CLEAN_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s