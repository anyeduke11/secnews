"""v0.8 Phase A (A3) — skill_registry Skill 商店 API (预注册态).

路由清单
--------
- GET  /api/skill-registry                      — 列表 (category / enabled_only 过滤)
- GET  /api/skill-registry/{skill_id}           — 详情 (schema + C/D 类 prompt 全文)
- POST /api/skill-registry/{skill_id}/enable    — 启用 (写 settings kv)
- POST /api/skill-registry/{skill_id}/disable   — 停用 (写 settings kv)
- POST /api/skill-registry/{skill_id}/run       — 触发 (trigger-gate 入队, 不执行)

命名偏离声明: plan §6 A3 原定 ``/api/skills`` + ``api/skills.py``, 但两者均已被
Phase 41 skill 书签 CRUD 占用 (core 路由, GET /api/skills 同路径先注册必遮蔽;
前端 SkillsPage 在用, 不可替换)。按 info_filter → ``/api/info-filter`` 先例
改为 ``/api/skill-registry`` (gate 名 snake → 路径 kebab)。

run 端点预注册态: 只做「启用检查 → trigger-gate 入队」不执行 (runner 接线
是 B5); 返回 ticket_id ≠ 已执行。错误信封 (P3-2): detail 三字段必填
``{message, code, hint}``, 429 额外携带 ``retry_after_seconds``。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.skill_registry import BUILTIN, SkillDef, SkillNotFoundError, is_skill_enabled
from backend.services.trigger_gate import Priority, ThrottleExceededError, trigger_gate

router = APIRouter(prefix="/api/skill-registry", tags=["skill-registry"])

#: 携带 prompt_template 的类型 (§2 分类法: C 报告 / D 分析); A/B/E 类禁止
_PROMPT_TYPES = frozenset({"C", "D"})


#: run 端点请求体 — inputs 为 skill 入参 (runner 渲染 ``{{ input.x }}``)
class RunSkillRequest(BaseModel):
    inputs: dict[str, Any] | None = None


def _http_error(status: int, message: str, code: str, hint: str, **extra: Any) -> HTTPException:
    """统一错误信封 — detail 三字段必填 (P3-2), extra 附补充键 (如 retry_after)。"""
    return HTTPException(
        status_code=status, detail={"message": message, "code": code, "hint": hint, **extra}
    )


def _skill_not_found(skill_id: str) -> HTTPException:
    """未知 skill_id 的标准 404 — get/enable/disable/run 四端点共用。"""
    return _http_error(
        404, f"skill not found: {skill_id!r}", "SKILL_NOT_FOUND",
        "GET /api/skill-registry 列出全部可用 skill id",
    )


def _json_schema(schema: dict) -> dict:
    """schema 值的类型对象 → 类型名 — SkillDef 契约存 Python type, JSON 不认。"""
    return {k: getattr(v, "__name__", str(v)) for k, v in schema.items()}


def _summary(skill: SkillDef) -> dict:
    """列表项序列化 — 不含 prompt_template 全文, C/D 类只给 has_prompt 标志。"""
    return {
        "id": skill.id, "name": skill.name, "desc": skill.desc,
        "category": skill.category, "skill_type": skill.skill_type,
        "runner": skill.runner, "timeout_seconds": skill.timeout_seconds,
        "feature_gate": skill.feature_gate, "default_enabled": skill.default_enabled,
        "enabled": is_skill_enabled(skill.id),
        "has_prompt": skill.skill_type in _PROMPT_TYPES,
    }


def _detail(skill: SkillDef) -> dict:
    """详情序列化 — 列表项全字段 + input/output schema; C/D 类附 prompt 全文。"""
    data = _summary(skill)
    data["input_schema"] = _json_schema(skill.input_schema)
    data["output_schema"] = _json_schema(skill.output_schema)
    if skill.skill_type in _PROMPT_TYPES:
        data["prompt_template"] = skill.prompt_template
    return data


@router.get("")
def list_skills(category: str | None = None, enabled_only: bool = False) -> list[dict]:
    """列表 — category 过滤 (operations/compliance/analysis/report) + enabled_only
    (kv AND 父 gate); 保持注册顺序 (前端卡片顺序稳定)。"""
    return [_summary(s) for s in BUILTIN.list(category=category, enabled_only=enabled_only)]


@router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict:
    """详情 — 含 input_schema / output_schema (类型名); C/D 类含 prompt_template。"""
    try:
        return _detail(BUILTIN.get(skill_id))
    except SkillNotFoundError:
        raise _skill_not_found(skill_id) from None


@router.post("/{skill_id}/enable")
def enable_skill(skill_id: str) -> dict:
    """启用 — settings kv 写 True (key = skill.feature_gate); 幂等。"""
    try:
        BUILTIN.enable(skill_id)
    except SkillNotFoundError:
        raise _skill_not_found(skill_id) from None
    return {"enabled": True}


@router.post("/{skill_id}/disable")
def disable_skill(skill_id: str) -> dict:
    """停用 — settings kv 写 False (显式覆盖默认态); 与 enable 对称。"""
    try:
        BUILTIN.disable(skill_id)
    except SkillNotFoundError:
        raise _skill_not_found(skill_id) from None
    return {"enabled": False}


@router.post("/{skill_id}/run")
def run_skill(skill_id: str, req: RunSkillRequest | None = None) -> dict:
    """触发一次 skill — **Phase A 预注册态: 仅入队不执行** (B5 接线 runner)。
    编排: 404 未知 id → 409 SKILL_DISABLED → trigger_gate.submit
    (REALTIME / manual) → 200 ``{"ticket_id": "tg-..."}``;
    ThrottleExceededError → 429 (THROTTLED, 含 retry_after_seconds, 票据不落库)。
    """
    try:
        BUILTIN.get(skill_id)
    except SkillNotFoundError:
        raise _skill_not_found(skill_id) from None
    if not is_skill_enabled(skill_id):
        raise _http_error(
            409, f"skill {skill_id!r} 未启用", "SKILL_DISABLED",
            f"先 POST /api/skill-registry/{skill_id}/enable 再触发",
        )
    try:
        ticket = trigger_gate.submit(
            target_type="skill", target_id=skill_id, source="manual",
            inputs=req.inputs if req is not None else None,
            priority=Priority.REALTIME,
        )
    except ThrottleExceededError as e:
        raise _http_error(
            429, f"触发过于频繁: {e}", "THROTTLED",
            "等待 retry_after_seconds 后重试 (限流 60 次/分/用户 + 600 次/分全局)",
            retry_after_seconds=e.retry_after_seconds,
        ) from None
    return {"ticket_id": ticket.ticket_id}


__all__ = ["router"]
