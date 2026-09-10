"""v1.0 T14 Skill Registry v1 API (contracts §T14 §1 第 2 点).

路由清单 (前缀 /api/skill-registry/v1)
--------
- ``GET  /api/skill-registry/v1``            列表 (query: status=v1_active|legacy_v0|deprecated, category)
- ``GET  /api/skill-registry/v1/{skill_id}`` 详情 (含 prompt_template + version + status + manifest_path)

错误
----
- ``E_NOT_FOUND`` (404) — id 不存在
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.services.skill_registry.builtin import BUILTIN
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/skill-registry/v1", tags=["v1-skill-registry"])


def _json_schema(schema: dict[str, Any]) -> dict[str, str]:
    """SkillDef 契约里 schema 值是 Python type 对象, jsonable_encoder 遇到会 ValueError → 转类型名 (与 legacy API 同口径)."""
    return {k: getattr(v, "__name__", str(v)) for k, v in schema.items()}


def _skill_to_dict(s: Any) -> dict[str, Any]:
    """SkillDef → JSON (v1 字段展开)."""
    target = None
    if s.target is not None:
        if hasattr(s.target, "module") and hasattr(s.target, "class_name"):
            target = {
                "type": "ServiceTarget",
                "module": s.target.module,
                "class_name": s.target.class_name,
                "method": s.target.method,
            }
        else:
            target = {
                "type": "ApiTarget",
                "path": getattr(s.target, "path", None),
            }
    return {
        "id": s.id,
        "name": s.name,
        "desc": s.desc,
        "category": s.category,
        "skill_type": s.skill_type,
        "target": target,
        "prompt_template": s.prompt_template,
        "input_schema": _json_schema(s.input_schema),
        "output_schema": _json_schema(s.output_schema),
        "runner": s.runner,
        "timeout_seconds": s.timeout_seconds,
        "feature_gate": s.feature_gate,
        "default_enabled": s.default_enabled,
        "requires_gate_check": s.requires_gate_check,
        "version": getattr(s, "version", "0.9.0"),
        "status": getattr(s, "status", "legacy_v0"),
        "manifest_path": getattr(s, "manifest_path", None),
    }


def _list(
    status: str | None = None, category: str | None = None,
) -> dict[str, Any]:
    items = BUILTIN.list(category=category if category else None)
    if status:
        items = [s for s in items if getattr(s, "status", "legacy_v0") == status]
    return {
        "version": API_VERSION,
        "items": [_skill_to_dict(s) for s in items],
        "total": len(items),
    }


def _get(skill_id: str) -> dict[str, Any]:
    try:
        s = BUILTIN.get(skill_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": f"skill {skill_id} not found: {e}"})
    return {"version": API_VERSION, "item": _skill_to_dict(s)}


@router.get("", response_model=None)
async def list_v1_skills(
    status: str | None = Query(None, pattern="^(v1_active|legacy_v0|deprecated)$"),
    category: str | None = Query(None),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, status, category)


@router.get("/{skill_id}", response_model=None)
async def get_v1_skill(skill_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, skill_id)
