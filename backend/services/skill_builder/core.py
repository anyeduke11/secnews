"""skill_builder.core — UserSkill 数据类 + UserSkillRepo (CRUD + 软删 + 上限 50)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.repository.db import get_connection

MAX_USER_SKILLS = 50


@dataclass
class UserSkill:
    """用户自建 skill 完整记录 (与 builtin SkillDef 字段镜像 + 元数据).

    fields:
        id:                snake_case 用户自定义 (≥3 字符)
        name / desc:       UI 展示
        category:          operations/compliance/analysis/report
        skill_type:        A/B/C/D (E 拒绝, R1)
        runner:            builtin (Phase C 范围)
        timeout_seconds:   1-3600 (SkillRunner 跑 timeout)
        input_schema_json: JSON string (key → type name)
        output_schema_json: JSON string
        prompt_template:   仅 C/D; A/B 拒绝
        target_type:       'skill_step' (Phase C 唯一允许)
        target_module:     module path (loader find_spec 校验)
        target_class:      optional (None → 模块级函数)
        target_method:     method name (loader 校验存在)
        enabled:           0/1 软启用 (与 builtin 同, settings.kv 父 gate)
        created_by / created_at / updated_at / deleted_at: 审计
    """

    id: str
    name: str
    desc: str
    category: str
    skill_type: str
    runner: str
    timeout_seconds: int
    input_schema_json: str
    output_schema_json: str
    prompt_template: str | None
    target_type: str
    target_module: str
    target_class: str | None
    target_method: str
    enabled: int
    created_by: str
    created_at: str
    updated_at: str
    deleted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {**self.__dict__}
        # 反序列化 schema 字段供前端 (snake_case 已是契约)
        return out

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None


class UserSkillRepo:
    """user_skills 表 DAO — 单表平铺, 软删 (deleted_at 标记), 写幂等."""

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        return dict(row)

    def create(self, skill: UserSkill) -> UserSkill:
        """创建用户 skill; 违反上限 / id 冲突 / 软删占位 → ValueError."""
        if self.count_active() >= MAX_USER_SKILLS:
            raise ValueError(f"用户 skill 已达上限 {MAX_USER_SKILLS}, 不能再创建")
        if self.get(skill.id, include_deleted=True) is not None:
            raise ValueError(f"skill id {skill.id!r} 已存在 (含软删)")
        conn = get_connection()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO user_skills(
                id, name, desc, category, skill_type, runner, timeout_seconds,
                input_schema_json, output_schema_json, prompt_template,
                target_type, target_module, target_class, target_method,
                enabled, created_by, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                skill.id,
                skill.name,
                skill.desc,
                skill.category,
                skill.skill_type,
                skill.runner,
                skill.timeout_seconds,
                skill.input_schema_json,
                skill.output_schema_json,
                skill.prompt_template,
                skill.target_type,
                skill.target_module,
                skill.target_class,
                skill.target_method,
                skill.enabled,
                skill.created_by,
                now,
                now,
            ),
        )
        return self.get_or_raise(skill.id)

    def get(self, skill_id: str, *, include_deleted: bool = False) -> UserSkill | None:
        conn = get_connection()
        if include_deleted:
            row = conn.execute(
                "SELECT * FROM user_skills WHERE id = ?", (skill_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM user_skills WHERE id = ? AND deleted_at IS NULL",
                (skill_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_obj(row)

    def get_or_raise(self, skill_id: str) -> UserSkill:
        s = self.get(skill_id)
        if s is None:
            raise ValueError(f"user skill {skill_id!r} 不存在")
        return s

    def list_active(
        self,
        *,
        category: str | None = None,
        skill_type: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> list[UserSkill]:
        conn = get_connection()
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if skill_type is not None:
            clauses.append("skill_type = ?")
            params.append(skill_type)
        if enabled_only:
            clauses.append("enabled = 1")
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM user_skills WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC, id LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_obj(r) for r in rows]

    def count_active(self) -> int:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM user_skills WHERE deleted_at IS NULL"
        ).fetchone()
        return int(row["c"])

    def update(
        self,
        skill_id: str,
        *,
        name: str | None = None,
        desc: str | None = None,
        category: str | None = None,
        skill_type: str | None = None,
        runner: str | None = None,
        timeout_seconds: int | None = None,
        input_schema_json: str | None = None,
        output_schema_json: str | None = None,
        prompt_template: str | None = None,
        target_module: str | None = None,
        target_class: str | None = None,
        target_method: str | None = None,
        enabled: int | None = None,
    ) -> UserSkill:
        existing = self.get_or_raise(skill_id)
        now = datetime.now().isoformat(timespec="seconds")
        fields: dict[str, Any] = {"updated_at": now}
        if name is not None:
            fields["name"] = name
        if desc is not None:
            fields["desc"] = desc
        if category is not None:
            fields["category"] = category
        if skill_type is not None:
            fields["skill_type"] = skill_type
        if runner is not None:
            fields["runner"] = runner
        if timeout_seconds is not None:
            fields["timeout_seconds"] = timeout_seconds
        if input_schema_json is not None:
            fields["input_schema_json"] = input_schema_json
        if output_schema_json is not None:
            fields["output_schema_json"] = output_schema_json
        if prompt_template is not None:
            fields["prompt_template"] = prompt_template
        if target_module is not None:
            fields["target_module"] = target_module
        if target_class is not None:
            fields["target_class"] = target_class
        if target_method is not None:
            fields["target_method"] = target_method
        if enabled is not None:
            fields["enabled"] = enabled

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [skill_id]
        conn = get_connection()
        conn.execute(
            f"UPDATE user_skills SET {set_clause} WHERE id = ?", params
        )
        _ = existing  # silence unused
        return self.get_or_raise(skill_id)

    def soft_delete(self, skill_id: str) -> bool:
        """软删 (deleted_at 标记); 重复删返 False."""
        conn = get_connection()
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "UPDATE user_skills SET deleted_at = ?, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (now, now, skill_id),
        )
        return cur.rowcount > 0

    def _row_to_obj(self, row: Any) -> UserSkill:
        d = self._row_to_dict(row)
        return UserSkill(**d)


__all__ = ["MAX_USER_SKILLS", "UserSkill", "UserSkillRepo"]