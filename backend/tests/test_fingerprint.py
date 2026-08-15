"""Tests for simhash-based dedup in collection_service._dedup_items.

5 tests:
1. 指纹写入 — non-duplicate items are written to content_fingerprints
2. 去重检测 — duplicate item (simhash Hamming < 5) is skipped
3. 重复跳过 — multiple duplicates only keep the first unique item
4. 索引验证 — function handles large fingerprint sets (mock perf)
5. 边界 — empty list, empty title, None summary
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.services.collection_service import _to_signed_64
from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    normalize_title,
    simhash,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    id_: str,
    title: str = "Test Article",
    summary: str | None = None,
) -> HotspotItem:
    """Create a minimal HotspotItem for testing."""
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        summary=summary,
        source="test",
        url=f"https://example.com/{id_}",
        category=Category.AI,
        published_at=now,
        fetched_at=now,
    )


def _make_mock_conn(
    simhash_rows: list[tuple[str, int]] | None = None,
    url_rows: list[tuple[str]] | None = None,
) -> MagicMock:
    """Build a mock DB connection that returns controlled fingerprint data."""
    mock_conn = MagicMock()

    def execute_side_effect(sql, *args):
        cursor = MagicMock()
        stripped = sql.strip()
        if stripped.startswith("SELECT") and "simhash" in stripped:
            cursor.fetchall.return_value = simhash_rows or []
        elif stripped.startswith("SELECT") and "url_canonical" in stripped:
            cursor.fetchall.return_value = url_rows or []
        # INSERT: return an empty cursor (result ignored)
        return cursor

    mock_conn.execute.side_effect = execute_side_effect
    return mock_conn


@pytest.fixture
def svc():
    from backend.services.collection_service import CollectionService
    return CollectionService()


# ---------------------------------------------------------------------------
# 1. 指纹写入
# ---------------------------------------------------------------------------

class TestFingerprintInsertion:
    """Non-duplicate items' fingerprints are written by _write_fingerprints.

    P0-5: _dedup_items 不再写 content_fingerprints (hotspot 行尚未入库,
    FK 必失败); 改为入库成功后由 _write_fingerprints 补写。
    """

    def test_dedup_no_longer_writes_fingerprints(self, svc):
        """_dedup_items 只做判定, 不再发 INSERT (指纹写入移至入库后)."""
        items = [
            _make_item("a1", title="AI Safety Research Update"),
            _make_item("a2", title="New Quantum Computing Breakthrough"),
        ]
        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            result = svc._dedup_items(items)

            assert len(result) == 2
            insert_calls = [
                c for c in mock_conn.execute.call_args_list
                if "INSERT" in c[0][0]
            ]
            assert len(insert_calls) == 0  # P0-5: 去重阶段不再写指纹

    def test_write_fingerprints_for_new_items(self, svc):
        """_write_fingerprints 在入库后写入正确指纹 (FK 已满足)."""
        items = [
            _make_item("a1", title="AI Safety Research Update"),
            _make_item("a2", title="New Quantum Computing Breakthrough"),
        ]
        fp1 = simhash("AI Safety Research Update")
        fp2 = simhash("New Quantum Computing Breakthrough")

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            written = svc._write_fingerprints(items)

            insert_calls = [
                c for c in mock_conn.execute.call_args_list
                if "INSERT" in c[0][0]
            ]
            assert len(insert_calls) == 2

            _sql, params = insert_calls[0].args
            assert params[0] == "a1"  # hotspot_id
            assert params[1] == _to_signed_64(fp1)  # simhash (signed)
            assert params[2] == canonicalize_url("https://example.com/a1")
            assert params[3] == normalize_title("AI Safety Research Update")

            _sql, params = insert_calls[1].args
            assert params[0] == "a2"
            assert params[1] == _to_signed_64(fp2)

    def test_summary_used_in_simhash(self, svc):
        """Summary is included in the simhash text when present."""
        item = _make_item("s1", title="Title", summary="Body content")
        fp_with_summary = simhash("Title Body content")

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            svc._write_fingerprints([item])

            insert_calls = [
                c for c in mock_conn.execute.call_args_list
                if "INSERT" in c[0][0]
            ]
            assert len(insert_calls) == 1
            _sql, params = insert_calls[0].args
            assert params[1] == _to_signed_64(fp_with_summary)


# ---------------------------------------------------------------------------
# 2. 去重检测
# ---------------------------------------------------------------------------

class TestDedupDetection:
    """Duplicate items (by simhash or URL) are skipped."""

    def test_skips_by_simhash(self, svc):
        """Item with simhash close to an existing one is skipped."""
        item = _make_item("dup1", title="AI Safety Research Update 2024")
        title_text = "AI Safety Research Update 2024"
        fp = simhash(title_text)

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn(
                simhash_rows=[("existing_1", fp)],
            )
            mock_get.return_value = mock_conn

            result = svc._dedup_items([item])

            assert len(result) == 0

    def test_skips_by_url(self, svc):
        """Item whose canonical URL already exists is skipped."""
        item = _make_item("url_dup", title="Different Title New Content")
        url_canonical = canonicalize_url("https://example.com/url_dup")

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn(
                url_rows=[(url_canonical,)],
            )
            mock_get.return_value = mock_conn

            result = svc._dedup_items([item])

            assert len(result) == 0

    def test_skips_by_hamming_distance(self, svc):
        """Item with Hamming distance < 5 to existing fingerprint is skipped."""
        item = _make_item("close_dup", title="AI Safety Research Update 2024")
        title_text = "AI Safety Research Update 2024"
        fp = simhash(title_text)

        # Flip 2 bits to simulate a very close fingerprint
        close_fp = fp ^ 0b11  # Hamming distance = 2
        assert hamming_distance(fp, close_fp) == 2

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn(
                simhash_rows=[("existing_1", close_fp)],
            )
            mock_get.return_value = mock_conn

            result = svc._dedup_items([item])

            assert len(result) == 0


# ---------------------------------------------------------------------------
# 3. 重复跳过
# ---------------------------------------------------------------------------

class TestBatchDedup:
    """Multiple duplicates only keep the first unique item."""

    def test_keeps_only_first_of_duplicates(self, svc):
        """Three items, two duplicates → only one passes through."""
        items = [
            _make_item("unique_1", title="Completely Unique Topic"),
            _make_item("dup_a", title="Duplicate News Story"),
            _make_item("dup_b", title="Duplicate News Story"),
        ]
        fp_unique = simhash("Completely Unique Topic")
        fp_dup = simhash("Duplicate News Story")

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            # First call: no existing fingerprints
            cursor = MagicMock()
            cursor.fetchall.return_value = []

            # We need to track which execute calls are which
            call_log: list[str] = []

            def execute_side(sql, *args):
                call_log.append(sql)
                cur = MagicMock()
                stripped = sql.strip()
                if (stripped.startswith("SELECT") and "simhash" in stripped) or (stripped.startswith("SELECT") and "url_canonical" in stripped):
                    cur.fetchall.return_value = []
                return cur

            mock_conn = MagicMock()
            mock_conn.execute.side_effect = execute_side
            mock_get.return_value = mock_conn

            result = svc._dedup_items(items)

            # unique_1 passes, dup_a passes (first occurrence), dup_b is skipped
            assert len(result) == 2
            assert result[0].id == "unique_1"

    def test_handles_mixed_duplicates(self, svc):
        """Mix of unique and duplicate items — only unique ones survive."""
        items = [
            _make_item("unique_1", title="Unique Article Alpha"),
            _make_item("dup_1", title="Repeated Headline"),
            _make_item("unique_2", title="Unique Article Beta"),
            _make_item("dup_2", title="Repeated Headline"),
            _make_item("unique_3", title="Unique Article Gamma"),
        ]

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            result = svc._dedup_items(items)

            # 3 unique + 1 first occurrence of "Repeated Headline" = 4
            assert len(result) == 4
            assert result[0].id == "unique_1"
            assert result[1].id == "dup_1"
            assert result[2].id == "unique_2"
            assert result[3].id == "unique_3"


# ---------------------------------------------------------------------------
# 4. 索引验证
# ---------------------------------------------------------------------------

class TestIndexPerformance:
    """Function handles large fingerprint sets efficiently."""

    def test_handles_large_existing_set(self, svc):
        """No crash when many existing fingerprints exist (mocked)."""
        item = _make_item("new_item", title="Fresh Content")
        fp = simhash("Fresh Content")

        # Simulate 1000 existing fingerprints, all different from fp
        existing_rows = [
            (f"old_{i}", simhash(f"Old Content Article Number {i}"))
            for i in range(1000)
        ]
        # Ensure none match fp (very unlikely with different content)
        # But also add a few that are close to verify dedup still works
        existing_rows.append(("close_one", fp ^ 0b111111))  # Hamming dist = 6 → not duplicate

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn(
                simhash_rows=existing_rows,
            )
            mock_get.return_value = mock_conn

            # Should complete without error
            result = svc._dedup_items([item])

            assert len(result) == 1
            assert result[0].id == "new_item"

    def test_query_count_is_constant(self, svc):
        """Only two SELECT queries are made regardless of item count."""
        items = [
            _make_item(f"item_{i}", title=f"Article Number {i}")
            for i in range(10)
        ]

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            svc._dedup_items(items)

            # Verify only 2 SELECT queries total
            select_calls = [
                c for c in mock_conn.execute.call_args_list
                if "SELECT" in c[0][0]
            ]
            assert len(select_calls) == 2


# ---------------------------------------------------------------------------
# 5. 边界
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases: empty list, empty title, None summary, etc."""

    def test_empty_list(self, svc):
        """Empty input returns empty list."""
        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            result = svc._dedup_items([])

            assert result == []
            # No DB queries should be made for empty input
            mock_conn.execute.assert_not_called()

    def test_whitespace_title(self, svc):
        """Item with whitespace-only title is handled (simhash returns 0)."""
        item = _make_item("ws_title", title="   ")

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            # Should not raise
            result = svc._dedup_items([item])

            assert len(result) == 1

    def test_none_summary(self, svc):
        """Item with None summary does not crash."""
        item = _make_item("no_summary", title="Title Only", summary=None)

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            result = svc._dedup_items([item])

            assert len(result) == 1

    def test_special_characters_in_title(self, svc):
        """Special characters in title are handled."""
        item = _make_item(
            "special",
            title="🔥 AI Safety: 2024 Update! (urgent) #research",
        )

        with patch(
            "backend.services.collection_service.get_connection"
        ) as mock_get:
            mock_conn = _make_mock_conn()
            mock_get.return_value = mock_conn

            result = svc._dedup_items([item])

            assert len(result) == 1