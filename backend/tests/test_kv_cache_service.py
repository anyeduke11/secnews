"""v1.7 Phase 5 — KV Cache Service 测试."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.kv_cache_repo import KVCacheRepository, kv_cache_repo
from backend.services.kv_cache_service import KVCacheService, kv_cache


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_kv_cache.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# KVCacheRepository
# ---------------------------------------------------------------------------
class TestKVCacheRepository:
    def test_set_and_get(self, temp_db):
        repo = KVCacheRepository()
        repo.set("foo", {"bar": 1}, expires_seconds=60)
        assert repo.get("foo") == {"bar": 1}

    def test_get_missing_returns_none(self, temp_db):
        repo = KVCacheRepository()
        assert repo.get("nonexistent") is None

    def test_set_overwrites(self, temp_db):
        repo = KVCacheRepository()
        repo.set("k", {"v": 1})
        repo.set("k", {"v": 2})
        assert repo.get("k") == {"v": 2}

    def test_set_no_expiry(self, temp_db):
        repo = KVCacheRepository()
        repo.set("permanent", {"x": True}, expires_seconds=None)
        assert repo.get("permanent") == {"x": True}

    def test_expired_not_returned(self, temp_db):
        repo = KVCacheRepository()
        repo.set("short", {"v": 1}, expires_seconds=0)
        # expires_seconds=0 → 已过期 (expires_at ≈ now)
        time.sleep(0.05)
        assert repo.get("short") is None

    def test_delete(self, temp_db):
        repo = KVCacheRepository()
        repo.set("k", {"v": 1})
        repo.delete("k")
        assert repo.get("k") is None

    def test_invalidate_prefix(self, temp_db):
        repo = KVCacheRepository()
        repo.set("items:list", {"a": 1})
        repo.set("items:detail", {"b": 2})
        repo.set("other:key", {"c": 3})
        deleted = repo.invalidate_prefix("items:")
        assert deleted == 2
        assert repo.get("items:list") is None
        assert repo.get("items:detail") is None
        assert repo.get("other:key") == {"c": 3}

    def test_invalidate_prefix_no_match(self, temp_db):
        repo = KVCacheRepository()
        assert repo.invalidate_prefix("nonexistent:") == 0

    def test_cleanup_expired(self, temp_db):
        repo = KVCacheRepository()
        repo.set("expired1", {"v": 1}, expires_seconds=0)
        repo.set("expired2", {"v": 2}, expires_seconds=0)
        repo.set("alive", {"v": 3}, expires_seconds=300)
        time.sleep(0.05)
        cleaned = repo.cleanup_expired()
        assert cleaned == 2
        assert repo.get("alive") == {"v": 3}

    def test_cleanup_expired_keeps_no_expiry(self, temp_db):
        repo = KVCacheRepository()
        repo.set("permanent", {"v": 1}, expires_seconds=None)
        repo.set("expired", {"v": 2}, expires_seconds=0)
        time.sleep(0.05)
        cleaned = repo.cleanup_expired()
        assert cleaned == 1
        assert repo.get("permanent") == {"v": 1}

    def test_count(self, temp_db):
        repo = KVCacheRepository()
        repo.set("a", {"v": 1})
        repo.set("b", {"v": 2})
        assert repo.count() == 2

    def test_count_excludes_expired(self, temp_db):
        repo = KVCacheRepository()
        repo.set("alive", {"v": 1}, expires_seconds=60)
        repo.set("dead", {"v": 2}, expires_seconds=0)
        time.sleep(0.05)
        assert repo.count() == 1

    def test_malformed_value_returns_none(self, temp_db):
        """value 列损坏时 get 返回 None 而非抛异常."""
        from backend.repository.db import get_connection
        get_connection().execute(
            "INSERT INTO kv_cache (key, value, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("bad", "not-json", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        assert kv_cache_repo.get("bad") is None


# ---------------------------------------------------------------------------
# KVCacheService
# ---------------------------------------------------------------------------
class TestKVCacheService:
    def test_get_and_set(self, temp_db):
        svc = KVCacheService()
        svc.set("k", {"v": 1})
        assert svc.get("k") == {"v": 1}

    def test_cached_get_hit(self, temp_db):
        svc = KVCacheService()
        svc.set("cached", {"v": 42})
        fetcher_calls = []

        def fetcher():
            fetcher_calls.append(1)
            return {"v": 999}

        result = svc.cached_get("cached", fetcher)
        assert result == {"v": 42}
        assert len(fetcher_calls) == 0, "缓存命中时不应调 fetcher"

    def test_cached_get_miss(self, temp_db):
        svc = KVCacheService()
        fetcher_calls = []

        def fetcher():
            fetcher_calls.append(1)
            return {"v": "fetched"}

        result = svc.cached_get("miss", fetcher, expires_seconds=60)
        assert result == {"v": "fetched"}
        assert len(fetcher_calls) == 1
        # 第二次应命中缓存
        result2 = svc.cached_get("miss", fetcher, expires_seconds=60)
        assert result2 == {"v": "fetched"}
        assert len(fetcher_calls) == 1

    def test_invalidate_knowledge_items(self, temp_db):
        svc = KVCacheService()
        svc.set("items:list", {"a": 1})
        svc.set("item:abc", {"b": 2})
        svc.set("other", {"c": 3})
        svc.invalidate_knowledge_items()
        assert svc.get("items:list") is None
        assert svc.get("item:abc") is None
        assert svc.get("other") == {"c": 3}

    def test_invalidate_item(self, temp_db):
        svc = KVCacheService()
        svc.set("item:abc", {"v": 1})
        svc.set("items:list", {"v": 2})
        svc.invalidate_item("abc")
        assert svc.get("item:abc") is None
        assert svc.get("items:list") is None

    def test_cleanup_expired(self, temp_db):
        svc = KVCacheService()
        svc.set("dead", {"v": 1}, expires_seconds=0)
        svc.set("alive", {"v": 2}, expires_seconds=60)
        time.sleep(0.05)
        cleaned = svc.cleanup_expired()
        assert cleaned == 1
        assert svc.get("alive") == {"v": 2}

    def test_singleton(self):
        """kv_cache 单例可用."""
        assert kv_cache is not None
        assert kv_cache.repo is not None
