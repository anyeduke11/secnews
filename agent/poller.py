"""v1.7 Phase 5 — Agent Poller.

Daemon-style polling loop. Adjusts interval based on queue depth:
  - 有任务时: 间隔减半 (最低 60s)
  - 无任务时: 间隔递增 (最高 600s)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from agent.client import HotspotClient
from agent.executor import execute_task

log = logging.getLogger("hotspot.agent.poller")

# 鸭子类型 client (只需有 get_tasks/complete_task 方法)
AgentClientLike = HotspotClient


class AgentPoller:
    """轮询执行任务的后台循环.

    Args:
        client: HotspotClient 实例
        interval: 初始轮询间隔 (秒)
        min_interval: 最小间隔 (有任务时), 默认 60s
        max_interval: 最大间隔 (无任务时), 默认 600s
    """

    def __init__(
        self,
        client: AgentClientLike,
        interval: int = 60,
        min_interval: int = 60,
        max_interval: int = 600,
    ) -> None:
        self.client = client
        self.interval = max(min_interval, min(interval, max_interval))
        self.min_interval = min_interval
        self.max_interval = max_interval

    def run_forever(self) -> None:
        """无限循环 (前台)."""
        log.info("poller started, interval=%ds", self.interval)
        while True:
            try:
                self.run_once()
            except Exception as e:
                log.exception("poller iteration failed: %s", e)
            time.sleep(self.interval)

    def run_once(self, limit: int = 10) -> dict:
        """执行一个轮询周期.

        Returns:
            {
                "fetched": 拉取数,
                "done": 成功数,
                "failed": 失败数,
                "interval": 下一周期间隔 (秒),
            }
        """
        tasks = self.client.get_tasks(limit=limit)
        fetched = len(tasks)

        if fetched == 0:
            # 无任务: 拉长间隔
            self.interval = min(self.max_interval, self.interval + 30)
        else:
            # 有任务: 缩短间隔
            self.interval = max(self.min_interval, self.interval // 2)

        done = 0
        failed = 0
        for task in tasks:
            task_id = task.get("task_id")
            task_type = task.get("task_type", "?")
            try:
                log.info("executing task %s (%s)", task_id, task_type)
                result = execute_task(task, client=self.client)
                self.client.complete_task(task_id, "done", result=result)
                done += 1
            except Exception as e:
                log.exception("task %s failed: %s", task_id, e)
                try:
                    self.client.complete_task(
                        task_id, "failed", error=str(e)[:500]
                    )
                except Exception as ce:
                    log.error("failed to mark task %s as failed: %s", task_id, ce)
                failed += 1

        log.info(
            "poller cycle: fetched=%d done=%d failed=%d next_interval=%ds",
            fetched, done, failed, self.interval,
        )
        return {
            "fetched": fetched,
            "done": done,
            "failed": failed,
            "interval": self.interval,
        }
