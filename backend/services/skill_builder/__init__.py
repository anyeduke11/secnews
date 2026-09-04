"""skill_builder — v0.8 Phase C C3 (用户自建 Skill).

模块分层 (按 spec tasks C3.1):
- ``core.py``   — UserSkill 数据类 + UserSkillRepo (CRUD + 软删 + 上限 50)
- ``schema.py`` — input/output schema JSON ↔ dict 转换 + 校验
- ``validate.py`` — id 命名 / target importlib.find_spec / target_method 存在 / A/B/E 类无 prompt / C/D 类有 prompt / 不与 builtin 20 id 冲突 / runner 仅 builtin (Phase C 范围)

对外契约:
- validate_user_skill(payload) → ValidationReport (errors/warnings)
- UserSkillRepo().create/update/soft_delete/list_active/get/...

边界 (V0.8_REFACTOR_PLAN.md §3):
- 上限 50 (create 超限 → ValueError)
- 软删 (deleted_at 标记, 不真删; 重建不冲突已删 id)
- target 仅 builtin (Phase C 不开放 pi/claude-code/codex, P1-6)
- E 类操作型 v0.8 不开放 (loader 拒绝)
- A/B/E 类不允许 prompt_template (R1 纪律 3)
- C/D 类必填 prompt_template
"""
from __future__ import annotations

from backend.services.skill_builder.core import (
    MAX_USER_SKILLS,
    UserSkill,
    UserSkillRepo,
)
from backend.services.skill_builder.schema import (
    parse_schema,
    serialize_schema,
    validate_schema_shape,
)
from backend.services.skill_builder.validate import (
    validate_user_skill,
    builtin_skill_ids,
)

__all__ = [
    "MAX_USER_SKILLS",
    "UserSkill",
    "UserSkillRepo",
    "builtin_skill_ids",
    "parse_schema",
    "serialize_schema",
    "validate_schema_shape",
    "validate_user_skill",
]