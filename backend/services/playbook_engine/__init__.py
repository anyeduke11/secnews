"""playbook_engine — v0.8 Phase C C1+C2 (升级 codegarden_orchestration_service).

模块分层 (按 spec tasks C1.1 + C2):
- ``core.py``      — Playbook / PlaybookStep / PlaybookRun / PlaybookEngine 主类
                     (load/validate/execute + 50step/1h 上限 + 危险命令黑名单 P4-7)
- ``loader.py``    — YAML 解析 + fs 加载 (含 hot-reload token 算子, 留 C2 cron 用)
- ``step.py``      — 单步执行器: skill / api / condition 三类 (R7 砍 script)
- ``scheduler.py`` — PlaybookScheduler (BackgroundScheduler + SQLite 持久化,
                     migration 094 playbook_schedules + playbook_runs)

对外契约:
- PlaybookEngine().execute(name, inputs=...) -> PlaybookRun
- PlaybookScheduler().upsert_schedule(...)/set_enabled/remove_schedule
- 旧 codegarden_orchestration_service.run_playbook 薄包装调新引擎, 保留
  P4-7 黑名单; 旧路由 /api/codegarden/... 不破坏 (R-对抗审查场景 4)。

设计纪律 (V0.8_REFACTOR_PLAN.md §5):
- 步数 ≤50 + 总时长 ≤1h → 强制停止 + 写 audit (R6 边界)
- step 类型仅 skill / api / condition, **script step 不实现** (R7 RCE 边界)
- 危险命令黑名单 (P4-7 沿用): sudo / rm -rf / chmod 777 / curl|sh / eval 等
- 引用的 skill 必须已注册 (R8 悬空引用 → validate 失败)
- Jinja 表达式简化版: 仅支持 ``{{ steps.<id>.output.<path> }}`` 与 ``{{ inputs.<key> }}``
  替换, 不引入 jinja2 依赖; condition 步骤用 asteval 安全求值布尔/比较表达式
- cron 调度独立 BackgroundScheduler (不接入主 AsyncIOScheduler), 防 playbook
  长任务阻塞主调度单线程 (R6 1h 上限风险隔离)
"""
from __future__ import annotations

from backend.services.playbook_engine.core import (
    MAX_STEPS,
    MAX_TOTAL_SECONDS,
    Playbook,
    PlaybookEngine,
    PlaybookRun,
    PlaybookStep,
    StepKind,
    StepResult,
    ValidationReport,
    ValidationReportEntry,
)
from backend.services.playbook_engine.loader import list_examples, load_playbook
from backend.services.playbook_engine.scheduler import (
    DEFAULT_TZ,
    PlaybookRunRepo,
    PlaybookScheduleRepo,
    PlaybookScheduler,
)
from backend.services.playbook_engine.step import StepExecutor

__all__ = [
    "DEFAULT_TZ",
    "MAX_STEPS",
    "MAX_TOTAL_SECONDS",
    "Playbook",
    "PlaybookEngine",
    "PlaybookRun",
    "PlaybookRunRepo",
    "PlaybookScheduleRepo",
    "PlaybookScheduler",
    "PlaybookStep",
    "StepExecutor",
    "StepKind",
    "StepResult",
    "ValidationReport",
    "ValidationReportEntry",
    "list_examples",
    "load_playbook",
]