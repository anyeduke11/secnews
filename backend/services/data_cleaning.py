"""Data cleaning service — dedup, merge, validate knowledge items."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

log = logging.getLogger("hotspot.data_cleaning")


def url_fingerprint(url: str) -> str:
    """Generate a normalized URL fingerprint for dedup.

    Strips protocol, www, trailing slash, query params, and fragment.
    """
    url = re.sub(r"^https?://(www\.)?", "", url.lower())
    url = url.split("?")[0].split("#")[0].rstrip("/")
    return url


def item_id_from_url(url: str) -> str:
    """Generate a stable item ID from URL fingerprint."""
    fp = url_fingerprint(url)
    return hashlib.sha256(fp.encode()).hexdigest()[:12]


def simhash(text: str) -> int:
    """Generate a 64-bit SimHash fingerprint for a URL/text.

    Tokenizes by ``/ ? & = . - _`` (lowercased), then for each token
    computes an md5 hash and accumulates per-bit weights (+1 for bit=1,
    -1 for bit=0). Final fingerprint sets bit=1 where weight > 0.
    """
    tokens = re.split(r"[/?&=\.\-_]", text.lower())
    tokens = [t for t in tokens if t]
    if not tokens:
        return 0

    weights = [0] * 64
    for token in tokens:
        h = hashlib.md5(token.encode()).digest()
        hash_int = int.from_bytes(h[:8], "big")
        for i in range(64):
            if hash_int & (1 << i):
                weights[i] += 1
            else:
                weights[i] -= 1

    fingerprint = 0
    for i in range(64):
        if weights[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(h1: int, h2: int) -> int:
    """Compute Hamming distance between two 64-bit hashes."""
    return bin(h1 ^ h2).count("1")


def find_similar_items(url: str, threshold: int = 6) -> list[str]:
    """Find existing knowledge items with similar URLs.

    Returns list of item IDs whose source_url SimHash Hamming distance
    to *url* is ≤ *threshold* (≈90% similarity for 64-bit).
    """
    from backend.repository.knowledge_repo import knowledge_repo

    target_hash = simhash(url)
    similar: list[str] = []
    items = knowledge_repo.list_items(limit=10000)
    for item in items:
        if not item.source_url:
            continue
        item_hash = simhash(item.source_url)
        if hamming_distance(target_hash, item_hash) <= threshold:
            similar.append(item.id)
    return similar


def merge_metadata(primary: dict, secondary: dict) -> dict:
    """Merge metadata from two sources; primary wins on conflict.

    primary: higher-priority source (e.g. Cubox)
    secondary: lower-priority source (e.g. bookmark)

    Special handling:
    - ``sources``: list union (accumulate from both)
    - ``tags``: list union (accumulate from both)
    - Other fields: primary overrides secondary (skip None)
    """
    merged = dict(secondary)
    for k, v in primary.items():
        if v is None:
            continue
        if k in ("sources", "tags"):
            continue  # handled separately
        merged[k] = v

    # sources: list union
    ps = primary.get("sources") or []
    ss = secondary.get("sources") or []
    if ps or ss:
        merged["sources"] = list(dict.fromkeys(ss + ps))

    # tags: list union
    pt = primary.get("tags") or []
    st = secondary.get("tags") or []
    if pt or st:
        merged["tags"] = list(dict.fromkeys(st + pt))
    return merged


def validate_url(url: str, timeout: int = 5) -> bool:
    """Check if URL is reachable via proxy.

    Returns True if reachable, False otherwise.
    """
    import requests
    from backend.config import config
    try:
        proxies = None
        if config.proxy_mode == "manual":
            proxies = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
        resp = requests.head(url, timeout=timeout, proxies=proxies, allow_redirects=True)
        return resp.status_code < 500
    except Exception:
        return False


def clean_and_dedupe(items: list[dict]) -> list[dict]:
    """Deduplicate items by URL fingerprint, merge metadata.

    items: list of dicts with at least 'url' and 'title'
    Returns: deduplicated list
    """
    seen: dict[str, dict] = {}
    for item in items:
        fp = url_fingerprint(item.get("url", ""))
        item["id"] = item_id_from_url(item["url"])
        if fp in seen:
            seen[fp] = merge_metadata(seen[fp], item)
        else:
            seen[fp] = item
    return list(seen.values())
