"""skill_registry — v0.8 Skill 注册子包 (Phase A).

模块分层:
- ``abstractor.py`` — 反模式 linter (A2a): R1/R2/R3 客观信号拦截, 不做分类
- ``core.py``       — SkillDef 统一契约 + Target 三兄弟 + SkillRegistry (A2b)
- ``loader.py``     — 启动加载校验 (六条规则 + 步骤结构, feature_gate 锁)
- ``builtin.py``    — 20 个内置 skill 静态注册 + BUILTIN 单例 (plan §4)
- ``gate.py``       — is_skill_enabled (settings kv AND 父 gate)

对外契约: 注册面走 ``builtin.BUILTIN`` (register 自带校验, 违规 import 期
爆炸); 启停读数走 ``gate.is_skill_enabled``; 候选审查走 ``check_candidate``。
原则文档: docs/V0.8_SKILL_ABSTRACTION.md (A2a 产物, 本包的约束源)。
"""
from __future__ import annotations

from backend.services.skill_registry.abstractor import (
    AbstractorVerdict,
    AntiPatternFinding,
    SkillCandidate,
    check_candidate,
    find_anti_patterns,
)
from backend.services.skill_registry.builtin import BUILTIN, BUILTIN_SKILLS
from backend.services.skill_registry.core import (
    ApiTarget,
    LlmTarget,
    ServiceTarget,
    SkillDef,
    SkillNotFoundError,
    SkillRegistry,
    SkillRegistryValidationError,
    Step,
)
from backend.services.skill_registry.gate import is_skill_enabled
from backend.services.skill_registry.loader import ValidationReport, load_validation

__all__ = [
    "BUILTIN",
    "BUILTIN_SKILLS",
    "AbstractorVerdict",
    "AntiPatternFinding",
    "ApiTarget",
    "LlmTarget",
    "ServiceTarget",
    "SkillCandidate",
    "SkillDef",
    "SkillNotFoundError",
    "SkillRegistry",
    "SkillRegistryValidationError",
    "Step",
    "ValidationReport",
    "check_candidate",
    "find_anti_patterns",
    "is_skill_enabled",
    "load_validation",
]
