"""skill_runner — v0.8 Phase B (B2) 按 skill_type 分流派单子包.

模块分层:
- ``result.py``   — SkillRunResult 数据类 + SkillRunRepo (skill_runs 表 DAO)
- ``dispatch.py`` — A/B 快速路径 + C/D pipeline 步骤执行器 (含 wiki 落盘)
- ``core.py``     — SkillRunner 主类 + run_skill 顶层入口

对外契约:
    from backend.services.skill_runner import run_skill, SkillRunner, SkillRunResult
    result = run_skill(skill_def, inputs, ticket_id=...)
    # result.run_id, result.status, result.metrics, result.wiki_path

设计纪律 (V0.8_REFACTOR_PLAN.md §5.3 + spec.md R2):
- A/B 类走 fast-path (2 阶段: resolve→execute→commit, 零 LLM token)
- C/D 类走完整五阶段 (agent_loop 驱动; pipeline steps 按序执行)
- 全部 run 写 skill_runs 表 (R3 统一数据源)
- C 类 wiki step 产物落 llm-wiki-2.0/ (wiki-first 哲学)
- ApiTarget 通过进程内 httpx 调本机 backend (不 import backend.api, 反向依赖禁令)
- ServiceTarget 通过 importlib + getattr 反射调用 module.class.method
"""
from __future__ import annotations

from backend.services.skill_runner.core import (
    SkillRunner,
    SkillRunnerSettings,
    run_skill,
)
from backend.services.skill_runner.result import (
    SkillRunRepo,
    SkillRunResult,
)

__all__ = [
    "SkillRunRepo",
    "SkillRunResult",
    "SkillRunner",
    "SkillRunnerSettings",
    "run_skill",
]