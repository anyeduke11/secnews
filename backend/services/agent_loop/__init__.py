"""agent_loop — v0.8 Phase B (B1) agent 五阶段状态机子包.

模块分层:
- ``state.py``     — 阶段枚举 + LoopStatus + LoopResult (结果数据类)
- ``checkpoint.py`` — loop_checkpoints 表读写 + 崩溃恢复扫描
- ``core.py``       — AgentLoop 状态机主类 (run/run_fast, 5 阶段调度, REFLECT retry 1)

对外契约: ``AgentLoop().run(skill, inputs, run_id=...)`` 入口;
REFLECT 失败自动 retry 1 次, 仍失败 → commit partial=True。
``run_fast`` 跳过 REFLECT (A/B 类快速路径, 不调 LLM)。
checkpoint 持久化按 run 维度一行/阶段, 进程崩溃可续跑。
"""
from __future__ import annotations

from backend.services.agent_loop.checkpoint import (
    LoopCheckpoint,
    LoopCheckpointRepo,
)
from backend.services.agent_loop.core import (
    AgentLoop,
    AgentLoopHooks,
    AgentLoopSettings,
    LLMPort,
    build_default_llm_port,
)
from backend.services.agent_loop.state import (
    PHASE_ORDER,
    LoopPhase,
    LoopResult,
    LoopStatus,
    is_terminal,
    next_phase,
    should_run_phase,
)
from backend.services.agent_loop.core import (
    recover_stale_checkpoints as _recover_stale_checkpoints,
)

__all__ = [
    "AgentLoop",
    "AgentLoopHooks",
    "AgentLoopSettings",
    "LLMPort",
    "LoopCheckpoint",
    "LoopCheckpointRepo",
    "LoopPhase",
    "LoopResult",
    "LoopStatus",
    "PHASE_ORDER",
    "build_default_llm_port",
    "is_terminal",
    "next_phase",
    "recover_stale_checkpoints",
    "should_run_phase",
]

#: 重新导出, 保持单入口
recover_stale_checkpoints = _recover_stale_checkpoints
del _recover_stale_checkpoints
