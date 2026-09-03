"""skill_registry — v0.8 Skill 注册子包 (Phase A).

A2a (当前) 只落地 abstractor 反模式 linter;
core/builtin (SkillDef 契约 + 20 内置 skill 静态注册) 由 A2b 扩展,
届时在此追加导出 — 原则先行, 实现后置 (docs/V0.8_SKILL_ABSTRACTION.md §6)。
"""
from __future__ import annotations

from backend.services.skill_registry.abstractor import (
    AbstractorVerdict,
    AntiPatternFinding,
    SkillCandidate,
    check_candidate,
    find_anti_patterns,
)

__all__ = [
    "AbstractorVerdict",
    "AntiPatternFinding",
    "SkillCandidate",
    "check_candidate",
    "find_anti_patterns",
]
