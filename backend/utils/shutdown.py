"""Graceful shutdown 助手 — v0.8.1 Day 0 (V0.8.1_PRD v1.0 F5 / D-b)。

SIGTERM 时 uvicorn 先停收 HTTP (in-flight 请求自然收尾), 再走 lifespan
shutdown。本模块补齐 lifespan 关闭链缺的三件事:

1. :func:`drain_in_flight` — 有界等待在跑 APScheduler job 自然收尾。
   此前 lifespan 直接 ``sched.stop()`` → ``AsyncIOScheduler.shutdown()``
   会 cancel pending futures, 即协作式打断在跑 job (collect_all 等长任务
   在下一个 await 点被掐断)。
2. :func:`wal_checkpoint` — close_db() 前 ``PRAGMA wal_checkpoint(TRUNCATE)``,
   把 WAL 折叠回主库 (此前从未显式 checkpoint, 依赖下次打开时自动恢复)。
3. 关闭路径永不抛异常 — 任何失败只告警, 保证 SIGTERM rc=0。

环境变量
--------
- ``HOTSPOT_GRACEFUL_TIMEOUT``  drain 等待上限秒数, 默认 ``30``; ``0`` 跳过
  等待 (测试环境 conftest 预置 0); 非法值回退默认。
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from typing import Any

from loguru import logger as _logger

from backend.repository import db as repo_db

# 注意: 本仓生产日志 = loguru (logging_config.setup), stdlib logging 无
# InterceptHandler → 输出不可见。新代码一律用 loguru。

DEFAULT_GRACE_SECONDS = 30.0


def get_graceful_timeout() -> float:
    """读 ``HOTSPOT_GRACEFUL_TIMEOUT``; 非法/负值安全回退。"""
    raw = os.getenv("HOTSPOT_GRACEFUL_TIMEOUT")
    if raw is None:
        return DEFAULT_GRACE_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        _logger.warning(
            "HOTSPOT_GRACEFUL_TIMEOUT={} 非法, 回退 {}s", raw, DEFAULT_GRACE_SECONDS
        )
        return DEFAULT_GRACE_SECONDS


def _collect_pending_futures(apsched: Any) -> tuple[list[asyncio.Future], bool]:
    """从 AsyncIOScheduler 的各 executor 快照未完成 future。

    只读不改 (不动 APScheduler 私有结构); 取不到内省通道时返回
    ``(=[], False)``, 调用方按"无法内省"走固定等待兜底。
    """
    futures: list[asyncio.Future] = []
    seen_executor = False
    executors = getattr(apsched, "_executors", None)
    if not isinstance(executors, dict):
        return futures, False
    for exc in executors.values():
        pending = getattr(exc, "_pending_futures", None)
        if pending is None:
            continue
        seen_executor = True
        futures.extend(f for f in list(pending) if not f.done())
    return futures, seen_executor


async def drain_in_flight(scheduler: Any, timeout: float | None = None) -> dict:
    """有界等待在跑 job 自然收尾。永不抛异常。

    - 能内省 pending futures: 只等真正在跑的 (没有在跑 → 立即返回, 不空等);
    - 不能内省: 固定等待 ``timeout`` 秒兜底;
    - ``timeout <= 0``: 跳过等待 (测试环境)。
    """
    if timeout is None:
        timeout = get_graceful_timeout()
    timeout = max(0.0, float(timeout))
    stats: dict[str, Any] = {
        "timeout_s": timeout,
        "waited_s": 0.0,
        "drained": 0,
        "left_running": 0,
        "introspected": False,
    }
    if timeout <= 0 or scheduler is None:
        return stats
    try:
        apsched = getattr(scheduler, "scheduler", None)
        pending, seen_executor = _collect_pending_futures(apsched)
        stats["introspected"] = seen_executor
    except Exception as e:  # pragma: no cover - 防御性
        _logger.warning(f"drain introspection failed (ignored): {e}")
        pending, seen_executor = [], False
        stats["introspected"] = False

    t0 = time.monotonic()
    try:
        if pending:
            done, not_done = await asyncio.wait(set(pending), timeout=timeout)
            stats["drained"] = len(done)
            stats["left_running"] = len(not_done)
        elif seen_executor:
            pass  # 内省成功且无在跑 job — 无需等待
        else:
            await asyncio.sleep(timeout)  # 无法内省, 固定等待兜底
    except Exception as e:  # pragma: no cover - 防御性
        _logger.warning(f"drain wait failed (ignored): {e}")
    stats["waited_s"] = round(time.monotonic() - t0, 3)
    if timeout > 0:
        _logger.info(f"graceful drain done: {stats}")
    return stats


def wal_checkpoint() -> bool:
    """主连接 ``PRAGMA wal_checkpoint(TRUNCATE)``; 失败不抛 (关闭路径容忍)。

    Returns:
        True = WAL 完全折叠 (checkpoint 返回 0); False = busy / 失败。
    """
    try:
        conn = repo_db.get_connection()
    except Exception as e:
        _logger.warning(f"wal_checkpoint: get_connection failed (ignored): {e}")
        return False
    try:
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        ok = bool(row) and int(row[0]) == 0
        if ok:
            _logger.info("wal_checkpoint: truncated")
        else:
            _logger.warning(f"wal_checkpoint: busy (row={row!r}) — 下次打开时自动恢复")
        return ok
    except sqlite3.Error as e:
        _logger.warning(f"wal_checkpoint failed (ignored): {e}")
        return False
