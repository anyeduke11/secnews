"""v1.7 Phase 2 — SM-2 间隔复习服务。

SM-2 算法 (SuperMemo 2):
    grade ∈ [0, 5] (0-2: 失败, 3-5: 通过)
    - grade < 3:  复习次数归零, 间隔 1 天
    - grade >= 3: 第 1 次 → 1 天, 第 2 次 → 6 天, 之后 → round(interval * easiness)
    easiness 永远 ≥ 1.3, 每次评分动态调整。

对外暴露:
    - ``sm2_schedule``: 纯函数, 给定当前状态返回新状态 (easiness, interval, repetitions)
    - ``submit_grade``: 评分 → 更新 sm2_reviews 记录
    - ``list_due``: 到期复习队列
    - ``stats``: 复习统计 (总数/到期数/平均 easiness)
    - ``create_review``: 为新学概念创建首条复习记录 (验收 1: 24h 内进入队列)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.repository.reviews_repo import ReviewRepository

# 默认初始参数
_DEFAULT_EASINESS = 2.5
_DEFAULT_INTERVAL = 0
_DEFAULT_REPETITIONS = 0


def sm2_schedule(
    grade: int,
    easiness: float,
    interval: int,
    repetitions: int,
) -> tuple[float, int, int]:
    """SM-2 核心公式 (纯函数, 无副作用)。

    返回 (new_easiness, new_interval, new_repetitions)。
    """
    if grade < 3:
        # 失败: 重置
        repetitions = 0
        interval = 1
    else:
        # 通过
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * easiness)
        repetitions += 1
    # easiness 调整 (永不低于 1.3)
    easiness = max(
        1.3,
        easiness + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02),
    )
    return easiness, interval, repetitions


def submit_grade(entity_type: str, entity_id: str, grade: int) -> dict:
    """对 ``entity_type/entity_id`` 提交一次评分, 更新 SM-2 状态。

    - grade ∈ [0, 5], 超范围抛 ValueError。
    - 首次评分 (无记录) 用默认参数 (easiness=2.5, interval=0, repetitions=0)。
    - 返回更新后的记录 dict。
    """
    if not 0 <= grade <= 5:
        raise ValueError(f"grade must be 0-5, got {grade}")

    repo = ReviewRepository()
    row = repo.get(entity_type, entity_id)
    if row:
        easiness = row["easiness"]
        interval = row["interval"]
        repetitions = row["repetitions"]
    else:
        easiness = _DEFAULT_EASINESS
        interval = _DEFAULT_INTERVAL
        repetitions = _DEFAULT_REPETITIONS

    new_easiness, new_interval, new_repetitions = sm2_schedule(
        grade, easiness, interval, repetitions
    )
    due_at = (
        datetime.now(timezone.utc) + timedelta(days=new_interval)
    ).isoformat()

    repo.upsert(
        entity_type, entity_id,
        new_easiness, new_interval, new_repetitions,
        due_at, grade,
    )
    return repo.get(entity_type, entity_id)


def create_review(
    entity_type: str,
    entity_id: str,
    initial_interval_days: int = 1,
) -> dict:
    """为新学概念创建首条复习记录 (验收 1)。

    默认 1 天后到期 (24h 内进入复习队列)。若已存在记录则不覆盖, 直接返回现有。
    """
    repo = ReviewRepository()
    existing = repo.get(entity_type, entity_id)
    if existing is not None:
        return existing
    due_at = (
        datetime.now(timezone.utc) + timedelta(days=initial_interval_days)
    ).isoformat()
    repo.upsert(
        entity_type, entity_id,
        _DEFAULT_EASINESS, initial_interval_days, 0,
        due_at, -1,  # last_grade=-1 表示尚未评分
    )
    return repo.get(entity_type, entity_id)


def list_due(limit: int = 20) -> list[dict]:
    """列出到期复习记录 (due_at <= now)。"""
    return ReviewRepository().list_due(limit=limit)


def stats() -> dict:
    """复习统计: 总数 / 到期数 / 平均 easiness。"""
    repo = ReviewRepository()
    all_rows = repo.list_all(limit=10000)
    due = repo.list_due(limit=10000)
    avg_easiness = (
        sum(r["easiness"] for r in all_rows) / len(all_rows) if all_rows else 0.0
    )
    return {
        "total": len(all_rows),
        "due": len(due),
        "avg_easiness": round(avg_easiness, 3),
    }


__all__ = [
    "sm2_schedule",
    "submit_grade",
    "create_review",
    "list_due",
    "stats",
]
