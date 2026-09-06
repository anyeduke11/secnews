#!/usr/bin/env python3
"""
codegen_v1_ts — Pydantic v1.0 域模型 → TypeScript 单文件类型.

输出: frontend/src/domain/v1_0.ts (单文件, 所有 9 域对象 + EvidenceRef + Step).
CI:  --check 模式比较生成结果与已提交文件, 漂移则 exit 1.

依赖: 仅 stdlib + pydantic (已在 backend 依赖).
最佳实践:
  - 一文件前端类型 (frontend/src/domain/v1_0.ts) — 禁止从 Pydantic 镜像路径导入
  - 一类型一接口, snake_case (与 Pydantic model_dump(mode='json') 对齐)
  - datetime → string (ISO 8601 UTC, 服务端写)
  - enum → TS union literal, 带注释标注值来源
  - list[T] → T[], dict[str, V] → Record<string, V> 或 Record<string, unknown>

用法:
  python scripts/codegen_v1_ts.py                          # 写入 frontend/src/domain/v1_0.ts
  python scripts/codegen_v1_ts.py --check                   # CI 模式, 漂移则 exit 1
  python scripts/codegen_v1_ts.py --check --json            # JSON 报告 (CI 消费)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# repo root = scripts/..
REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Pydantic 导入 (延迟, 允许 standalone --check 时给清晰报错)
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel
except ImportError:
    print(
        "ERROR: pydantic 不可用. 在项目 venv 中运行: .venv/bin/python scripts/codegen_v1_ts.py",
        file=sys.stderr,
    )
    sys.exit(2)

# 延迟导入 v1_0_models (允许 --list-models 等无需 pydantic 的场景)
def _load_domain_models() -> dict[str, type[BaseModel]]:
    """按 contracts §1-§9 顺序导入 v1.0 域模型."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from domain.v1_0_models import (  # type: ignore[import]
        Action,
        Artifact,
        Case,
        EvidenceRef,
        Judgment,
        Knowledge,
        Material,
        Run,
        Signal,
        Step,
        Subject,
    )
    return {
        "EvidenceRef": EvidenceRef,
        "Step": Step,
        "Subject": Subject,
        "Material": Material,
        "Signal": Signal,
        "Case": Case,
        "Judgment": Judgment,
        "Action": Action,
        "Run": Run,
        "Artifact": Artifact,
        "Knowledge": Knowledge,
    }


# ---------------------------------------------------------------------------
# 类型映射规则 (contracts §0.2 + §5.4)
# ---------------------------------------------------------------------------
# datetime / date → ISO 8601 string (服务端写, 客户端只读)
_DATETIME_TYPES = {"datetime", "date"}

# 内置类型忽略前缀 (typing.Optional 等)
_OPTIONAL_PREFIX = "typing.Optional["
_LIST_SUFFIX = "list["
_DICT_SUFFIX = "dict[str, "


# ---------------------------------------------------------------------------
# Schema 提取 (Pydantic v2)
# ---------------------------------------------------------------------------
def _get_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """返回 Pydantic v2 model_json_schema() 结果."""
    return model.model_json_schema()


