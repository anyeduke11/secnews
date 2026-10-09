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
import threading
import time
from typing import Any

from loguru import logger as _logger

from backend.repository import db as repo_db

# 注意: 本仓生产日志 = loguru (logging_config.setup), stdlib logging 无
# InterceptHandler → 输出不可见。新代码一律用 loguru。

DEFAULT_GRACE_SECONDS = 30.0

# DEV-0307 R13: 无法内省 pending futures 时的盲等上限 — 看不见在跑什么,
# 盲等满 30s 既无信息量又挤兑停机总预算, 10s 后照常走关闭链。
UNINTROSPECTED_DRAIN_CAP_S = 10.0


def _env_float(name: str, default: float) -> float:
    """读 env 浮点值; 非法回退 default (停机路径永不抛)。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        _logger.warning("{}={} 非法, 回退 {}s", name, raw, default)
        return default


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
            # DEV-0307 R13: 无法内省 (APScheduler 私有结构变更等) → 盲等
            # 封顶 10s 兜底, 不再吃满整个 drain 预算挤兑停机 deadline
            await asyncio.sleep(min(timeout, UNINTROSPECTED_DRAIN_CAP_S))
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


def guaranteed_exit(exit_code: int = 0) -> None:  # pragma: no cover - os._exit 不可回归
    """解释器退出尾闸 (DEV-0303 R2): uvicorn.run 返回后立即硬退出。

    优雅停机工作已全部在 lifespan 完成 (drain / scheduler / dsh / outbox /
    watcher / wal_checkpoint / close_db)。此后若走解释器正常退出流程,
    ``threading._shutdown`` 会 join 全部非守护线程 — 任何一个被遗漏的
    非守护线程在跑都会挂死退出。现实实例: 启动期图谱点火把 STIX bundle
    下载 (分钟级) 丢进 asyncio 默认线程池 (main.py run_in_executor(None)),
    停机窗口撞上即卡退出。``os._exit`` 跳过 atexit / join 阶段, 使进程
    退出时间有确定上界。run.py 与 backend.main ``__main__`` 在 finally
    中调用 — 无论正常返回还是异常退出都保证有界终结。
    """
    try:
        _logger.complete()  # 刷所有 sink 缓冲, 保住尾部日志
        _logger.info(f"guaranteed_exit: hard exit (code={exit_code})")
        _logger.complete()
    except Exception:
        pass
    import os as _os

    _os._exit(exit_code)


# ---------------------------------------------------------------------------
# DEV-0305 R8+R9: 停机总监时器 (deadline watchdog)
# DEV-0307 R13: 预算改「派生和」— 固定 60s 会被关闭链各子超时之和挤兑穿底
# (排空+drain 已占 45s, 撞 crawl4ai/dsh 慢环节时优雅收尾被 deadline 抢杀)。
# ---------------------------------------------------------------------------

# 关闭链非 env 化环节预算: crawl4ai close 5s + dsh stop 15s (wait 10 +
# kill + wait 5) + outbox/watcher/WAL/close_db 等杂项余量 10s。
_CLOSE_CHAIN_FIXED_BUDGET_S = 30.0
# 派生值解析异常时的最终兜底
_FALLBACK_SHUTDOWN_BUDGET_S = 75.0

_deadline_lock = threading.Lock()
_deadline_timer: threading.Timer | None = None


def derived_shutdown_budget() -> float:
    """停机总预算 = 排空 + drain + 关闭链固定环节 (与子超时联动)。

    env 显式 HOTSPOT_SHUTDOWN_HARD_TIMEOUT 优先 (见 get_shutdown_budget);
    本函数保证 deadline 永远 ≥ 正常关闭链之和, 不再抢杀优雅收尾。
    """
    try:
        drain = max(0.0, _env_float("HOTSPOT_SHUTDOWN_TIMEOUT", 15.0))
        graceful = get_graceful_timeout()
        return drain + graceful + _CLOSE_CHAIN_FIXED_BUDGET_S
    except Exception:  # pragma: no cover - 防御性
        return _FALLBACK_SHUTDOWN_BUDGET_S


def get_shutdown_budget() -> float:
    """读 ``HOTSPOT_SHUTDOWN_HARD_TIMEOUT``; 未设 → 派生和 (DEV-0307 R13)。

    派生构成: uvicorn 排空 (HOTSPOT_SHUTDOWN_TIMEOUT, 默认 15s) + lifespan
    drain (HOTSPOT_GRACEFUL_TIMEOUT, 默认 30s) + 关闭链固定环节 30s
    (crawl4ai 5 + dsh 15 + 杂项余量 10)。默认派生 = 75s。
    """
    raw = os.getenv("HOTSPOT_SHUTDOWN_HARD_TIMEOUT")
    if raw is None:
        return derived_shutdown_budget()
    try:
        val = float(raw)
    except ValueError:
        _logger.warning(
            "HOTSPOT_SHUTDOWN_HARD_TIMEOUT={} 非法, 回退派生和", raw
        )
        return derived_shutdown_budget()
    if val <= 0:
        _logger.warning(
            "HOTSPOT_SHUTDOWN_HARD_TIMEOUT={} 非正, 回退派生和", raw
        )
        return derived_shutdown_budget()
    return val


def _deadline_exceeded() -> None:
    """预算耗尽回调: 无论主线程卡在哪 (executor join / 无超时 await), 硬退。"""
    try:
        _logger.warning(
            "shutdown deadline exceeded — guaranteed_exit from watchdog "
            "(主线程疑卡在 executor join / close_client 等无界 await, 见 DEV-0305 R8/R9)"
        )
    except Exception:
        pass
    guaranteed_exit(0)


def arm_shutdown_deadline() -> None:
    """信号到达时武装停机总监时器 (daemon Timer, 预算耗尽 os._exit)。

    R8+R9 同根治理: ``guaranteed_exit`` 挂在 ``uvicorn.run`` 返回之后的
    finally — 但 (a) Runner.close 的 ``shutdown_default_executor`` 会 join
    正在执行的 to_thread/run_in_executor 同步任务 (实验: 6s 任务 → run()
    6s 后才返回; 图谱点火 STIX 75s 级), (b) lifespan 关闭链无总时限, 任一
    无超时 await (如 crawl4ai close_client 撞僵尸浏览器) 都让 run 永不
    返回 → 尾闸入口本身被堵死。定时器从信号时刻起算, 覆盖停机全链, 是
    唯一能穿透一切挂点的兜底 (与 R1 前置哨兵同架构: 不信任下游, 先到先防)。

    幂等: 重复信号只武装一次 (预算从第一次 TERM 起算, 二次 TERM 不重置)。
    """
    global _deadline_timer
    with _deadline_lock:
        if _deadline_timer is not None:
            return
        budget = get_shutdown_budget()
        _deadline_timer = threading.Timer(budget, _deadline_exceeded)
        _deadline_timer.daemon = True
        _deadline_timer.name = "shutdown-deadline"
        _deadline_timer.start()
    _logger.info(f"shutdown deadline armed: hard exit if not down in {budget:.0f}s")


__all__ = [
    "DEFAULT_GRACE_SECONDS",
    "arm_shutdown_deadline",
    "drain_in_flight",
    "get_graceful_timeout",
    "get_shutdown_budget",
    "guaranteed_exit",
    "wal_checkpoint",
]
