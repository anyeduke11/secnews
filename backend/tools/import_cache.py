"""One-shot migration tool: import the legacy ``cache_data.json`` snapshot.

Phase-2 / Task-8 utility. Reads the historical ``cache_data.json`` produced
by the pre-schema collectors and bulk-loads every entry into the new
``hotspots`` table, tagging each row with ``is_fallback=True`` and a
``legacy_import`` quality flag so downstream consumers can distinguish
legacy data from real, freshly-collected entries.

The script is idempotent — re-running on the same file updates rows in
place via the repository's ``ON CONFLICT DO UPDATE`` upsert rather than
failing on duplicate ``id`` values.

Run from the project root::

    python -m backend.tools.import_cache            # default path
    python -m backend.tools.import_cache path/to/other.json

Key invariants
--------------
* The cache file is **backed up before any DB write** (so a failed import
  leaves the legacy JSON intact at ``<name>.bak.<YYYYMMDDHHMMSS>.json``).
* Item-level failures (bad category, invalid URL, malformed timestamp)
  are caught and counted in ``skipped_count``; they never abort the run.
* No ``print`` is used inside the library code path — all observability
  goes through the loguru ``logger``.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import InvalidParamException
from backend.logging_config import logger
from backend.repository.hotspot_repo import HotspotRepository


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Placeholder used when a legacy row has no URL — keeps HotspotItem
# validation happy (HttpUrl cannot be empty) without inventing a real
# link. Rows whose stored URL is non-empty but malformed are caught by
# the ValidationError branch below and counted in skipped_count.
_PLACEHOLDER_URL = "https://example.com/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_iso(s: str | None) -> datetime:
    """Parse an ISO 8601 string into a tz-aware UTC ``datetime``.

    Returns ``datetime.now(timezone.utc)`` on falsy input, on a
    ``ValueError`` (malformed string, including legacy unix-timestamp
    numerics like ``"1783147728"``) or on a ``TypeError``. The import
    flow must never abort on a single bad timestamp.
    """
    if not s:
        return datetime.now(timezone.utc)
    try:
        # ``datetime.fromisoformat()`` did not accept the trailing ``Z``
        # until Python 3.11; normalise to an explicit UTC offset to be
        # portable across all supported runtimes.
        normalised = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the items list regardless of legacy / new envelope.

    * Legacy envelope: ``{"timestamp": ..., "payload": {"items": [...]}}``
    * New envelope:    ``{"items": [...]}``
    * Missing key:     ``[]``
    """
    if "payload" in payload and isinstance(payload["payload"], dict):
        items = payload["payload"].get("items")
        if isinstance(items, list):
            return items
        return []
    if "items" in payload and isinstance(payload["items"], list):
        return payload["items"]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def import_from_cache_json(path: Path) -> dict[str, Any]:
    """Backup the cache file, then import every item into the DB.

    Returns a dict with ``imported_count``, ``skipped_count``,
    ``error_count`` and ``backup_path``. Item-level failures are
    logged and counted; only the JSON-read failure path or the
    bulk-upsert failure path can short-circuit the call early.
    """
    path = Path(path)

    # ------------------------------------------------------------------
    # 1. Backup — must happen before any DB write.
    # ------------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = path.parent / f"{path.stem}.bak.{timestamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    logger.info(
        "cache backup created",
        extra={"trace_id": "", "backup_path": str(backup_path)},
    )

    # ------------------------------------------------------------------
    # 2. Load JSON.
    # ------------------------------------------------------------------
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error(
            "cache json load failed",
            extra={"trace_id": "", "path": str(path), "error": str(e)},
        )
        return {
            "imported_count": 0,
            "skipped_count": 0,
            "error_count": 1,
            "backup_path": str(backup_path),
        }

    raw_items = _extract_items(data if isinstance(data, dict) else {})
    logger.info(
        "cache items extracted",
        extra={"trace_id": "", "path": str(path), "raw_count": len(raw_items)},
    )

    # ------------------------------------------------------------------
    # 3. Convert each item to a HotspotItem, collecting failures.
    # ------------------------------------------------------------------
    now_dt = datetime.now(timezone.utc)
    imported: list[HotspotItem] = []
    skipped: list[Any] = []
    error_count = 0

    for raw in raw_items:
        if not isinstance(raw, dict):
            skipped.append(raw)
            error_count += 1
            logger.warning(
                "cache item skipped: not a dict",
                extra={"trace_id": "", "raw": str(raw)[:200]},
            )
            continue

        # Category — fall back to InvalidParamException via from_str.
        try:
            cat = Category.from_str(raw.get("category", "general"))
        except InvalidParamException as e:
            skipped.append(raw)
            error_count += 1
            logger.warning(
                "cache item skipped: bad category",
                extra={"trace_id": "", "id": raw.get("id"), "error": str(e)},
            )
            continue

        # Timestamps — legacy uses ``publishedAt`` (camelCase); newer
        # snapshots may use ``published_at``. Some fin_sina_* rows
        # store a bare unix-timestamp string, which parse_iso() rejects
        # and falls back to now_dt.
        pub_raw = raw.get("publishedAt") or raw.get("published_at")
        pub_dt = parse_iso(pub_raw) if pub_raw else now_dt

        # URL — empty / missing → placeholder; explicit malformed value
        # is caught by HotspotItem validation below and skipped.
        url_raw = raw.get("url") or _PLACEHOLDER_URL

        try:
            item = HotspotItem(
                id=str(raw.get("id", ""))[:200],
                title=str(raw.get("title", ""))[:500],
                summary=(
                    str(raw.get("summary") or "")[:500]
                    if raw.get("summary")
                    else None
                ),
                source=str(raw.get("source", "unknown"))[:50],
                url=url_raw,
                category=cat,
                published_at=pub_dt,
                score=0,
                fetched_at=now_dt,
                is_fallback=True,
                quality_score=50,
                quality_flags=["legacy_import"],
                url_check_status="skipped",
                # Phase 15: legacy import 的录入时间用 published_at,
                # 让历史老资讯按发布时间显示在历史位置
                ingested_at=pub_dt,
            )
        except (ValidationError, ValueError, TypeError) as e:
            skipped.append(raw)
            error_count += 1
            logger.warning(
                "cache item skipped: validation error",
                extra={"trace_id": "", "id": raw.get("id"), "error": str(e)},
            )
            continue

        imported.append(item)

    # ------------------------------------------------------------------
    # 4. Bulk upsert. Idempotent — re-runs update in place.
    # ------------------------------------------------------------------
    if imported:
        try:
            affected = HotspotRepository().upsert_many(imported)
        except Exception as e:
            logger.error(
                "cache import upsert failed",
                extra={
                    "trace_id": "",
                    "imported": len(imported),
                    "skipped": len(skipped),
                    "error": str(e),
                },
            )
            return {
                "imported_count": 0,
                "skipped_count": len(skipped),
                "error_count": error_count + 1,
                "backup_path": str(backup_path),
            }
        logger.info(
            "imported N items, all marked as fallback",
            extra={
                "trace_id": "",
                "imported": len(imported),
                "skipped": len(skipped),
                "affected": affected,
            },
        )
    else:
        logger.warning(
            "cache import found no items to upsert",
            extra={"trace_id": "", "skipped": len(skipped)},
        )

    return {
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "error_count": error_count,
        "backup_path": str(backup_path),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    """``python -m backend.tools.import_cache [path]``"""
    import sys

    from backend.logging_config import setup
    from backend.repository.db import init_db

    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(__file__).resolve().parent.parent / "cache_data.json"

    setup()
    init_db()
    result = import_from_cache_json(target)
    print(f"导入完成: {result}")


__all__ = ["import_from_cache_json", "parse_iso"]