def _extract_properties(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """
    从 $defs / inline 拆出 properties + required.
    返回 (properties, title 或 None).
    """
    if schema.get("type") != "object":
        return {}, schema.get("title")
    return schema.get("properties", {}), schema.get("title")


# ---------------------------------------------------------------------------
# TS 类型生成
# ---------------------------------------------------------------------------
def _ts_type_for_field(
    field_name: str,
    field_schema: dict[str, Any],
    all_defs: dict[str, dict[str, Any]],
    indent: str = "  ",
) -> str:
    """
    把单个 JSON Schema 字段转 TypeScript 类型字符串.

    规则:
    - $ref → 递归取 ref 类型名
    - anyOf (Optional) → T | null 或 T | undefined
    - enum → 'a' | 'b' | 'c'  (加注释)
    - array → T[]
    - object (inline) → { ... } 或 已有 $defs 引用
    - 默认 → 按 contracts §0.2 处理
    """
    # ----- Optional: anyOf with null -----
    any_of = field_schema.get("anyOf", [])
    if any_of:
        non_null = [a for a in any_of if a.get("type") != "null"]
        if len(non_null) == 1 and len(any_of) == 2:
            inner = _ts_type_for_field(field_name, non_null[0], all_defs, indent)
            return f"{inner} | null"
        # 复杂 union (不常见) → 回退 any
        return "any"

    # ----- $ref (内嵌或 $defs) -----
    ref = field_schema.get("$ref")
    if ref:
        ref_name = ref.rsplit("/", 1)[-1]
        return ref_name

    # ----- enum -----
    if "enum" in field_schema:
        values = field_schema["enum"]
        # 过滤掉 None (should be handled by anyOf above, but just in case)
        str_values = [v for v in values if v is not None]
        if not str_values:
            return "string"
        # 如果是简单的值类型 (str/int), 生成 union literal
        if all(isinstance(v, str) for v in str_values):
            return " | ".join(f"'{v}'" for v in str_values)
        return " | ".join(repr(v) if not isinstance(v, str) else f"'{v}'" for v in str_values)

    # ----- array -----
    if field_schema.get("type") == "array":
        items = field_schema.get("items", {})
        item_type = _ts_type_for_field(field_name, items, all_defs, indent)
        return f"{item_type}[]"

    # ----- object (inline / $defs) -----
    if field_schema.get("type") == "object":
        additional = field_schema.get("additionalProperties")
        if isinstance(additional, dict):
            val_type = _ts_type_for_field(field_name, additional, all_defs, indent)
            return f"Record<string, {val_type}>"
        if additional is True:
            return "Record<string, unknown>"
        return "Record<string, unknown>"

    # ----- 基础类型 -----
    ts_type_map = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
    }
    ts_type = ts_type_map.get(field_schema.get("type", "any"), "any")
    return ts_type


