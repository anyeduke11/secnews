"""评分工具。

- :func:`compute_final_score` base=100 累加扣分，最低 0
- :func:`merge_flags`        列表去重，保留顺序
- :func:`is_acceptable`      评分 ≥ 阈值返回 True
"""
from __future__ import annotations

from typing import Iterable


def compute_final_score(
    base: int = 100, deductions: Iterable[int] = ()
) -> int:
    """``base`` 减去 ``deductions`` 之和；最低 0。

    >>> compute_final_score(100, [10, 20, 30])
    40
    >>> compute_final_score(100, [200])
    0
    """
    score = base
    for d in deductions:
        if d is None:
            continue
        score -= int(d)
    return max(0, score)


def merge_flags(*flags_lists: Iterable[str]) -> list[str]:
    """合并多个 flag 列表，去重，保留首次出现顺序。

    >>> merge_flags(["a", "b"], ["b", "c"])
    ['a', 'b', 'c']
    """
    seen: set[str] = set()
    out: list[str] = []
    for lst in flags_lists:
        if not lst:
            continue
        for f in lst:
            if f and f not in seen:
                seen.add(f)
                out.append(f)
    return out


def is_acceptable(score: int, threshold: int = 30) -> bool:
    """``score >= threshold`` 表示可接受。"""
    return score >= threshold


__all__ = ["compute_final_score", "merge_flags", "is_acceptable"]
