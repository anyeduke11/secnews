"""v0.7 Batch ⑤ — 用户记忆服务.

读取/写入 user_memory 表, 为反馈分析器 + feed 个性化提供上下文。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.repository.user_memory_repo import UserMemoryRepository

logger = logging.getLogger(__name__)

_user_memory_repo = UserMemoryRepository()


class UserMemoryService:
    """用户记忆 CRUD."""

    def record_memory(
        self,
        memory_type: str,
        key: str,
        value: str,
        source: str = "feedback_analyzer",
    ) -> dict[str, Any]:
        """写入单条记忆 (幂等: 同一 memory_type+key 更新 value)。

        Returns
        -------
        dict
            写入后的行。
        """
        return _user_memory_repo.upsert(memory_type, key, value, source)

    def get_memory(self, memory_type: str, key: str) -> dict | None:
        """读取单条记忆."""
        return _user_memory_repo.get(memory_type, key)

    def list_memories(self, memory_type: str) -> list[dict[str, Any]]:
        """按 memory_type 列出所有记忆."""
        return _user_memory_repo.list_by_type(memory_type)

    def get_user_context(self) -> dict[str, Any]:
        """返回结构化用户画像上下文。

        Returns
        -------
        dict
            ``{"interests": [...], "dislikes": [...], "source_prefs": [...],
            "reading_style": "...", "raw_count": N}``
        """
        interests = self._memory_list_to_values("interest")
        dislikes = self._memory_list_to_values("dislike")
        source_prefs = self._memory_list_to_values("source_pref")
        reading_style_rows = _user_memory_repo.list_by_type("reading_style")
        reading_style = ""
        if reading_style_rows:
            try:
                val = json.loads(reading_style_rows[0]["value"])
                reading_style = val.get("style", "")
            except Exception:
                pass

        return {
            "interests": interests,
            "dislikes": dislikes,
            "source_prefs": source_prefs,
            "reading_style": reading_style,
            "raw_count": len(interests) + len(dislikes) + len(source_prefs),
        }

    def _memory_list_to_values(self, memory_type: str) -> list[str]:
        rows = _user_memory_repo.list_by_type(memory_type)
        values: list[str] = []
        for r in rows:
            try:
                val = json.loads(r["value"])
                if memory_type == "interest":
                    values.append(val.get("interest", r["key"]))
                elif memory_type == "dislike":
                    values.append(val.get("dislike", r["key"]))
                elif memory_type == "source_pref":
                    values.append(val.get("preferred_source", r["key"]))
                else:
                    values.append(r["key"])
            except Exception:
                values.append(r["key"])
        return values


# 模块级单例
user_memory_service = UserMemoryService()

__all__ = ["UserMemoryService", "user_memory_service"]
