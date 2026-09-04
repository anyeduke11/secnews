"""skill_builder.schema — input/output schema JSON ↔ dict 转换.

设计:
- ``schema`` 字段结构: ``{field_name: type_name_string}`` (与 builtin SkillDef 同).
- ``parse_schema`` 反序列化 JSON string → dict; 失败抛 ValueError (防坏 JSON).
- ``serialize_schema`` 反向.
- ``validate_schema_shape`` 字段名 / 类型名基本校验 (≥1 个字段 + Python type 名合法).
"""
from __future__ import annotations

import json
import re
from typing import Any

# Python builtin type 名白名单 — 与 builtin SkillDef loader 同口径 (loader.load_validation
# 不强制, 仅校验 dict 形态); 这里收紧避免用户提交 str/int/list/dict/custom 等之外的乱码.
_ALLOWED_TYPE_NAMES: frozenset[str] = frozenset(
    {"str", "int", "float", "bool", "list", "dict", "tuple", "Any", "None"}
)

_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def serialize_schema(schema: dict[str, str] | None) -> str:
    """dict → JSON string; 空 schema 返 '{}'."""
    if not schema:
        return "{}"
    return json.dumps(dict(schema), ensure_ascii=False)


def parse_schema(raw: str | dict | None) -> dict[str, str]:
    """JSON string OR dict → dict; 失败抛 ValueError (含具体字段)."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as e:
            raise ValueError(f"schema JSON 解析失败: {e}") from e
        if not isinstance(parsed, dict):
            raise ValueError("schema 必须是 JSON object")
        return {str(k): str(v) for k, v in parsed.items()}
    raise ValueError(f"schema 类型必须是 dict 或 JSON string, got {type(raw).__name__}")


def validate_schema_shape(schema: dict[str, str], *, allow_empty: bool = True) -> list[str]:
    """返回错误列表 (空 = ok).

    规则:
      - 空 schema 仅在 allow_empty=True 时允许
      - field name: snake_case 标识符 (与 builtin 一致)
      - type name: 在 _ALLOWED_TYPE_NAMES 白名单内
    """
    if not schema:
        return [] if allow_empty else ["schema 不能为空"]
    errs: list[str] = []
    for fname, tname in schema.items():
        if not isinstance(fname, str) or not _FIELD_NAME_RE.match(fname):
            errs.append(f"field name {fname!r} 非法 (必须 snake_case 标识符)")
        if not isinstance(tname, str):
            errs.append(f"field {fname!r} 的 type 必须为字符串")
        elif tname not in _ALLOWED_TYPE_NAMES:
            errs.append(f"field {fname!r} 的 type {tname!r} 不在白名单内 ({sorted(_ALLOWED_TYPE_NAMES)})")
    return errs


__all__ = ["parse_schema", "serialize_schema", "validate_schema_shape"]