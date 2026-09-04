"""skill_eval.dataset — 黄金 fixture YAML 加载与 dataclass 契约 (C5).

黄金 fixture 的设计:
- 每个 .yml 描述一个最小可重现 case: skill_id / inputs / assertions
- assertions 列表式声明, 每条带 ``name`` + ``type`` + ``target`` + 校验参数
- 顶层 ``id`` 全局唯一 (EvalReport 按 id 索引), 命名规范: ``<skill_id>-<type>-<n>``

assertion.type 当前白名单 (judge.py 消费):
  type_check / equal / range / field_type / length_eq
  list_field_type / list_field_eq / list_field_range / list_field_min
  list_field_min_length / list_avg_above / dict_has_keys

加载失败 fail loud: 文件找不到 / 顶层非 mapping / assertions 非 list
/ assertion 缺 name / type_key 未知 → ValueError (R12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.logging_config import logger

__all__ = [
    "FIXTURES_DIR",
    "Assertion",
    "EvalFixture",
    "list_fixture_ids",
    "load_fixture",
    "load_fixture_by_id",
]


#: 黄金 fixture 目录 (仓库根 skill_eval/fixtures/); 与 plan 一致
FIXTURES_DIR = Path("skill_eval/fixtures")


#: 全部合法 assertion.type (judge.py 同步消费, 缺一个 → EvalFixture.load 抛 ValueError)
ASSERTION_TYPES: frozenset[str] = frozenset(
    {
        "type_check",
        "equal",
        "range",
        "field_type",
        "length_eq",
        "list_field_type",
        "list_field_eq",
        "list_field_range",
        "list_field_min",
        "list_field_min_length",
        "list_avg_above",
        "dict_has_keys",
    }
)


@dataclass(frozen=True)
class Assertion:
    """单条黄金断言; 字段含义见 module docstring."""

    name: str
    type: str
    target: str
    expected: Any = None
    min: float | None = None
    max: float | None = None
    field: str | None = None
    min_length: int | None = None
    threshold: float | None = None
    skip_if_null: bool = False
    skip_if_empty: bool = False


@dataclass(frozen=True)
class EvalFixture:
    """黄金 fixture 完整契约.

    - ``id`` 全局唯一 (string)
    - ``skill_id`` / ``playbook`` 二选一 (kind 决定); playbook 走 FixtureRunner 分支
    - ``inputs`` 喂给 skill / playbook
    - ``assertions`` 是 Assertion 列表 (至少 1 条)
    """

    id: str
    kind: str  # "skill" | "playbook"
    skill_id: str | None
    playbook: str | None
    skill_type: str | None
    category: str | None
    desc: str
    inputs: dict[str, Any] = field(default_factory=dict)
    assertions: list[Assertion] = field(default_factory=list)
    source_path: str | None = None

    @staticmethod
    def from_dict(d: dict[str, Any], source_path: str | None = None) -> "EvalFixture":
        """从 dict 构造, 缺关键字段 → ValueError (R12 fail loud)."""
        if not isinstance(d, dict):
            raise ValueError(f"fixture 顶层必须是 mapping, got {type(d).__name__}")

        fid = d.get("id")
        if not fid or not isinstance(fid, str):
            raise ValueError("fixture 缺 id (string 必填)")

        kind_raw = d.get("kind") or ("playbook" if d.get("playbook") else "skill")
        if kind_raw not in ("skill", "playbook"):
            raise ValueError(
                f"fixture {fid!r} kind 非法 {kind_raw!r}, 仅允许 skill / playbook"
            )

        skill_id = d.get("skill_id")
        playbook = d.get("playbook")
        if kind_raw == "skill" and not skill_id:
            raise ValueError(f"fixture {fid!r} (kind=skill) 缺 skill_id")
        if kind_raw == "playbook" and not playbook:
            raise ValueError(f"fixture {fid!r} (kind=playbook) 缺 playbook")

        assertions_raw = d.get("assertions") or []
        if not isinstance(assertions_raw, list) or not assertions_raw:
            raise ValueError(f"fixture {fid!r} assertions 必须是非空 list")

        assertions: list[Assertion] = []
        for a in assertions_raw:
            if not isinstance(a, dict):
                raise ValueError(f"fixture {fid!r} assertion 必须是 mapping")
            atype = a.get("type")
            if atype not in ASSERTION_TYPES:
                raise ValueError(
                    f"fixture {fid!r} assertion type {atype!r} 非法, "
                    f"仅允许 {sorted(ASSERTION_TYPES)}"
                )
            assertions.append(
                Assertion(
                    name=a["name"] if "name" in a else atype,
                    type=atype,
                    target=a.get("target", ""),
                    expected=a.get("expected"),
                    min=a.get("min"),
                    max=a.get("max"),
                    field=a.get("field"),
                    min_length=a.get("min_length"),
                    threshold=a.get("threshold"),
                    skip_if_null=bool(a.get("skip_if_null", False)),
                    skip_if_empty=bool(a.get("skip_if_empty", False)),
                )
            )

        return EvalFixture(
            id=fid,
            kind=kind_raw,
            skill_id=skill_id,
            playbook=playbook,
            skill_type=d.get("skill_type"),
            category=d.get("category"),
            desc=d.get("desc", ""),
            inputs=dict(d.get("inputs") or {}),
            assertions=assertions,
            source_path=source_path,
        )


def _yaml() -> Any:
    """惰性 import PyYAML, 缺 → RuntimeError 让调用方感知."""
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML is required to load skill_eval fixtures") from e
    return yaml


def list_fixture_ids() -> list[str]:
    """扫 FIXTURES_DIR/*.yaml (忽略 read 失败), 返回 id 列表 (不解析)."""
    if not FIXTURES_DIR.exists():
        return []
    out: list[str] = []
    for path in sorted(FIXTURES_DIR.glob("*.yaml")):
        out.append(path.stem)
    return out


def load_fixture(path: str) -> EvalFixture:
    """从 YAML 路径加载 + 解析为 EvalFixture; 失败抛 ValueError (含原因)."""
    pb_path = Path(path)
    if not pb_path.exists():
        raise ValueError(f"fixture {path!r} 不存在")

    try:
        content = pb_path.read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"fixture {path!r} 读取失败: {e}") from e

    try:
        parsed = _yaml().safe_load(content) or {}
    except Exception as e:
        raise ValueError(f"fixture {path!r} YAML 解析失败: {e}") from e

    return EvalFixture.from_dict(parsed, source_path=str(pb_path))


def load_fixture_by_id(fixture_id: str) -> EvalFixture:
    """按 stem 名 (不带扩展) 加载 FIXTURES_DIR/*.yaml; 失败抛 ValueError."""
    path = FIXTURES_DIR / f"{fixture_id}.yaml"
    if not path.exists():
        # 试用 .yml 扩展
        alt = FIXTURES_DIR / f"{fixture_id}.yml"
        if alt.exists():
            path = alt
        else:
            raise ValueError(
                f"fixture {fixture_id!r} 在 {FIXTURES_DIR} 找不到 (尝试 .yaml / .yml)"
            )
    try:
        fx = load_fixture(str(path))
    except ValueError as e:
        logger.error(f"load_fixture_by_id: {e}")
        raise
    return fx