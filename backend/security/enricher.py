"""Enrichment — extract security entity IDs from hotspot/knowledge items.

Re-exports SecurityGraphEngine.enrich_item / enrich_batch for convenience.
"""
from __future__ import annotations

from backend.security.graph import SecurityGraphEngine

_engine = SecurityGraphEngine()


def enrich_item(item: dict) -> dict:
    return _engine.enrich_item(item)


def enrich_batch(items: list[dict]) -> list[dict]:
    return _engine.enrich_batch(items)


__all__ = ["enrich_item", "enrich_batch"]
