"""Data cleaning service — dedup, merge, validate knowledge items."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

log = logging.getLogger("hotspot.data_cleaning")


def url_fingerprint(url: str) -> str:
    """Generate a normalized URL fingerprint for dedup.

    Strips protocol, www, trailing slash, query params, and fragment.
    """
    import re
    url = re.sub(r"^https?://(www\.)?", "", url.lower())
    url = url.split("?")[0].split("#")[0].rstrip("/")
    return url


def item_id_from_url(url: str) -> str:
    """Generate a stable item ID from URL fingerprint."""
    fp = url_fingerprint(url)
    return hashlib.sha256(fp.encode()).hexdigest()[:12]


def merge_metadata(primary: dict, secondary: dict) -> dict:
    """Merge metadata from two sources; primary wins on conflict.

    primary: higher-priority source (e.g. Cubox)
    secondary: lower-priority source (e.g. bookmark)
    """
    merged = dict(secondary)
    merged.update({k: v for k, v in primary.items() if v is not None})
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
