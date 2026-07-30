"""Imported aggregator — 5-source knowledge imported view.

Aggregates, deduplicates, sorts, and paginates data from:
- favorites   (FavoriteRepository)
- secnews     (knowledge_repo, source='secnews')
- cubox       (knowledge_repo, source='cubox')
- bookmarks   (knowledge_repo, source='bookmark')
- secnews_archive  (knowledge_repo, source='secnews_archive')
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.repository.favorite_repo import FavoriteRepository
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.data_cleaning import url_fingerprint

log = logging.getLogger("hotspot.imported_aggregator")

# Source type → display name mapping
SOURCE_LABELS: dict[str, str] = {
    "favorites": "手动收藏",
    "cubox": "Cubox",
    "bookmark": "书签导入",
    "secnews_archive": "归档",
    "secnews": "实时",
}

# Source type → description for origin field
SOURCE_ORIGINS: dict[str, str] = {
    "favorites": "手动收藏",
    "cubox": "Cubox 同步",
    "bookmark": "书签导入",
    "secnews_archive": "SecNews 归档",
    "secnews": "SecNews 实时",
}

# Priority for dedup: lower number wins (favorites = 0 takes precedence)
SOURCE_PRIORITY: dict[str, int] = {
    "favorites": 0,
    "cubox": 1,
    "bookmark": 2,
    "secnews": 3,
    "secnews_archive": 4,
}


@dataclass
class ImportedItem:
    """Single item in the aggregated imported view."""
    id: str
    title: str
    url: str
    source_type: str  # 'favorites' | 'cubox' | 'bookmark' | 'secnews_archive' | 'secnews'
    source_name: str  # display name
    ingested_at: str  # ISO format timestamp
    origin: str       # source description


@dataclass
class ImportedResult:
    """Paginated result from the aggregator."""
    items: list[ImportedItem]
    total: int
    page: int
    page_size: int


class ImportedAggregator:
    """5-source data aggregator with dedup, sorting, and pagination."""

    def get_items(
        self,
        source_type: Optional[str] = None,
        keyword: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ImportedResult:
        """Aggregate 5 sources, dedup, sort by ingested_at DESC, paginate.

        Parameters
        ----------
        source_type : str, optional
            Filter by source type. One of: favorites, cubox, bookmark,
            secnews_archive, secnews. None = all sources.
        keyword : str, optional
            Filter by title/URL match (case-insensitive substring).
        since : str, optional
            ISO date string. Include items ingested at or after this time.
        until : str, optional
            ISO date string. Include items ingested before this time.
        page : int
            1-based page number (clamped to >= 1).
        page_size : int
            Items per page (clamped to 1..200, default 20).

        Returns
        -------
        ImportedResult
            Paginated, deduplicated, sorted results.
        """
        page = max(1, page)
        page_size = max(1, min(page_size, 200))

        # Gather all items from selected sources
        all_items: list[ImportedItem] = []
        if source_type is None or source_type == "favorites":
            all_items.extend(self._get_favorites())
        if source_type is None or source_type == "secnews":
            all_items.extend(self._get_secnews())
        if source_type is None or source_type == "cubox":
            all_items.extend(self._get_cubox())
        if source_type is None or source_type == "bookmark":
            all_items.extend(self._get_bookmarks())
        if source_type is None or source_type == "secnews_archive":
            all_items.extend(self._get_secnews_archive())

        # Apply keyword filter
        if keyword:
            kw = keyword.lower()
            all_items = [
                it for it in all_items
                if kw in it.title.lower() or kw in it.url.lower()
            ]

        # Apply time range filter
        if since:
            all_items = [it for it in all_items if it.ingested_at >= since]
        if until:
            all_items = [it for it in all_items if it.ingested_at < until]

        # Dedup by URL fingerprint: favorites priority wins
        seen: dict[str, ImportedItem] = {}
        for item in all_items:
            fp = url_fingerprint(item.url)
            if fp in seen:
                existing_priority = SOURCE_PRIORITY.get(seen[fp].source_type, 99)
                new_priority = SOURCE_PRIORITY.get(item.source_type, 99)
                if new_priority < existing_priority:
                    seen[fp] = item
            else:
                seen[fp] = item

        # Sort by ingested_at DESC
        deduped = sorted(seen.values(), key=lambda x: x.ingested_at, reverse=True)

        total = len(deduped)

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        paged = deduped[start:end]

        return ImportedResult(
            items=paged,
            total=total,
            page=page,
            page_size=page_size,
        )

    def _get_favorites(self) -> list[ImportedItem]:
        """Fetch items from FavoriteRepository."""
        items: list[ImportedItem] = []
        try:
            favorites = FavoriteRepository().list(limit=1000)
            for fav in favorites:
                items.append(ImportedItem(
                    id=f"fav_{fav.hotspot_id}",
                    title=fav.title,
                    url=fav.url,
                    source_type="favorites",
                    source_name=SOURCE_LABELS["favorites"],
                    ingested_at=fav.favorited_at,
                    origin=SOURCE_ORIGINS["favorites"],
                ))
        except Exception as e:
            log.warning("failed to fetch favorites: %s", e)
        return items

    def _get_secnews(self) -> list[ImportedItem]:
        """Fetch items from knowledge_repo where source='secnews'."""
        return self._items_from_knowledge_repo("secnews")

    def _get_cubox(self) -> list[ImportedItem]:
        """Fetch items from knowledge_repo where source='cubox'."""
        return self._items_from_knowledge_repo("cubox")

    def _get_bookmarks(self) -> list[ImportedItem]:
        """Fetch items from knowledge_repo where source='bookmark'."""
        return self._items_from_knowledge_repo("bookmark")

    def _get_secnews_archive(self) -> list[ImportedItem]:
        """Fetch items from knowledge_repo where source='secnews_archive'."""
        return self._items_from_knowledge_repo("secnews_archive")

    def _items_from_knowledge_repo(self, source: str) -> list[ImportedItem]:
        """Generic helper to convert KnowledgeItem rows to ImportedItem list."""
        items: list[ImportedItem] = []
        try:
            rows = knowledge_repo.list_items(source=source, limit=1000)
            for row in rows:
                items.append(ImportedItem(
                    id=f"{source}_{row.id}",
                    title=row.title,
                    url=row.source_url or "",
                    source_type=source,
                    source_name=SOURCE_LABELS.get(source, source),
                    ingested_at=row.ingested_at,
                    origin=SOURCE_ORIGINS.get(source, source),
                ))
        except Exception as e:
            log.warning("failed to fetch %s items: %s", source, e)
        return items