"""v1.7 Phase 4 — 个性化画像服务.

PRD §3.2.9: 隐式权重计算与衰减。

核心函数
---------
- ``apply_signal(key, signal)`` — 对某维度施加一个信号, 更新权重 (EMA 风格)
- ``decay_all()`` — 全局衰减 (定时任务调用)
- ``get_profile()`` — 返回所有维度排序结果
- ``get_weight(key)`` — 读取单维度权重

权重公式
---------
::

    new_weight = clamp(old_weight * 0.95 + signal, -2.0, 2.0)

- ``old_weight * 0.95``: 每次信号到来时先做一次微衰减 (局部 EMA)
- ``+ signal``: 叠加新信号 (正值=兴趣增强, 负值=兴趣减弱)
- ``clamp``: 防止权重发散

信号常量
---------
- ``SIGNAL_READ`` (0.1): 阅读一篇文章 (弱正信号)
- ``SIGNAL_FAVORITE`` (0.3): 收藏一篇文章 (中正信号)
- ``SIGNAL_SKIP`` (-0.05): 跳过/不感兴趣 (弱负信号)
- ``SIGNAL_DEEP_READ`` (0.2): 深度阅读 + 笔记 (中正信号)

验收 1: "阅读 3 篇 AI 文章后 AI 分类权重提升"
  → 连续 3 次 ``apply_signal("category:ai", SIGNAL_READ)`` 后 weight > 0
"""
from __future__ import annotations

from typing import Optional

from backend.repository.profile_repo import ProfileRepository

# ---------------------------------------------------------------------------
# 信号常量
# ---------------------------------------------------------------------------
SIGNAL_READ = 0.1          # 阅读一篇文章
SIGNAL_FAVORITE = 0.3      # 收藏一篇文章
SIGNAL_DEEP_READ = 0.2     # 深度阅读 + 笔记
SIGNAL_SKIP = -0.05        # 跳过/不感兴趣
SIGNAL_REVIEW_GOOD = 0.15  # SM-2 复习评分高

# 权重范围
WEIGHT_MIN = -2.0
WEIGHT_MAX = 2.0

# 局部衰减系数 (每次 apply_signal 时先衰减旧权重)
_LOCAL_DECAY = 0.95


def apply_signal(key: str, signal: float) -> float:
    """对某维度施加一个信号, 更新并返回新权重。

    Parameters
    ----------
    key:
        维度 key, 如 ``"category:ai"`` / ``"tag:fastapi"``。
    signal:
        信号强度, 正值增强兴趣, 负值减弱。建议用 ``SIGNAL_*`` 常量。

    Returns
    -------
    float
        更新后的权重 (已 clamp 到 [-2.0, 2.0])。
    """
    repo = ProfileRepository()
    existing = repo.get(key)
    old = existing["weight"] if existing else 0.0
    new = max(WEIGHT_MIN, min(WEIGHT_MAX, old * _LOCAL_DECAY + signal))
    repo.set(key, new)
    return new


def decay_all() -> int:
    """全局衰减: 所有维度 weight *= 0.95。

    供定时任务 (scheduler) 每日调用, 实现遗忘曲线。

    Returns
    -------
    int
        受影响行数。
    """
    return ProfileRepository().decay_all()


def get_weight(key: str) -> float:
    """读取单维度权重, 不存在返回 0.0。"""
    row = ProfileRepository().get(key)
    return float(row["weight"]) if row else 0.0


def get_profile(limit: int = 100) -> list[dict]:
    """返回所有维度, 按权重绝对值降序 (最感兴趣/最排斥的在前)。

    Parameters
    ----------
    limit:
        最多返回条数。

    Returns
    -------
    list[dict]
        每条: ``{"dimension", "weight", "last_updated", "decayed_at"}``
    """
    rows = ProfileRepository().list_all()
    return rows[:limit] if limit > 0 else rows


def get_profile_by_prefix(prefix: str) -> list[dict]:
    """按维度前缀过滤 (如 ``"category:"`` → 所有分类维度)。"""
    return ProfileRepository().list_by_prefix(prefix)


def record_read(category: str, source: Optional[str] = None) -> float:
    """便捷方法: 记录一次阅读行为, 更新分类权重 (可选源权重)。

    Parameters
    ----------
    category:
        文章分类 (如 ``"ai"``)。
    source:
        可选, 数据源名 (如 ``"freebuf"``)。

    Returns
    -------
    float
        分类维度更新后的权重。
    """
    new_weight = apply_signal(f"category:{category}", SIGNAL_READ)
    if source:
        apply_signal(f"source:{source}", SIGNAL_READ)
    return new_weight


__all__ = [
    "SIGNAL_READ",
    "SIGNAL_FAVORITE",
    "SIGNAL_DEEP_READ",
    "SIGNAL_SKIP",
    "SIGNAL_REVIEW_GOOD",
    "WEIGHT_MIN",
    "WEIGHT_MAX",
    "apply_signal",
    "decay_all",
    "get_weight",
    "get_profile",
    "get_profile_by_prefix",
    "record_read",
]
