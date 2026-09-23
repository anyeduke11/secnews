"""能力开关 API (2026-09-22 设置重构 P2 §4.3)。

路由清单
--------
- ``GET /api/settings/feature-gates``        16 gate 全量 (name/enabled/source/effective_scope)
- ``PUT /api/settings/feature-gates/{name}`` 写 TOML + audit_log; env 覆盖时 409

source 语义: default=白名单默认 / toml=TOML 显式 / env=HOTSPOT_FEATURE_GATES 覆盖 (TOML 写入无效)。
effective_scope: runtime=5s TTL 热重载即生效 / startup=需重启 (路由注册/job 调度为启动快照)。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/settings", tags=["feature-gates"])

# 路由注册依赖该 gate 的扩展域 (启动快照语义); security_graph 等仅占 job 的 gate 也算 startup
_STARTUP_SCOPED = {
    "codegarden", "codegarden_phase2b", "mcp", "sync", "dsh",
    "secnews", "info_filter", "skill_registry", "user_skills",
    "trigger_gate", "tech_stack",
}


class GateToggleRequest(BaseModel):
    enabled: bool = Field(..., description="true=启用, false=停用")


def _list_gates() -> dict:
    import backend.extensions as ext

    overrides = ext.env_overrides()  # {"extensions": {...}} 或 {}
    env_keys = set((overrides.get("extensions") or {}).keys())
    items = []
    for name in ext.extension_names():
        enabled = ext.is_extension_enabled(name)
        source = "env" if name in env_keys else (
            "toml" if name in ext.toml_explicit_keys() else "default"
        )
        items.append({
            "name": name,
            "enabled": enabled,
            "source": source,
            "effective_scope": "startup" if name in _STARTUP_SCOPED else "runtime",
        })
    return {"version": API_VERSION, "count": len(items), "items": items}


def _set_gate(name: str, enabled: bool) -> dict:
    import backend.extensions as ext

    if name not in ext.extension_names():
        raise HTTPException(status_code=404, detail={"message": f"未知 gate: {name}"})
    if name in (ext.env_overrides().get("extensions") or {}):
        raise HTTPException(
            status_code=409,
            detail={"message": f"{name} 被 HOTSPOT_FEATURE_GATES 环境变量覆盖, TOML 写入无效; 请改 env 后重启"},
        )
    ext.set_toml_gate(name, enabled)  # 写 TOML (保留其他键 + 行内注释, .bak 备份一次)
    from backend.observability_records import record_audit

    record_audit(
        "web",
        "feature_gate.set",
        target=name,
        detail={"gate": name, "enabled": enabled},
    )
    return {"version": API_VERSION, "name": name, "enabled": enabled,
            "note": "运行时读数 5s 内生效; 路由注册与 job 调度需重启后端"}


@router.get("/feature-gates")
async def list_feature_gates():
    return await asyncio.to_thread(_list_gates)


@router.put("/feature-gates/{name}")
async def set_feature_gate(name: str, req: GateToggleRequest):
    return await asyncio.to_thread(_set_gate, name, req.enabled)


__all__ = ["router"]
