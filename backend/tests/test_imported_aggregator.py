"""Tests for ImportedAggregator — 5-source merge, dedup, sort, pagination.

All data sources are mocked; no real DB or file I/O.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.domain.knowledge_models import KnowledgeItem
from backend.repository.favorite_repo import FavoriteItem


# ---------------------------------------------------------------------------
# Helpers: factory functions
# ---------------------------------------------------------------------------
def _make_fav(
    hotspot_id: str,
    title: str,
    url: str,
    favorited_at: str,
    category: str = "ai",
) -> FavoriteItem:
    return FavoriteItem(
        id=hash(hotspot_id) % 10**6,
        hotspot_id=hotspot_id,
        category=category,
        title=title,
        source="test_source",
        url=url,
        favorited_at=favorited_at,
        created_via="ui",
    )


def _make_ki(
    item_id: str,
    title: str,
    url: str,
    ingested_at: str,
    source: str = "secnews",
) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        title=title,
        source=source,
        source_url=url,
        ingested_at=ingested_at,
        updated_at=ingested_at,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def aggregator():
    from backend.services.imported_aggregator import ImportedAggregator
    return ImportedAggregator()


# ---------------------------------------------------------------------------
# Test 1: 5-source merge produces correct counts
# ---------------------------------------------------------------------------
def test_merge_all_sources(aggregator, monkeypatch):
    """All 5 sources should be merged into a single result set."""
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(
            list=lambda limit=200: [
                _make_fav("h1", "Fav A", "https://a.com", "2026-07-01T00:00:00"),
            ]
        ),
    )

    def _mock_list_items(source="secnews", limit=50, offset=0):
        if source == "secnews":
            return [_make_ki("s1", "SecNews B", "https://b.com", "2026-07-02T00:00:00", source="secnews")]
        if source == "cubox":
            return [_make_ki("c1", "Cubox C", "https://c.com", "2026-07-03T00:00:00", source="cubox")]
        if source == "bookmark":
            return [_make_ki("b1", "Bookmark D", "https://d.com", "2026-07-04T00:00:00", source="bookmark")]
        if source == "secnews_archive":
            return [_make_ki("a1", "Archive E", "https://e.com", "2026-07-05T00:00:00", source="secnews_archive")]
        return []

    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=_mock_list_items),
    )

    result = aggregator.get_items()
    assert result.total == 5, f"expected 5 total, got {result.total}"
    assert len(result.items) == 5
    # All source types should be represented
    types = {it.source_type for it in result.items}
    assert types == {"favorites", "secnews", "cubox", "bookmark", "secnews_archive"}


# ---------------------------------------------------------------------------
# Test 2: URL dedup — favorites priority wins
# ---------------------------------------------------------------------------
def test_dedup_favorites_priority(aggregator, monkeypatch):
    """Same URL from multiple sources: favorites should be retained."""
    common_url = "https://example.com/article"

    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(
            list=lambda limit=200: [
                _make_fav("h1", "Fav Title", common_url, "2026-07-01T00:00:00"),
            ]
        ),
    )

    def _mock_list_items(source="secnews", limit=50, offset=0):
        return [
            _make_ki("k1", "SecNews Title", common_url, "2026-07-02T00:00:00",
                     source="secnews" if source == "secnews" else source),
        ]

    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=_mock_list_items),
    )

    result = aggregator.get_items()
    assert result.total == 1, f"expected 1 deduped item, got {result.total}"
    assert result.items[0].source_type == "favorites"
    assert result.items[0].title == "Fav Title"


# ---------------------------------------------------------------------------
# Test 3: Pagination
# ---------------------------------------------------------------------------
def test_pagination(aggregator, monkeypatch):
    """Pagination should return correct slices and total."""
    favs = [_make_fav(f"h{i}", f"Fav {i}", f"https://a{i}.com",
                       f"2026-07-{i+1:02d}T00:00:00") for i in range(5)]

    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(list=lambda limit=200: favs),
    )
    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=lambda source="secnews", limit=50, offset=0: []),
    )

    # Page 1 (page_size=2)
    r1 = aggregator.get_items(page=1, page_size=2)
    assert r1.total == 5
    assert len(r1.items) == 2
    assert r1.page == 1
    assert r1.page_size == 2

    # Page 3 (page_size=2) — last page with 1 item
    r3 = aggregator.get_items(page=3, page_size=2)
    assert r3.total == 5
    assert len(r3.items) == 1
    assert r3.page == 3

    # Page beyond total — empty
    r4 = aggregator.get_items(page=10, page_size=2)
    assert r4.total == 5
    assert len(r4.items) == 0


# ---------------------------------------------------------------------------
# Test 4: Keyword filter
# ---------------------------------------------------------------------------
def test_keyword_filter(aggregator, monkeypatch):
    """Keyword filter should match title and URL."""
    items = [
        _make_fav("h1", "Alpha Release", "https://alpha.com", "2026-07-01T00:00:00"),
        _make_fav("h2", "Beta Launch", "https://beta.com", "2026-07-02T00:00:00"),
    ]
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(list=lambda limit=200: items),
    )
    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=lambda source="secnews", limit=50, offset=0: []),
    )

    # Match by title
    r1 = aggregator.get_items(keyword="alpha")
    assert r1.total == 1
    assert r1.items[0].title == "Alpha Release"

    # Match by URL
    r2 = aggregator.get_items(keyword="beta.com")
    assert r2.total == 1
    assert r2.items[0].title == "Beta Launch"

    # No match
    r3 = aggregator.get_items(keyword="nonexistent")
    assert r3.total == 0


# ---------------------------------------------------------------------------
# Test 5: Source type filter
# ---------------------------------------------------------------------------
def test_source_type_filter(aggregator, monkeypatch):
    """Filter by source_type should return only matching items."""
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(
            list=lambda limit=200: [
                _make_fav("h1", "Fav A", "https://a.com", "2026-07-01T00:00:00"),
            ]
        ),
    )

    def _mock_list_items(source="secnews", limit=50, offset=0):
        if source == "cubox":
            return [_make_ki("c1", "Cubox B", "https://b.com", "2026-07-02T00:00:00", source="cubox")]
        return []

    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=_mock_list_items),
    )

    # Only cubox
    r_cubox = aggregator.get_items(source_type="cubox")
    assert r_cubox.total == 1
    assert r_cubox.items[0].source_type == "cubox"

    # Only favorites
    r_fav = aggregator.get_items(source_type="favorites")
    assert r_fav.total == 1
    assert r_fav.items[0].source_type == "favorites"


# ---------------------------------------------------------------------------
# Test 6: Time range filter
# ---------------------------------------------------------------------------
def test_time_range_filter(aggregator, monkeypatch):
    """since/until should filter by ingested_at."""
    items = [
        _make_fav("h1", "Early", "https://a.com", "2026-07-01T00:00:00"),
        _make_fav("h2", "Middle", "https://b.com", "2026-07-15T00:00:00"),
        _make_fav("h3", "Late", "https://c.com", "2026-07-20T00:00:00"),
    ]
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(list=lambda limit=200: items),
    )
    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=lambda source="secnews", limit=50, offset=0: []),
    )

    # since only
    r1 = aggregator.get_items(since="2026-07-15T00:00:00")
    assert r1.total == 2
    assert {it.title for it in r1.items} == {"Middle", "Late"}

    # until only
    r2 = aggregator.get_items(until="2026-07-15T00:00:00")
    assert r2.total == 1
    assert r2.items[0].title == "Early"

    # both
    r3 = aggregator.get_items(since="2026-07-10T00:00:00",
                               until="2026-07-18T00:00:00")
    assert r3.total == 1
    assert r3.items[0].title == "Middle"


# ---------------------------------------------------------------------------
# Test 7: Empty result
# ---------------------------------------------------------------------------
def test_empty_result(aggregator, monkeypatch):
    """When all sources are empty, result should be empty with correct shape."""
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(list=lambda limit=200: []),
    )
    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=lambda source="secnews", limit=50, offset=0: []),
    )

    result = aggregator.get_items()
    assert result.total == 0
    assert result.items == []
    assert result.page == 1
    assert result.page_size == 20


# ---------------------------------------------------------------------------
# Test 8: Edge cases — page_size=1, page=0
# ---------------------------------------------------------------------------
def test_edge_cases(aggregator, monkeypatch):
    """Edge cases: page_size=1, page=0 should be handled gracefully."""
    items = [
        _make_fav("h1", "First", "https://a.com", "2026-07-01T00:00:00"),
        _make_fav("h2", "Second", "https://b.com", "2026-07-02T00:00:00"),
    ]
    monkeypatch.setattr(
        "backend.services.imported_aggregator.FavoriteRepository",
        lambda: MagicMock(list=lambda limit=200: items),
    )
    monkeypatch.setattr(
        "backend.services.imported_aggregator.knowledge_repo",
        MagicMock(list_items=lambda source="secnews", limit=50, offset=0: []),
    )

    # page_size=1 should return 1 item per page
    r1 = aggregator.get_items(page=1, page_size=1)
    assert r1.total == 2
    assert len(r1.items) == 1
    assert r1.page_size == 1

    # page=0 should be clamped to 1
    r0 = aggregator.get_items(page=0, page_size=1)
    assert r0.page == 1
    assert len(r0.items) == 1

    # page_size=0 should be clamped to 1
    r_size0 = aggregator.get_items(page=1, page_size=0)
    assert r_size0.page_size == 1
    assert len(r_size0.items) == 1

    # page_size large should be clamped to 200
    r_large = aggregator.get_items(page=1, page_size=999)
    assert r_large.page_size == 200