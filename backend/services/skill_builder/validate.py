"""skill_builder.validate — 用户 skill 校验 (loader 风格).

校验范围 (按 R1/R7/R8 + C3 spec):
- id 命名: snake_case, ≥3 字符, 不与 builtin 20 冲突
- category: 4 选 1
- skill_type: 4 选 1 (A/B/C/D, E 操作型 v0.8 不开放)
- runner: builtin only (Phase C 范围)
- timeout: 1-3600
- prompt_template: A/B 拒绝; C/D 必填
- target 引用: importlib.find_spec(module) + getattr(class, method) 存在
- schema shape: snake_case 字段 + 合法 type 名
"""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from typing import Any

from backend.logging_config import logger

#: id 命名: snake_case 或 kebab-case (与 builtin 20 风格兼容); 长度 3-64
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")

#: enum 校验白名单
_CATEGORIES = frozenset({"operations", "compliance", "analysis", "report"})
_TYPES = frozenset({"A", "B", "C", "D"})
_RUNNERS = frozenset({"builtin"})


@dataclass
class ValidationReport:
    """校验报告 — 复用 playbook_engine 的 entry 风格 (errors 阻止保存)."""

    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors)}


def builtin_skill_ids() -> set[str]:
    """列出当前已注册 builtin skill id (20 个 + user_skills 中活跃 id 也算).

    注: C3 不去重 union user_skills (避免循环), 调用方需先调用 validate_user_skill
    再判断 id 是否与 user_skills 重复 (由 repo.create 抛错).
    """
    from backend.services.skill_registry.builtin import BUILTIN

    return {s.id for s in BUILTIN.list()}


def validate_user_skill(payload: dict[str, Any]) -> ValidationReport:
    """校验用户提交 payload; 返回 errors 列表 (空 = ok)."""
    errors: list[str] = []

    # id 命名
    sid = payload.get("id") or ""
    if not isinstance(sid, str):
        errors.append("id 必须是字符串")
    elif not _ID_RE.match(sid):
        errors.append(f"id {sid!r} 非法 (snake_case, 3-64 字符, 首字符小写字母)")
    elif sid in builtin_skill_ids():
        errors.append(f"id {sid!r} 与 builtin skill 冲突 (R8: 不允许覆盖)")

    # name / desc
    if not payload.get("name") or not isinstance(payload["name"], str):
        errors.append("name 必填且为字符串")
    if "desc" in payload and payload["desc"] is not None and not isinstance(payload["desc"], str):
        errors.append("desc 必须为字符串或 null")

    # category
    category = payload.get("category")
    if category not in _CATEGORIES:
        errors.append(f"category {category!r} 不在白名单内 ({sorted(_CATEGORIES)})")

    # skill_type
    skill_type = payload.get("skill_type")
    if skill_type not in _TYPES:
        errors.append(f"skill_type {skill_type!r} 不在白名单内 ({sorted(_TYPES)}); E 操作型 v0.8 不开放")

    # runner
    runner = payload.get("runner", "builtin")
    if runner not in _RUNNERS:
        errors.append(f"runner {runner!r} 不支持 (Phase C 仅 builtin)")

    # timeout
    timeout = payload.get("timeout_seconds", 60)
    if not isinstance(timeout, int) or not (1 <= timeout <= 3600):
        errors.append(f"timeout_seconds {timeout!r} 必须在 [1, 3600]")

    # prompt_template: A/B 拒绝; C/D 必填
    prompt = payload.get("prompt_template")
    if skill_type in ("A", "B"):
        if prompt:
            errors.append(f"skill_type={skill_type} 不允许 prompt_template (R1 纪律 3)")
    elif skill_type in ("C", "D"):
        if not (isinstance(prompt, str) and prompt.strip()):
            errors.append(f"skill_type={skill_type} 必填 prompt_template (R1 纪律 3)")

    # target 引用 (R8 + P4-7 风格: 只引用已存在的方法, 不执行任何逻辑)
    module = payload.get("target_module")
    method = payload.get("target_method")
    target_class = payload.get("target_class") or None
    if not isinstance(module, str) or not isinstance(method, str):
        errors.append("target_module / target_method 必填且为字符串")
    else:
        # module 存在性
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ModuleNotFoundError, ValueError) as e:
            spec = None
            errors.append(f"target_module {module!r} 不可导入: {e}")
        if spec is not None:
            # method 存在性
            try:
                mod = importlib.import_module(module)
                cls = None
                if target_class:
                    cls = getattr(mod, target_class, None)
                    if cls is None:
                        errors.append(f"target_class {target_class!r} 不在 {module!r} 中")
                obj = cls if cls is not None else mod
                if not hasattr(obj, method):
                    target_label = f"{module}.{target_class}.{method}" if target_class else f"{module}.{method}"
                    errors.append(f"target_method {target_label} 不存在")
            except Exception as e:  # noqa: BLE001 — 校验边界, 上层收口
                errors.append(f"target 引用失败: {e}")

    # input/output schema shape (允许空 — 简化自定义场景)
    from backend.services.skill_builder.schema import validate_schema_shape

    for field_name in ("input_schema", "output_schema"):
        raw = payload.get(field_name)
        if raw is None or raw == "":
            continue
        if isinstance(raw, str):
            import json as _json

            try:
                parsed = _json.loads(raw)
            except (TypeError, ValueError) as e:
                errors.append(f"{field_name} JSON 解析失败: {e}")
                continue
        elif isinstance(raw, dict):
            parsed = raw
        else:
            errors.append(f"{field_name} 类型必须是 dict 或 JSON string")
            continue
        # shape
        for err in validate_schema_shape(parsed, allow_empty=True):
            errors.append(f"{field_name}: {err}")

    return ValidationReport(errors=errors)


__all__ = ["ValidationReport", "builtin_skill_ids", "validate_user_skill"]