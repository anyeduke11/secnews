"""kl:publish stage — terminal state marking + review scheduling.

Marks the item as published and schedules a future review date
based on severity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.wiki_fs.contract import get_lifecycle

# Review intervals by severity (days).
_REVIEW_DAYS = {
    "critical": 7,
    "high": 14,
    "medium": 30,
    "low": 90,
    "info": 180,
}


def run_publish(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Mark item as published and schedule review."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    if get_lifecycle(fm) != "kl:structure":
        logger.info(f"publish: skipping {item_id} (stage={get_lifecycle(fm)})")
        return

    severity = fm.get("severity", "info")
    review_days = _REVIEW_DAYS.get(severity, 180)
    review_at = datetime.now(timezone.utc) + timedelta(days=review_days)

    fm["lifecycle"] = "kl:publish"
    fm["published_at"] = datetime.now(timezone.utc).isoformat()
    fm["review_at"] = review_at.isoformat()
    wiki_fs.write_item(item_id, {"fm": fm, "body": doc.get("body", "")})

    logger.info(f"published {item_id} (review in {review_days}d)")
