"""playbook_engine.loader — YAML 解析与 fs 加载 (C1).

设计:
- 不引入 jinja2; YAML 用 PyYAML (仓库已隐式传递依赖); inputs/skill/action/expr
  字符串中的 ``{{ ... }}`` 替换留 StepExecutor (不依赖 jinja)
- load_playbook(path) → Playbook; 解析失败抛 ValueError (与 codegarden_orchestration
  .get_playbook 行为一致, 旧包装层兼容)
- list_examples() 扫 codegarden/playbooks/*.yml (与 P2-7 旧 example.yml 共存)
  + 新 hot-spec playbook_engine/examples/*.yml (C1 提供 3 个示例)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.logging_config import logger

__all__ = ["EXAMPLES_DIR", "load_playbook", "list_examples"]


#: 示例目录 (C1 在仓库根 playbook_engine/examples/ 留 3 个示例, 与
#: codegarden/playbooks/example.yml 共存, 互不干扰)
EXAMPLES_DIR = Path("playbook_engine/examples")


def list_examples() -> list[dict[str, Any]]:
    """扫 EXAMPLES_DIR + codegarden/playbooks/*.yml, 返回 summary (轻量, 不解析 YAML)。

    与 codegarden_orchestration.list_playbooks 风格一致 (含 name/path/size),
    但同时扫描两个目录 (兼容路径)。
    """
    out: list[dict[str, Any]] = []

    for base in (EXAMPLES_DIR, Path("codegarden/playbooks")):
        if not base.exists():
            continue
        for pb_file in sorted(base.glob("*.yml")):
            try:
                content = pb_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"list_examples: read {pb_file} failed: {e}")
                continue
            out.append(
                {
                    "name": pb_file.stem,
                    "path": str(pb_file),
                    "size": len(content),
                }
            )
    return out


def _yaml() -> Any:
    """惰性 import PyYAML, 失败抛 RuntimeError 让调用方感知。"""
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML is required to load playbook YAML") from e
    return yaml


def load_playbook(path: str) -> Any:  # 返回 Playbook dataclass, 此处避免循环 import
    """从 YAML 路径加载 + 解构为 dataclass; 失败抛 ValueError (含具体原因)。"""
    # 推迟到此处 import 避免 loader ↔ core 循环
    from backend.services.playbook_engine.core import Playbook

    pb_path = Path(path)
    if not pb_path.exists():
        raise ValueError(f"playbook {path!r} 不存在")

    try:
        content = pb_path.read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"playbook {path!r} 读取失败: {e}") from e

    try:
        parsed = _yaml().safe_load(content) or {}
    except Exception as e:
        raise ValueError(f"playbook {path!r} YAML 解析失败: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError(f"playbook {path!r} 顶层必须是 mapping, got {type(parsed).__name__}")

    if parsed.get("kind") != "Playbook":
        raise ValueError(
            f"playbook {path!r} kind 必须为 'Playbook', got {parsed.get('kind')!r}"
        )

    metadata = extract_metadata(parsed)
    inputs = extract_inputs(parsed)
    steps_raw = extract_steps(parsed)
    steps = [_step_from_dict(s) for s in steps_raw]
    trigger = extract_trigger(parsed)

    return Playbook(
        name=metadata.get("name") or pb_path.stem,
        desc=metadata.get("desc", ""),
        owner=metadata.get("owner", "user"),
        tags=list(metadata.get("tags", []) or []),
        trigger=trigger,
        inputs=inputs,
        steps=steps,
        raw_path=str(pb_path),
        primary_output=(parsed.get("outputs") or {}).get("primary"),
    )


def extract_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    return dict(parsed.get("metadata") or {})


def extract_inputs(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("inputs") or {}
    if not isinstance(raw, dict):
        return {}
    return {k: dict(v) if isinstance(v, dict) else {"default": v} for k, v in raw.items()}


def extract_trigger(parsed: dict[str, Any]) -> dict[str, Any]:
    """trigger 块; cron 触发 spec / timezone, C2 scheduler 消费。

    非 cron 类型暂不消费, 仅作 schema 透传。
    """
    raw = parsed.get("trigger")
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def extract_steps(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw = parsed.get("steps") or []
    if not isinstance(raw, list):
        raise ValueError("playbook 'steps' 必须是 list")
    return raw


def _step_from_dict(s: dict[str, Any]) -> Any:  # 返回 PlaybookStep
    """YAML step dict → PlaybookStep; 兼容 spec 字段命名。"""
    # 推迟 import 避免循环
    from backend.services.playbook_engine.core import PlaybookStep

    if not isinstance(s, dict):
        raise ValueError(f"step 必须是 mapping, got {type(s).__name__}")
    step_id = s.get("id") or s.get("name")
    if not step_id:
        raise ValueError("step 缺少 id/name")
    kind_raw = s.get("type") or s.get("kind") or ("skill" if s.get("skill") else ("api" if s.get("action") else "condition"))
    if kind_raw not in ("skill", "api", "condition"):
        # 显式禁止 script
        raise ValueError(
            f"step {step_id!r} kind {kind_raw!r} 禁止 — 仅允许 skill / api / condition (R7)"
        )
    return PlaybookStep(
        id=str(step_id),
        kind=kind_raw,  # type: ignore[arg-type]
        if_expr=s.get("if"),
        output=s.get("output"),
        skill=s.get("skill"),
        params=dict(s.get("params") or {}),
        action=s.get("action"),
        body=dict(s.get("body") or {}) if s.get("body") else None,
        expr=s.get("expr") if kind_raw == "condition" else None,
    )