"""v1.7 Phase 5 — KV Cache Service.

薄封装层, 提供:
- kv_cache 单例 (KVCacheRepository)
- 便捷的 cached_get: 先查缓存, miss 则调 fetcher 并回填
- watcher 调用的失效入口
"""
from __future__ import annotations

from typing import Callable, Optional

from backend.repository.kv_cache_repo import KVCacheRepository, kv_cache_repo


class KVCacheService:
    """KV 缓存服务 — 封装 repo + 提供高级语义."""

    def __init__(self, repo: Optional[KVCacheRepository] = None) -> None:
        self._repo = repo or kv_cache_repo

    @property
    def repo(self) -> KVCacheRepository:
        return self._repo

    # --- 基本读写 ---

    def get(self, key: str) -> Optional[dict]:
        return self._repo.get(key)

    def set(
        self,
        key: str,
        value: dict,
        expires_seconds: Optional[int] = 60,
    ) -> None:
        self._repo.set(key, value, expires_seconds)

    def delete(self, key: str) -> None:
        self._repo.delete(key)

    def invalidate_prefix(self, prefix: str) -> int:
        return self._repo.invalidate_prefix(prefix)

    def cleanup_expired(self) -> int:
        return self._repo.cleanup_expired()

    # --- 高级语义 ---

    def cached_get(
        self,
        key: str,
        fetcher: Callable[[], dict],
        expires_seconds: int = 60,
    ) -> dict:
        """先查缓存, miss 则调 fetcher 并回填.

        遵循 cache-aside 模式:
          1. get(key) → hit 返回
          2. miss → fetcher() → set(key, value) → 返回 value
        """
        cached = self._repo.get(key)
        if cached is not None:
            return cached
        value = fetcher()
        self._repo.set(key, value, expires_seconds)
        return value

    # --- watcher 集成入口 ---

    def invalidate_knowledge_items(self) -> None:
        """knowledge_items .md 文件变更后失效相关缓存."""
        self._repo.invalidate_prefix("items:")
        self._repo.invalidate_prefix("item:")

    def invalidate_item(self, item_id: str) -> None:
        """单个 knowledge_item 变更后失效."""
        self._repo.delete(f"item:{item_id}")
        self._repo.invalidate_prefix("items:")


kv_cache = KVCacheService()