def _generate_interface(
    model: type[BaseModel],
    all_defs: dict[str, dict[str, Any]],
) -> str:
    """生成单个 TS interface."""
    schema = _get_json_schema(model)
    properties, title = _extract_properties(schema)
    if title is None:
        title = model.__name__

    required: set[str] = set(schema.get("required", []))

    lines: list[str] = [f"export interface {model.__name__} {{"]
    for field_name, field_schema in properties.items():
        ts_type = _ts_type_for_field(field_name, field_schema, all_defs)
        optional = field_name not in required
        suffix = "?" if optional else ""
        # field description as comment
        desc = field_schema.get("description", "")
        if desc:
            lines.append(f"  /** {desc} */")
        lines.append(f"  {field_name}{suffix}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _generate_enum(name: str, values: list[str]) -> str:
    """生成 TS union type (用 type alias, 不是 enum)."""
    formatted = " | ".join(f"'{v}'" for v in values)
    return f"export type {name} = {formatted};"


def _generate_enums_ts(
    schema: dict[str, dict[str, Any]],
) -> str:
    """从 $defs 提取枚举生成 TS type."""
    lines: list[str] = []
    for def_name, def_schema in schema.get("$defs", {}).items():
        if def_schema.get("type") == "string" and "enum" in def_schema:
            lines.append(_generate_enum(def_name, def_schema["enum"]))
    return "\n".join(lines)


def _collect_all_defs(models: dict[str, type[BaseModel]]) -> dict[str, dict[str, Any]]:
    """合并所有模型的 $defs (Pydantic v2 每模型只含自身引用)."""
    merged: dict[str, dict[str, Any]] = {}
    for model in models.values():
        schema = model.model_json_schema()
        for name, defn in schema.get("$defs", {}).items():
            # 首次定义优先, 同名同构不覆盖
            if name not in merged:
                merged[name] = defn
    return merged


def generate_ts(models: dict[str, type[BaseModel]]) -> str:
    """
    生成完整 frontend/src/domain/v1_0.ts.

    输出顺序: contracts §1-§9 (Subject → Knowledge) + EvidenceRef + Step.
    """
    all_defs = _collect_all_defs(models)

    header = """\
/**
 * v1.0 域模型 — 由 scripts/codegen_v1_ts.py 自动生成 (Pydantic → TS).
 *
 * 单一真相源: backend/domain/v1_0_models.py
 * 字段命名: snake_case (与后端 Pydantic model_dump(mode='json') 对齐).
 * 时间字段: 全部 string (ISO 8601 UTC, 服务端写, 客户端只读).
 * 禁止手动编辑本文件; 改 Pydantic 模型后重新运行 codegen.
 */

"""

    # 1. 先排枚举 (按 $defs 字典序, 排除嵌套对象)
    enum_lines: list[str] = []
    for def_name, def_schema in sorted(all_defs.items()):
        if def_schema.get("type") == "string" and "enum" in def_schema:
            enum_lines.append(_generate_enum(def_name, def_schema["enum"]))
    enums_block = "\n\n".join(enum_lines)

    # 2. 接口按 contracts §1-§9 顺序
    interface_order = [
        "EvidenceRef",
        "Step",
        "Subject",
        "Material",
        "Signal",
        "Case",
        "Judgment",
        "Action",
        "Run",
        "Artifact",
        "Knowledge",
    ]
    interface_lines: list[str] = []
    for name in interface_order:
        model = models.get(name)
        if model is None:
            continue
        interface_lines.append(_generate_interface(model, all_defs))

    interfaces_block = "\n\n".join(interface_lines)

    # 3. 组合
    parts = [header]
    if enums_block:
        parts.append(enums_block)
        parts.append("")  # blank line
    parts.append(interfaces_block)
    parts.append("")  # trailing newline

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 文件 I/O + --check
# ---------------------------------------------------------------------------

def output_path() -> Path:
    return REPO_ROOT / "frontend" / "src" / "domain" / "v1_0.ts"


def write_file(content: str) -> Path:
    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def do_check(models: dict[str, type[BaseModel]], json_output: bool = False) -> bool:
    """
    --check: 比较生成内容与已提交文件.
    返回 True = 一致 (通过), False = 漂移 (CI 应 exit 1).
    """
    path = output_path()
    if not path.exists():
        if json_output:
            print(
                json.dumps({"ok": False, "reason": "file_missing", "path": str(path)})
            )
        print(f"FAIL: {path} 不存在 (需先运行 scripts/codegen_v1_ts.py)", file=sys.stderr)
        return False

    generated = generate_ts(models)
    current = path.read_text(encoding="utf-8")

    if generated == current:
        if json_output:
            print(json.dumps({"ok": True, "path": str(path)}))
        else:
            print(f"OK: {path} 与 Pydantic 模型一致 (SHA256 {file_sha256(path)[:16]}…)")
        return True

    # 漂移
    gen_hash = hashlib.sha256(generated.encode()).hexdigest()[:16]
    cur_hash = hashlib.sha256(current.encode()).hexdigest()[:16]
    if json_output:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "drift",
                    "path": str(path),
                    "generated_sha256_prefix": gen_hash,
                    "committed_sha256_prefix": cur_hash,
                }
            )
        )
    else:
        print(
            f"FAIL: {path} 与 Pydantic 模型漂移\n"
            f"  generated: {gen_hash}…\n"
            f"  committed: {cur_hash}…\n"
            f"  修复: .venv/bin/python scripts/codegen_v1_ts.py && git add frontend/src/domain/v1_0.ts",
            file=sys.stderr,
        )
    return False


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pydantic v1.0 域模型 → TypeScript 单文件类型生成器"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI 模式: 比较生成结果与已提交文件, 漂移则 exit 1",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="--check 时输出 JSON 报告",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="打印生成内容到 stdout, 不写盘",
    )
    args = parser.parse_args()

    models = _load_domain_models()

    if args.check:
        ok = do_check(models, json_output=args.json_output)
        sys.exit(0 if ok else 1)

    # 默认: 生成并写盘
    ts_content = generate_ts(models)
    if args.dry_run:
        print(ts_content)
        return

    path = write_file(ts_content)
    print(f"已写入: {path}  ({len(ts_content):,} 字节, SHA256 {file_sha256(path)[:16]}…)")


if __name__ == "__main__":
    main()
