"""v1.7 Phase 5 — Agent Package.

外部 AI Agent 的可执行包. 与 hotspot 后端通过 HTTP 通信.

结构:
  client.py     HTTP 客户端
  executor.py   task_type → skill 路由
  poller.py     后台轮询循环
  cli.py        命令行入口 (start/stop/status/run-once)
  skills/       可插拔 skill 实现
"""
from __future__ import annotations

from agent.client import HotspotClient
from agent.executor import execute_task
from agent.poller import AgentPoller

__all__ = ["HotspotClient", "AgentPoller", "execute_task"]
