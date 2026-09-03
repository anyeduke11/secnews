"""agent_memory — v0.8 B3 (Phase B Task B3) agent 记忆包.

模块分层:
- ``memory.py`` — AgentMemoryService (record_feedback / recall /
  mine_preferences / active_preferences) + MemoryHit / Preference dataclass
- ``recall.py`` — MemoryRecall 三路混合召回 (关键词 LIKE / simhash / skill_id 精确)
- ``miner.py``  — PreferenceMiner 规则化偏好挖掘 (avoid_skill /
  prefer_runner / prefer_style → agent_preferences 幂等落库)

**v1 兼容层**: ``backend/services/user_memory_service.py`` (v1 CRUD 薄壳)
文件本体不动; 其全部公开名 (``UserMemoryService`` / ``user_memory_service``)
在本包 re-export, ``from backend.services.agent_memory import user_memory_service``
与既有 ``from backend.services.user_memory_service import user_memory_service``
两条路径同一对象, 既有调用者 (feedback_analyzer / feedback_service) 零改动。
"""
from __future__ import annotations

# v2 符号
from backend.services.agent_memory.memory import (
    AgentMemoryService,
    MemoryHit,
    Preference,
)
from backend.services.agent_memory.miner import PreferenceMiner
from backend.services.agent_memory.recall import MemoryRecall

# v1 兼容转发 — user_memory_service.py 本体不删不改,
# 两条 import 路径 (包转发 / 原模块) 永远拿到同一 class + 同一单例。
from backend.services import user_memory_service as _v1

UserMemoryService = _v1.UserMemoryService
user_memory_service = _v1.user_memory_service

# 模块级单例 — 沿用仓库惯例 (trigger_gate / ai_hub 同款):
# 调用方一律 ``from backend.services.agent_memory import agent_memory``
agent_memory = AgentMemoryService()

__all__ = [
    "AgentMemoryService",
    "MemoryHit",
    "MemoryRecall",
    "Preference",
    "PreferenceMiner",
    "UserMemoryService",
    "agent_memory",
    "user_memory_service",
]
