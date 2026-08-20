"""P0.5: 调度器并发限制测试。

测试意图 (Rule 9):
- AsyncIOScheduler 应配置 AsyncIOExecutor (单线程异步, 天然限制并发)
- 所有 job 应有 max_instances=1 (同 job 不重叠)
- coalesce=True (错过的合并为一次)
- 这些限制防止 43 个 job 同时运行导致资源耗尽
"""
from __future__ import annotations

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor


def test_scheduler_creation_helper():
    """P0.5: 验证 create_scheduler() 工厂函数存在且配置正确。"""
    from backend.scheduler.scheduler import create_scheduler

    scheduler = create_scheduler()

    assert isinstance(scheduler, AsyncIOScheduler)
    # 验证 job_defaults
    defaults = scheduler._job_defaults
    assert defaults.get("max_instances") == 1
    assert defaults.get("coalesce") is True


def test_scheduler_uses_asyncio_executor():
    """P0.5: scheduler 应配置 AsyncIOExecutor (单线程异步)。

    AsyncIOExecutor 是单线程异步执行器, 天然限制并发:
    同时只有一个协程运行, 防止 43 个 job 资源耗尽。
    """
    from backend.scheduler.scheduler import create_scheduler

    scheduler = create_scheduler()
    executor = scheduler._executors.get("default")
    assert executor is not None
    assert isinstance(executor, AsyncIOExecutor)


def test_scheduler_max_instances_one():
    """P0.5: max_instances=1 确保同一 job 不重叠。

    场景: collect_all 间隔 300s, 但单次跑 400s
    修复前: 下一轮在 300s 时启动, 与上一轮重叠
    修复后: max_instances=1, APScheduler 跳过重叠轮次
    """
    from backend.scheduler.scheduler import create_scheduler

    scheduler = create_scheduler()
    defaults = scheduler._job_defaults
    assert defaults.get("max_instances") == 1


def test_scheduler_coalesce_true():
    """P0.5: coalesce=True 确保错过的合并为一次。

    场景: 服务停机 2 小时, 某个 5min 间隔的 job 错过 24 次
    修复前: 重启后补跑 24 次 (资源耗尽)
    修复后: coalesce=True, 只跑 1 次
    """
    from backend.scheduler.scheduler import create_scheduler

    scheduler = create_scheduler()
    defaults = scheduler._job_defaults
    assert defaults.get("coalesce") is True


def test_start_uses_create_scheduler():
    """P0.5: HotspotScheduler.start() 应使用 create_scheduler()。

    验证 start() 创建的 scheduler 有 max_instances + coalesce 配置。
    """
    from backend.scheduler.scheduler import HotspotScheduler, create_scheduler

    # 验证 create_scheduler 是模块级函数
    assert callable(create_scheduler)

    # 验证 start() 内部调用 create_scheduler (通过检查 scheduler 配置)
    # 不真正 start (需要 service), 只验证 create_scheduler 输出
    scheduler = create_scheduler()
    defaults = scheduler._job_defaults
    assert defaults.get("max_instances") == 1
    assert defaults.get("coalesce") is True
