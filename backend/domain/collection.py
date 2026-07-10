"""Collector run/result models used by the collection layer.

Three models, all Pydantic v2:

- ``SourceResult``     per-source outcome (one entry per configured source)
- ``CollectionResult`` per-category outcome (one per ``Category``)
- ``CollectionReport`` whole-run aggregate (one per ``run_once()`` call)

Plus Phase 3.5 quality-gate models:

- ``GateResult``       per-gate outcome (one per ``BaseGate.check()``)
- ``PipelineResult``   aggregate of all gates that ran for a single item

Datetime convention: all ``datetime`` fields MUST be tz-aware UTC
(``datetime.now(timezone.utc)``). This matches the convention in
``backend.domain.models`` and is enforced there by a validator; the
models here are passed-in values, so callers are expected to construct
them with aware datetimes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.domain.enums import Category


class SourceResult(BaseModel):
    """Outcome of fetching a single source.

    Fields
    ------
    source_name:
        Short identifier of the source (matches the ``name`` field on the
        source config dict passed to ``BaseCollector.fetch_source``).
    source_url:
        The URL that was requested.
    item_count:
        How many ``HotspotItem`` records were produced from this source.
        ``0`` on failure or empty page.
    fallback_used:
        True if the source required a fallback (e.g. the request failed
        and we returned a hard-coded item). Currently informational;
        the per-item ``is_fallback`` flag is the authoritative signal.
    error_msg:
        Short human-readable error description, ``None`` on success.
    duration_ms:
        Wall-clock time spent on this source, in milliseconds.
    """

    source_name: str
    source_url: str
    item_count: int = 0
    fallback_used: bool = False
    error_msg: Optional[str] = None
    duration_ms: int = 0


class CollectionResult(BaseModel):
    """Outcome of collecting a single category.

    ``items`` holds ``HotspotItem`` objects (not pre-serialised dicts) so
    that ``CollectionService.run_once`` can pass them straight to
    ``HotspotRepository.upsert_many``. When the result is serialised to
    JSON (e.g. for log records or API responses), Pydantic's nested
    model support will convert each ``HotspotItem`` to a dict via
    ``model_dump(mode="json")`` automatically.
    """

    category: Category
    items: list = Field(default_factory=list)  # list[HotspotItem]
    item_count: int = 0
    fallback_count: int = 0
    source_results: list[SourceResult] = Field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0
    started_at: datetime
    finished_at: Optional[datetime] = None


class CollectionReport(BaseModel):
    """Aggregate report returned by ``CollectionService.run_once``.

    ``results`` is one ``CollectionResult`` per category attempted.
    ``failures`` is a compact ``{"category": <str>, "error": <str>}``
    list suitable for log lines / API responses.
    """

    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    fallback_count: int = 0
    duration_ms: int = 0
    started_at: datetime
    finished_at: Optional[datetime] = None
    failures: list[dict[str, str]] = Field(default_factory=list)
    results: list[CollectionResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 3.5 — Quality gate models
# ---------------------------------------------------------------------------
class GateResult(BaseModel):
    """Outcome of a single ``BaseGate.check()`` call.

    Fields
    ------
    gate_name:
        Identifier of the gate that produced this result (matches
        ``BaseGate.name``).
    passed:
        True if the gate considered the item acceptable. False means
        the gate deducted points or set flags but the pipeline may
        still keep the item in loose mode.
    score_deduction:
        How many points to subtract from the item's base 100 score.
        Capped by the gate (e.g. schema gate uses 100, others use
        15-50).
    flags:
        List of symbolic flag strings describing what was wrong (e.g.
        ``["title_too_short", "spam_keyword"]``). Stored in
        ``hotspots.quality_flags`` JSON column.
    reason:
        Human-readable explanation. Logged / shown in /api/quality/logs.
    error_msg:
        Set when the gate itself crashed. The check is treated as a
        "skip" (no flag, no deduction) and surfaced in logs.
    """

    model_config = {"arbitrary_types_allowed": True}

    gate_name: str
    passed: bool = True
    score_deduction: int = 0
    flags: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    error_msg: Optional[str] = None


class PipelineResult(BaseModel):
    """Aggregate of all gate results for a single item.

    Returned by ``QualityGatePipeline.run_all``. Used by callers to
    update the item's ``quality_score`` / ``quality_flags`` /
    ``quality_checked_at`` fields, and to decide whether to accept /
    reject the item under strict mode.
    """

    model_config = {"arbitrary_types_allowed": True}

    item_id: str
    gate_results: list[GateResult] = Field(default_factory=list)
    final_score: int = 100
    final_flags: list[str] = Field(default_factory=list)
    accepted: bool = True
    mode: str = "loose"
    reason: Optional[str] = None


__all__ = [
    "SourceResult",
    "CollectionResult",
    "CollectionReport",
    "GateResult",
    "PipelineResult",
]
