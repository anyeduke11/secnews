"""v1.7 Phase 4 — 个性化画像 Repository.

``personal_profile`` 表 (migration 030) 记录各维度的隐式权重。

Schema
------
::

    personal_profile (
        dimension    TEXT PRIMARY KEY,   -- 维度 key, 如 "category:ai"
        weight       REAL DEFAULT 0.0,    -- 当前权重, 范围 [-2.0, 2.0]
        last_updated TEXT NOT NULL,       -- 最近一次 set/apply_signal 时间
        decayed_at   TEXT NOT NULL        -- 最近一次 decay_all 时间
    )

设计决策
---------
- 维度 key 命名: ``<type>:<value>`` (如 ``category:ai`` / ``tag:fastapi`` /
  ``source:freebuf``)，便于按类型聚合。
- 权重范围 [-2.0, 2.0]: 正值表示兴趣, 负值表示排斥, 0 为中性。
- 衰减: ``decay_all()`` 对所有维度 weight *= 0.95, 实现 EMA 风格的遗忘曲线。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.repository.db import get_connection

# 权重上下限 (与 profile_service.apply_signal 一致)
_WEIGHT_MIN = -2.0
_WEIGHT_MAX = 2.0

# 衰减系数
_DECAY_FACTOR = 0.95


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProfileRepository:
    """``personal_profile`` 表的 CRUD + 衰减。"""

    def get(self, dimension: str) -> Optional[dict]:
        """读取单个维度的权重记录。

        Returns
        -------
        Optional[dict]
            ``{"dimension", "weight", "last_updated", "decayed_at"}`` 或 ``None``。
        """
        row = get_connection().execute(
            "SELECT * FROM personal_profile WHERE dimension = ?",
            (dimension,),
        ).fetchone()
        return dict(row) if row else None

    def set(self, dimension: str, weight: float) -> dict:
        """设置某维度的权重 (upsert)。

        权重会被 clamp 到 ``[_WEIGHT_MIN, _WEIGHT_MAX]``。
        """
        clamped = max(_WEIGHT_MIN, min(_WEIGHT_MAX, float(weight)))
        now = _now_iso()
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO personal_profile (dimension, weight, last_updated, decayed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dimension) DO UPDATE SET
                weight = excluded.weight,
                last_updated = excluded.last_updated
            """,
            (dimension, clamped, now, now),
        )
        row = conn.execute(
            "SELECT * FROM personal_profile WHERE dimension = ?", (dimension,)
        ).fetchone()
        return dict(row)

    def list_all(self) -> list[dict]:
        """列出所有维度, 按权重绝对值降序 (最感兴趣/最排斥的在前)。"""
        rows = get_connection().execute(
            "SELECT * FROM personal_profile ORDER BY ABS(weight) DESC, dimension ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_prefix(self, prefix: str) -> list[dict]:
        """按维度前缀过滤 (如 ``"category:"`` → 所有分类维度)。"""
        rows = get_connection().execute(
            "SELECT * FROM personal_profile WHERE dimension LIKE ? "
            "ORDER BY weight DESC",
            (f"{prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, dimension: str) -> bool:
        """删除某维度。返回是否实际删除了一行。"""
        cur = get_connection().execute(
            "DELETE FROM personal_profile WHERE dimension = ?", (dimension,)
        )
        return cur.rowcount > 0

    def decay_all(self) -> int:
        """对所有维度权重衰减 (weight *= 0.95), 更新 decayed_at。

        Returns
        -------
        int
            受影响行数。
        """
        now = _now_iso()
        cur = get_connection().execute(
            "UPDATE personal_profile SET weight = weight * ?, decayed_at = ?",
            (_DECAY_FACTOR, now),
        )
        return cur.rowcount

    def count(self) -> int:
        """返回当前维度总数。"""
        row = get_connection().execute(
            "SELECT COUNT(*) AS n FROM personal_profile"
        ).fetchone()
        return int(row["n"]) if row else 0


__all__ = ["ProfileRepository"]
