"""v1.7 Phase 2 — SM-2 间隔复习服务。

SM-2 算法 (SuperMemo 2):
    grade ∈ [0, 5] (0-2: 失败, 3-5: 通过)
    - grade < 3:  复习次数归零, 间隔 1 天
    - grade >= 3: 第 1 次 → 1 天, 第 2 次 → 6 天, 之后 → round(interval * easiness)
    easiness 永远 ≥ 1.3, 每次评分动态调整。

对外暴露:
    - ``sm2_schedule``: 纯函数, 给定当前状态返回新状态 (easiness, interval, repetitions)
    - ``submit_grade``: 评分 → 更新 sm2_reviews 记录 + 写 review_log (旧→新快照)
    - ``list_due``: 到期复习队列 (排除 suspended)
    - ``stats``: 复习统计 (总数/到期数/平均 EF + 保留率/评分分布/暂停数)
    - ``create_review``: 为新学概念创建首条复习记录 (验收 1: 24h 内进入队列)
    - ``undo_grade``: 撤销最近一次评分 (恢复 review_log prev 状态)
    - ``set_suspended`` / ``forecast``: 卡片管理面 (migration 120)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.repository.reviews_log_repo import ReviewLogRepository
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
    - 每次评分原子地写一条 review_log 旧→新快照 (migration 120),
      undo 与统计以 log 为唯一真数据源。
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
    # 评分与 log 在同一写路径内先后落库; undo 无活跃 log 的状态不存在
    # (故 manage API 的 undo 缺 log 契约是 409, 不可能 "有评分无 log")。
    ReviewLogRepository().insert(
        entity_type, entity_id, grade,
        prev=row,
        new_easiness=new_easiness,
        new_interval=new_interval,
        new_repetitions=new_repetitions,
        new_due_at=due_at,
    )
    return repo.get(entity_type, entity_id)


def undo_grade(entity_type: str, entity_id: str) -> dict | None:
    """撤销最近一次评分 (migration 120)。

    恢复最新一条 ``reverted=0`` log 的 prev 状态 (含 last_grade /
    last_reviewed_at) 并标记 reverted; 首评 (prev 为空) = 删除记录;
    链式可重复调用逐级回退。无活跃 log → KeyError (API 层转 409)。
    返回恢复后的记录 (首评撤销返回 None)。
    """
    repo = ReviewRepository()
    log_repo = ReviewLogRepository()
    log = log_repo.latest_active(entity_type, entity_id)
    if log is None:
        raise KeyError(f"无可撤销评分: {entity_type}/{entity_id}")

    if log["prev_due_at"] is None:
        # 首评撤销: 评分前无记录 → 删除复习记录
        repo.delete(entity_type, entity_id)
        restored = None
    else:
        repo.restore_state(
            entity_type, entity_id,
            easiness=log["prev_easiness"],
            interval=log["prev_interval"],
            repetitions=log["prev_repetitions"],
            due_at=log["prev_due_at"],
            last_grade=log["prev_last_grade"],
            last_reviewed_at=log["prev_last_reviewed_at"],
        )
        restored = repo.get(entity_type, entity_id)
    log_repo.mark_reverted(log["id"])
    return restored


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


def set_suspended(entity_type: str, entity_id: str, suspended: bool) -> int:
    """暂停/恢复一张卡 (migration 120), 返回更新行数 (0 = 卡不存在)。"""
    return ReviewRepository().set_suspended(entity_type, entity_id, suspended)


def forecast(days: int = 7) -> list[dict]:
    """未来 N 天逐日到期计数 (排除 suspended, 含今日), 恒返回 N 条。"""
    return ReviewRepository().forecast(days=days)


def stats() -> dict:
    """复习统计: 总数 / 到期数 / 平均 easiness + 扩展字段 (migration 120)。

    - ``retention_30d``: review_log 近 30 天 grade>=3 占比, 无数据 None。
    - ``grade_distribution``: 近 30 天各 grade 次数 (键为字符串 grade)。
    - ``suspended_count``: 暂停中的卡片数。
    """
    repo = ReviewRepository()
    log_repo = ReviewLogRepository()
    all_rows = repo.list_all(limit=10000)
    due = repo.list_due(limit=10000)
    avg_easiness = (
        sum(r["easiness"] for r in all_rows) / len(all_rows) if all_rows else 0.0
    )
    retention_30d = log_repo.retention(days=30)
    distribution = log_repo.grade_distribution(days=30)
    return {
        "total": len(all_rows),
        "due": len(due),
        "avg_easiness": round(avg_easiness, 3),
        "retention_30d": round(retention_30d, 4) if retention_30d is not None else None,
        "grade_distribution": {str(k): v for k, v in distribution.items()},
        "suspended_count": repo.count_suspended(),
    }


__all__ = [
    "create_review",
    "forecast",
    "list_due",
    "set_suspended",
    "sm2_schedule",
    "stats",
    "submit_grade",
    "undo_grade",
]
