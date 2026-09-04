"""skill_registry.gate — skill 启停读数 (v0.8 Phase A · A2b).

判定公式: ``is_skill_enabled(id) = settings.kv(skill.<id>.enabled) AND
is_extension_enabled("skill_registry")``

父 gate 行为 (以 backend/extensions.py 代码实况为准, 2026-09-04 核对):
- ``is_extension_enabled`` 对未知名称**不抛 KeyError**, 而是按 fail-closed
  返回 False (``_load_gates().get(name, False)``, 见 extensions/__init__.py
  "未知名称按关闭处理 (fail-closed, 防漏登记即开放)")
- "skill_registry" 尚未登记进 ``_EXTENSION_NAMES`` / feature_gates.toml
  (A3/A5 任务), 因此当前父 gate 读数恒为 False → 所有 skill 读数为关。
  这是刻意的 fail-closed: 在全 API 无认证的单机工作站上, 漏登记的扩展
  不应意外开放。A3/A5 注册 gate 后父读数自然放开。
- 测试需验证 True 路径时 monkeypatch 本模块的 ``is_extension_enabled``。

kv 读数: 经 SettingsRepository (settings 表, migration 001) 读
``skill.feature_gate`` key; 未设置时回落 SkillDef.default_enabled
(当前全部 False)。
"""
from __future__ import annotations

from backend.extensions import is_extension_enabled
from backend.repository.settings_repo import SettingsRepository
from backend.services.skill_registry.builtin import BUILTIN
from backend.services.skill_registry.core import SkillDef

__all__ = ["is_skill_enabled"]


def is_skill_enabled(skill_id: str) -> bool:
    """skill 是否启用 — settings kv AND 父扩展 gate 联合读数。

    - 未知 skill_id 抛 SkillNotFoundError (调用方 bug, fail loud)
    - kv 未写 → 回落 skill.default_enabled (当前内置 20 个全 False)
    - 父 gate 关 → 恒 False, 无论 kv 写什么 (扩展域总开关优先)
    """
    skill: SkillDef = BUILTIN.get(skill_id)  # 未知 id 抛 SkillNotFoundError
    kv_value = SettingsRepository().get(skill.feature_gate, skill.default_enabled)
    return bool(kv_value) and is_extension_enabled("skill_registry")
