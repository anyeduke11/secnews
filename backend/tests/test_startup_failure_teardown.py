"""DEV-0309 R15 — 启动失败路径关闭链契约测试。

uvicorn 语义 (取证 server.py L103-106 / lifespan/on.py L65-66): lifespan
startup 抛错 → sys.exit(STARTUP_FAILURE), shutdown 半程整体跳过 → 曾经的
做法是残留全靠进程退出兜底。本测试锁定修复后契约:
1. 启动失败 → 同款关闭链被尽力驱动 + 原异常传播不吞 (fail-loud);
2. 链对「未启动子系统」完全容忍 (半程失败安全整链调用);
3. 正常路径链仍只执行一次 (行为回归)。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI

from backend import main as main_mod


class _Boom(RuntimeError):
    pass


def test_startup_failure_drives_chain_and_propagates(monkeypatch):
    """_run_startup raise → 链被调用一次 + 原异常类型/消息不变地传播。"""
    calls: list[str] = []

    async def _fake_startup(app):
        calls.append("startup")
        raise _Boom("migration failed")

    async def _fake_chain(app):
        calls.append("chain")

    monkeypatch.setattr(main_mod, "_run_startup", _fake_startup)
    monkeypatch.setattr(main_mod, "_run_shutdown_chain", _fake_chain)

    async def scenario():
        app = FastAPI()
        with pytest.raises(_Boom, match="migration failed"):
            async with main_mod.lifespan(app):
                pass

    asyncio.run(scenario())
    assert calls == ["startup", "chain"], f"失败路径必须驱动关闭链, got {calls}"


def test_startup_failure_when_chain_itself_raises_still_propagates(monkeypatch):
    """链意外抛异常也不得覆盖原始启动失败异常 (双保险路径)。"""
    async def _fake_startup(app):
        raise _Boom("root cause")

    async def _bad_chain(app):
        raise RuntimeError("chain exploded")

    monkeypatch.setattr(main_mod, "_run_startup", _fake_startup)
    monkeypatch.setattr(main_mod, "_run_shutdown_chain", _bad_chain)

    async def scenario():
        with pytest.raises(_Boom, match="root cause"):
            async with main_mod.lifespan(FastAPI()):
                pass

    asyncio.run(scenario())


def test_chain_tolerates_unstarted_subsystems():
    """裸 app (无 state.scheduler / 子系统全未启动) 整链调用不抛 —
    半程启动失败安全调链的前提 (幂等 + 逐步隔离)。"""
    async def scenario():
        await main_mod._run_shutdown_chain(FastAPI())
        await main_mod._run_shutdown_chain(FastAPI())  # 双调用幂等

    asyncio.run(scenario())  # 不抛即通过


def test_normal_path_runs_chain_exactly_once(monkeypatch):
    """正常路径回归: startup 成功 → 进入 → 退出时链执行一次。"""
    calls: list[str] = []

    async def _fake_startup(app):
        calls.append("startup")

    async def _fake_chain(app):
        calls.append("chain")

    monkeypatch.setattr(main_mod, "_run_startup", _fake_startup)
    monkeypatch.setattr(main_mod, "_run_shutdown_chain", _fake_chain)

    async def scenario():
        async with main_mod.lifespan(FastAPI()):
            calls.append("inside")

    asyncio.run(scenario())
    assert calls == ["startup", "inside", "chain"]
