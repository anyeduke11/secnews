"""v0.8 Phase C C3 — Skill Builder API (用户自建 skill).

路由清单
--------
- GET    /api/skill-builder                      — 列表 (category / type / enabled_only 过滤)
- POST   /api/skill-builder/validate             — 校验 payload (不落库)
- POST   /api/skill-builder                      — 创建 (上限 50 + 软删)
- GET    /api/skill-builder/{id}                 — 详情
- PATCH  /api/skill-builder/{id}                 — 修改 (含 enabled 启停)
- DELETE /api/skill-builder/{id}                 — 软删

错误信封 (P3-2): detail 三字段 ``{message, code, hint}``.

边界 (V0.8_REFACTOR_PLAN.md §3):
- 上限 50 (创建时校验; 删除不释放 50 配额 — 用户 cap 是"曾创建数")
- 软删 (deleted_at 标记, 不真删; 重建不冲突已删 id)
- 仅 builtin runner (Phase C 不开放 pi/claude-code/codex)
- E 操作型 v0.8 不开放
- A/B 类禁止 prompt_template; C/D 类必填
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.skill_builder import (
    MAX_USER_SKILLS,
    UserSkill,
    UserSkillRepo,
    parse_schema,
    serialize_schema,
    validate_user_skill,
)

router = APIRouter(prefix="/api/skill-builder", tags=["skill-builder"])

_repo = UserSkillRepo()


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------
class SkillCreateRequest(BaseModel):
    """创建用户 skill 完整 payload."""

    id: str = Field(min_length=3, max_length=64)
    name: str
    desc: str = ""
    category: str
    skill_type: str
    runner: str = "builtin"
    timeout_seconds: int = 60
    input_schema: dict[str, str] | str | None = None
    output_schema: dict[str, str] | str | None = None
    prompt_template: str | None = None
    target_module: str
    target_class: str | None = None
    target_method: str


class SkillPatchRequest(BaseModel):
    """修改 (任意字段可选)."""

    name: str | None = None
    desc: str | None = None
    category: str | None = None
    skill_type: str | None = None
    runner: str | None = None
    timeout_seconds: int | None = None
    input_schema: dict[str, str] | str | None = None
    output_schema: dict[str, str] | str | None = None
    prompt_template: str | None = None
    target_module: str | None = None
    target_class: str | None = None
    target_method: str | None = None
    enabled: int | None = None


class ValidateRequest(BaseModel):
    """仅校验 (不落库)."""

    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _http_error(status: int, message: str, code: str, hint: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"message": message, "code": code, "hint": hint},
    )


def _serialize(skill: UserSkill) -> dict[str, Any]:
    out = skill.to_dict()
    # 反序列化 schema 供前端
    out["input_schema"] = parse_schema(skill.input_schema_json)
    out["output_schema"] = parse_schema(skill.output_schema_json)
    return out


def _to_obj(payload: SkillCreateRequest, *, created_by: str = "user") -> UserSkill:
    """Pydantic payload → UserSkill dataclass (校验由 validate_user_skill 负责)."""
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    return UserSkill(
        id=payload.id,
        name=payload.name,
        desc=payload.desc or "",
        category=payload.category,
        skill_type=payload.skill_type,
        runner=payload.runner,
        timeout_seconds=payload.timeout_seconds,
        input_schema_json=serialize_schema(parse_schema(payload.input_schema)),
        output_schema_json=serialize_schema(parse_schema(payload.output_schema)),
        prompt_template=payload.prompt_template,
        target_type="skill_step",  # Phase C 唯一允许
        target_module=payload.target_module,
        target_class=payload.target_class,
        target_method=payload.target_method,
        enabled=0,  # 默认未启用, 用户主动 PATCH 启停
        created_by=created_by,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@router.get("")
def list_skills(
    category: str | None = None,
    skill_type: str | None = None,
    enabled_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    items = _repo.list_active(
        category=category,
        skill_type=skill_type,
        enabled_only=enabled_only,
        limit=limit,
    )
    return {
        "items": [_serialize(s) for s in items],
        "total": len(items),
        "max": MAX_USER_SKILLS,
    }


@router.post("/validate")
def validate_only(req: ValidateRequest) -> dict[str, Any]:
    """仅校验 — 前端 Skill Builder 第 3 步 dry-run."""
    report = validate_user_skill(req.payload)
    return report.to_dict()


@router.post("")
def create_skill(req: SkillCreateRequest) -> dict[str, Any]:
    payload = req.model_dump()
    report = validate_user_skill(payload)
    if not report.ok:
        raise _http_error(
            422,
            f"user skill validate failed: {'; '.join(report.errors)}",
            "VALIDATE_FAILED",
            "修正字段后重试 (id 命名/target 引用/schema 形态)",
        )

    # 上限 50 + 软删占位: 复用 repo.create 的二次校验
    if _repo.count_active() >= MAX_USER_SKILLS:
        raise _http_error(
            422,
            f"用户 skill 已达上限 {MAX_USER_SKILLS}, 不能再创建",
            "LIMIT_EXCEEDED",
            "软删旧 skill 释放空间 (上限计算包含软删)",
        )
    if _repo.get(req.id, include_deleted=True) is not None:
        raise _http_error(
            409,
            f"skill id {req.id!r} 已存在 (含软删)",
            "DUPLICATE_ID",
            "选新 id 或恢复软删 skill",
        )

    try:
        skill = _repo.create(_to_obj(req))
    except ValueError as e:
        raise _http_error(409, str(e), "REPO_CREATE_FAILED", "检查 id 与上限") from None
    return _serialize(skill)


@router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict[str, Any]:
    skill = _repo.get(skill_id)
    if skill is None:
        raise _http_error(
            404, f"user skill {skill_id!r} 不存在", "NOT_FOUND", "检查 id 是否拼错或已软删"
        )
    return _serialize(skill)


@router.patch("/{skill_id}")
def patch_skill(skill_id: str, req: SkillPatchRequest) -> dict[str, Any]:
    try:
        updated = _repo.update(
            skill_id,
            **req.model_dump(exclude_none=True),
        )
    except ValueError as e:
        raise _http_error(404, str(e), "NOT_FOUND", "检查 id") from None
    return _serialize(updated)


@router.delete("/{skill_id}")
def delete_skill(skill_id: str) -> dict[str, Any]:
    ok = _repo.soft_delete(skill_id)
    if not ok:
        raise _http_error(
            404,
            f"user skill {skill_id!r} 不存在或已软删",
            "NOT_FOUND",
            "GET 列表确认 id 后重试",
        )
    return {"deleted": True, "id": skill_id}