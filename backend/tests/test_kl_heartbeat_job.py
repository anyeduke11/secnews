"""kl_pipeline_heartbeat_job 单元测试 (SECNEWS Phase 1, 2026-08-24)。

心跳消费: 每 60s drain_due 常规消化 + 每 10 拍 sweep 兜底滞留条目;
底层故障只 log.error 不抛 (与既有 job 模式一致)。
"""
from __future__ import annotations

import asyncio

import pytest


class _FakePipeline:
    def __init__(self, calls: dict) -> None:
        self._calls = calls

    def drain_due(self, limit: int = 50) -> dict:
        self._calls["drain"] += 1
        return {"done": limit, "failed": 0}

    def sweep(self) -> int:
        self._calls["sweep"] += 1
        return 2


@pytest.fixture
def patched(monkeypatch):
    import backend.kl_pipeline.runtime as kl_runtime
    import backend.scheduler.jobs as jobs

    calls = {"drain": 0, "sweep": 0}
    monkeypatch.setattr(
        kl_runtime,
        "get_production_pipeline",
        lambda: _FakePipeline(calls),
    )
    monkeypatch.setattr(jobs, "_kl_heartbeat_beats", {"n": 0})
    return calls


def test_drain_and_sweep_on_tenth_beat(patched, monkeypatch):
    """第 10 拍触发兜底 sweep。"""
    import backend.scheduler.jobs as jobs

    monkeypatch.setattr(jobs, "_kl_heartbeat_beats", {"n": 9})
    asyncio.run(jobs.kl_pipeline_heartbeat_job())

    assert patched == {"drain": 1, "sweep": 1}
    assert jobs._kl_heartbeat_beats["n"] == 10


def test_drain_only_between_sweeps(patched):
    """非 10 的倍数拍不 sweep。"""
    import backend.scheduler.jobs as jobs

    asyncio.run(jobs.kl_pipeline_heartbeat_job())
    assert patched == {"drain": 1, "sweep": 0}


def test_crash_is_swallowed(monkeypatch):
    """底层故障只 log.error 不抛 — 与既有 job 模式一致。"""
    import backend.kl_pipeline.runtime as kl_runtime
    import backend.scheduler.jobs as jobs

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(kl_runtime, "get_production_pipeline", boom)
    monkeypatch.setattr(jobs, "_kl_heartbeat_beats", {"n": 0})

    asyncio.run(jobs.kl_pipeline_heartbeat_job())  # 不抛异常
