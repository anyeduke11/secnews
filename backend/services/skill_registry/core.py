"""skill_registry.core — SkillDef 统一契约 + 注册表 (v0.8 Phase A · A2b).

契约三条硬规则 (docs/V0.8_SKILL_ABSTRACTION.md §4.0, A2b 任务书扩展):
1. **target / pipeline 互斥二选一** — 单步复用走 target (A/B 类直调),
   多步编排走 pipeline (C/D 类); 同时出现或同时为空即设计错误。
2. **只存引用, 不复制逻辑** — target 存 ``module.class.method`` 引用,
   由后续 skill_runner 反射调用; 复制逻辑会造成 job/API/skill 行为漂移。
3. **prompt_template 仅 C/D 类** — A/B/E 类出现 prompt_template 即设计错误
   (设计纪律 2: 默认不调 LLM); C/D 类必填, pipeline 内 LLM 步骤可携带
   步骤级 prompt 覆盖 skill 级默认。

分类法 (§2): A 巡检 / B 查询 / C 报告 / D 分析 / E 操作 (v0.9 留空)。
启停控制: 每个 skill 独立 gate ``skill.<id>.enabled`` 落 settings kv,
父 gate 为扩展域 ``skill_registry`` (A3/A5 注册, 未注册前按 fail-closed
读数为关, 见 gate.py docstring)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backend.repository.settings_repo import SettingsRepository

__all__ = [
    "ApiTarget",
    "LlmTarget",
    "ServiceTarget",
    "SkillDef",
    "SkillNotFoundError",
    "SkillRegistry",
    "SkillRegistryValidationError",
    "Step",
]

#: 分类法取值 — 与 docs/V0.8_REFACTOR_PLAN.md §4 四个 skill 分组一一对应
SkillCategory = Literal["operations", "compliance", "analysis", "report"]
#: A-E 分类 (§2 五类分类法); E 操作型 v0.8 不落地, 契约先行
SkillType = Literal["A", "B", "C", "D", "E"]
#: 执行器 — builtin 为进程内直调; pi/claude-code/codex 留给后续 runner 接线
SkillRunner = Literal["builtin", "pi", "claude-code", "codex"]


class SkillNotFoundError(Exception):
    """get()/enable()/gate 查询未知 skill_id 时抛出 — 调用方 bug, fail loud。"""


class SkillRegistryValidationError(Exception):
    """register() 前置校验失败 (loader.load_validation errors 非空) 时抛出。

    message 携带全部违规条目, 便于启动日志一次性定位 (见 loader.py 规则清单)。
    """


# ---------------------------------------------------------------------------
# Target 三兄弟 — "只存引用" 的载体 (契约规则 2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ServiceTarget:
    """service / repository 方法引用 — 单步 skill 的直调目标。

    - class_name 非 None: ``<module>.<class_name>().<method>()`` 实例方法
    - class_name 为 None: ``<module>.<method>()`` 模块级函数
      (本仓库大量 service 为模块级函数, 如 maintenance_service.table_stats)

    module 必须是真实存在的模块路径 — loader 用 importlib.find_spec 校验,
    防止注册期拼错 module 名直到运行期才爆炸。
    """

    module: str
    class_name: str | None = None
    method: str = ""


@dataclass(frozen=True)
class ApiTarget:
    """API 端点引用 — B 类查询型 (单 GET + 展示层封装) 的直调目标。

    只存 path/http_method 字符串, **不 import backend.api** (service 层
    依赖方向约束); httpx 调用由后续 skill_runner 统一执行。
    """

    path: str
    http_method: str = "GET"


@dataclass(frozen=True)
class LlmTarget:
    """LLM 调用引用 — 显式钉死 provider 的 pipeline 步骤目标 (预留)。

    v0.8 内置 20 skill 的 LLM 步骤统一走 ai_hub 四级切换链, 不钉 provider;
    该 dataclass 供后续需要绕过默认链的 skill (如强制 codex 深度分析) 使用。
    """

    provider_hint: str = ""


# ---------------------------------------------------------------------------
# Step — pipeline 编排原语 (C/D 类多步)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Step:
    """pipeline 单步 — kind 决定字段语义。

    - kind="service": target 必填 (ServiceTarget 引用), args 为入参
      (值支持 ``{{ input.x }}`` / ``{{ steps.N.output }}`` 模板占位,
      由 runner 渲染 — 注册期只做结构校验不做渲染)
    - kind="llm": prompt_template 可选 — None 时回退 SkillDef.prompt_template
      (skill 级主指令); 显式给出则必须非空 (契约规则 3: prompt 只出现在 llm 步)
    - kind="wiki": path/content 为落盘模板 (wiki-first 归档)

    契约规则 3 的机械面: 非 llm 步携带 prompt_template → loader 违规。
    """

    kind: Literal["service", "llm", "wiki"]
    target: ServiceTarget | None = None
    args: dict | None = None
    prompt_template: str | None = None
    path: str | None = None
    content: str | None = None


# ---------------------------------------------------------------------------
# SkillDef — 统一注册契约
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SkillDef:
    """一个 skill = 一个原子用户价值 (30s-5min, §1.3 设计纪律 3)。

    字段分组:
    - 身份: id (kebab-case) / name / desc (中文, 前端卡片直出)
    - 分类: category (plan §4 四分组) + skill_type (§2 五类分类法)
    - 执行面: target | pipeline 二选一 + prompt_template (仅 C/D)
    - 契约面: input_schema / output_schema (轻量 Python 类型标注风格)
    - 控制面: runner / timeout_seconds / feature_gate / default_enabled
      / requires_gate_check (R12: 前置检查父扩展 gate, 如 mcp)

    feature_gate 锁: 格式恒为 ``skill.<id>.enabled``, 与 id 自洽
    (loader 规则 ②); kv 读写走 SettingsRepository (settings 表)。
    """

    id: str
    name: str
    desc: str
    category: SkillCategory
    skill_type: SkillType
    target: ServiceTarget | ApiTarget | None = None
    pipeline: list[Step] | None = None
    prompt_template: str | None = None
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    runner: SkillRunner = "builtin"
    timeout_seconds: int = 300
    feature_gate: str = ""
    default_enabled: bool = False
    requires_gate_check: list[str] | None = None


# ---------------------------------------------------------------------------
# SkillRegistry — 注册 + 查询 + 启停
# ---------------------------------------------------------------------------
class SkillRegistry:
    """skill 注册表: 注册(带校验) / 查询 / enable-disable (写 settings kv)。

    - register(): 先过 loader.load_validation (合并存量 id 查重),
      errors 非空抛 SkillRegistryValidationError — 注册期拦截, 不留坏定义
    - get(): 未知 id 抛 SkillNotFoundError (fail loud)
    - enable()/disable(): 写 settings kv (key = skill.feature_gate),
      经 SettingsRepository 真实落库; 运行态读数统一走 gate.is_skill_enabled
    - list(enabled_only=True): 惰性 import gate (避免 core↔gate 循环),
      按 kv+父 gate 联合读数过滤
    """

    def __init__(self) -> None:
        self._skills: list[SkillDef] = []
        self._index: dict[str, SkillDef] = {}

    # -- 查询 ---------------------------------------------------------------
    def list(
        self,
        category: SkillCategory | None = None,
        enabled_only: bool = False,
    ) -> list[SkillDef]:
        """按分类 / 启用态过滤, 保持注册顺序 (前端卡片顺序稳定)。"""
        skills = list(self._skills)
        if category is not None:
            skills = [s for s in skills if s.category == category]
        if enabled_only:
            # 惰性 import: gate → builtin → core, 顶层 import 会成环
            from backend.services.skill_registry.gate import is_skill_enabled

            skills = [s for s in skills if is_skill_enabled(s.id)]
        return skills

    def get(self, skill_id: str) -> SkillDef:
        """按 id 精确取 — 未知 id 抛 SkillNotFoundError。"""
        try:
            return self._index[skill_id]
        except KeyError:
            raise SkillNotFoundError(f"skill not found: {skill_id!r}") from None

    # -- 注册 ---------------------------------------------------------------
    def register(self, skills: list[SkillDef]) -> None:
        """批量注册 (启动加载入口) — 校验失败整体拒绝, 不做部分注册。

        校验对象是「存量 + 本次」合并清单: 规则 ① id 唯一需跨批次查重,
        只查本次会让分批注册的重复 id 漏网。
        """
        from backend.services.skill_registry.loader import load_validation

        combined = self._skills + list(skills)
        report = load_validation(combined)
        if report.errors:
            raise SkillRegistryValidationError(
                "skill 注册校验失败 (" + f"{len(report.errors)} 条):\n  - "
                + "\n  - ".join(report.errors)
            )
        for skill in skills:
            self._skills.append(skill)
            self._index[skill.id] = skill

    # -- 启停 (settings kv) --------------------------------------------------
    def enable(self, skill_id: str) -> None:
        """启用: settings kv 写 True (key = skill.feature_gate)。"""
        skill = self.get(skill_id)
        SettingsRepository().set(skill.feature_gate, True)

    def disable(self, skill_id: str) -> None:
        """停用: settings kv 写 False (与 enable 对称, 显式覆盖默认态)。"""
        skill = self.get(skill_id)
        SettingsRepository().set(skill.feature_gate, False)

    def __len__(self) -> int:
        """注册数量 — 测试与启动冒烟用。"""
        return len(self._skills)
