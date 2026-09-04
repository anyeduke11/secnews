"""三档优先级定义 (v0.8 Phase A / R6 非抢占语义).

trigger-gate 队列的调度只依赖一个整数优先级:
- 0 = REALTIME — 用户显式触发 / 交互式请求, 出队最优先
- 1 = NORMAL   — 常规触发 (cron / webhook / 事件), 默认档
- 2 = BATCH    — 批处理 / 低价值回填, 空闲时消费

优先级 **只影响出队顺序** (dequeue 按 priority ASC), 绝不中断正在
运行的任务 — 抢占语义被 R6 明确排除, worker 侧只做非抢占泵。

用 IntEnum 而非 str: 出队 SQL 直接 ORDER BY priority ASC, 数字即
排序键, 无需查表翻译; 同时保留枚举的命名可读性。
"""
from __future__ import annotations

from enum import IntEnum


class Priority(IntEnum):
    """三档优先级 (数值越小越优先出队)。"""

    REALTIME = 0
    NORMAL = 1
    BATCH = 2


# 数字 → 小写名称, 用于日志 / API 展示层翻译
PRIORITY_NAMES: dict[int, str] = {
    Priority.REALTIME.value: "realtime",
    Priority.NORMAL.value: "normal",
    Priority.BATCH.value: "batch",
}


__all__ = ["PRIORITY_NAMES", "Priority"]
