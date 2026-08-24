#!/usr/bin/env python3
"""harness_analyze.py — agent-assets-review CLI gate (Project-local equivalent of ``harness analyze``).

检测 ``.agents/skills/`` 下 ``SKILL.md`` 的合规性, 强制执行项目根 AGENTS.md 中
声明的 *Agent Assets Lint Policy*:

- **ERROR** (进程退出 1, 阻断 CI): 新增长 skill (>500 行) 缺少 ``references/`` 子文档
- **WARNING** (保留 reviewer 备注, 不阻断): 已有长 skill 在 baseline 豁免名单内
  仍缺 ``references/``; SKILL.md 缺失 YAML frontmatter 的 ``name``/``description`` 字段

输出
----
- 默认 stdout 为人类可读表格
- ``--format json`` 输出 JSON: ``{"errors": [...], "warnings": [...], "summary": {...}}``
- ``--check`` 严格模式 (等价 ``--format json`` + 非零退出码), 与 ruff/pytest/generate_meta --check 同款

退出码
------
- 0 — 无 ERROR
- 1 — 存在 ERROR (WARNING 不影响退出码)

豁免机制
--------
``scripts/harness_baseline.json`` 中登记的 skill 视为 grandfathered, 仅产生
WARNING, 不产生 ERROR。新增 / 改造的 skill 不在 baseline → 立即按 ERROR 处理。

用法::

    python scripts/harness_analyze.py                  # 默认 stdout human-readable
    python scripts/harness_analyze.py --format json    # CI 友好 JSON
    python scripts/harness_analyze.py --check          # 严格模式, 与其它 CI gate 同款
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / ".agents" / "skills"
BASELINE_PATH = ROOT / "scripts" / "harness_baseline.json"
LONG_SKILL_THRESHOLD = 500  # 行数阈值, 与 AGENTS.md 声明一致

# YAML frontmatter 强制字段 (skill metadata contract)
REQUIRED_FRONTMATTER = ("name", "description")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _load_baseline() -> dict[str, dict[str, Any]]:
    """读取豁免名单。文件缺失视为空 (即所有现存 skill 都是 ERROR 候选)。"""
    if not BASELINE_PATH.exists():
        return {}
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[WARN] {BASELINE_PATH.name} JSON 解析失败: {exc}", file=sys.stderr)
        return {}
    waivers = data.get("waivers", {})
    if not isinstance(waivers, dict):
        return {}
    return waivers


def _parse_frontmatter(skill_md: Path) -> dict[str, str]:
    """提取 SKILL.md 顶部 ``---`` 之间的 YAML 字段。本 lint 只校验键名存在, 不做 YAML 完整解析。"""
    text = skill_md.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def analyze_one(skill_dir: Path, waivers: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """分析单个 skill 目录, 返回 (errors, warnings) 元组。"""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        errors.append(
            {
                "skill": skill_name,
                "rule": "missing_skill_md",
                "message": f"{skill_dir}/SKILL.md 不存在",
            }
        )
        return errors, warnings

    line_count = sum(1 for _ in skill_md.open(encoding="utf-8"))
    has_references = (skill_dir / "references").is_dir()
    in_baseline = skill_name in waivers

    # Rule 1: 长 skill 必须有 references/
    if line_count > LONG_SKILL_THRESHOLD and not has_references:
        record = {
            "skill": skill_name,
            "rule": "long_skill_requires_references",
            "lines": line_count,
            "threshold": LONG_SKILL_THRESHOLD,
            "message": (
                f"{skill_name}/SKILL.md ({line_count} 行) 超过 {LONG_SKILL_THRESHOLD} 行, "
                "必须包含 references/ 子文档"
            ),
        }
        if in_baseline:
            record["waiver"] = waivers[skill_name].get("reason", "grandfathered")
            warnings.append(record)
        else:
            errors.append(record)

    # Rule 2: YAML frontmatter 必须有 name + description (advisory)
    fm = _parse_frontmatter(skill_md)
    missing = [k for k in REQUIRED_FRONTMATTER if k not in fm]
    if missing:
        warnings.append(
            {
                "skill": skill_name,
                "rule": "missing_frontmatter_fields",
                "missing": missing,
                "message": f"{skill_name}/SKILL.md frontmatter 缺字段: {', '.join(missing)}",
            }
        )

    return errors, warnings


def analyze_all() -> dict[str, Any]:
    """扫描 SKILLS_DIR 下所有 skill, 返回结构化报告。"""
    waivers = _load_baseline()
    all_errors: list[dict[str, Any]] = []
    all_warnings: list[dict[str, Any]] = []
    skills_seen: list[str] = []

    if not SKILLS_DIR.is_dir():
        return {
            "errors": [{"skill": "<root>", "rule": "skills_dir_missing", "message": f"{SKILLS_DIR} 不存在"}],
            "warnings": all_warnings,
            "summary": {"skills": 0, "errors": 1, "warnings": 0, "waivers": len(waivers)},
        }

    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        skills_seen.append(skill_dir.name)
        errs, warns = analyze_one(skill_dir, waivers)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    return {
        "errors": all_errors,
        "warnings": all_warnings,
        "summary": {
            "skills": len(skills_seen),
            "errors": len(all_errors),
            "warnings": len(all_warnings),
            "waivers": len(waivers),
            "long_skill_threshold": LONG_SKILL_THRESHOLD,
        },
    }


def render_human(report: dict[str, Any]) -> str:
    """生成人类可读报告。"""
    summary = report["summary"]
    lines = [
        f"agent-assets-review — scanned {summary['skills']} skills "
        f"(errors={summary['errors']}, warnings={summary['warnings']}, waivers={summary['waivers']})",
        f"long_skill_threshold = {summary['long_skill_threshold']} 行",
        "",
    ]
    if report["errors"]:
        lines.append("ERRORS (CI 阻断):")
        for e in report["errors"]:
            lines.append(f"  - [{e['rule']}] {e['message']}")
        lines.append("")
    if report["warnings"]:
        lines.append("WARNINGS (advisory, reviewer 备注):")
        for w in report["warnings"]:
            waiver_note = f" (waiver: {w['waiver']})" if "waiver" in w else ""
            lines.append(f"  - [{w['rule']}] {w['message']}{waiver_note}")
        lines.append("")
    if not report["errors"] and not report["warnings"]:
        lines.append("OK: 所有 agent assets 通过 lint")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="agent-assets-review CLI gate (Project-local equivalent of `harness analyze`)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式: text(默认,人类可读) 或 json(CI 友好)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="严格模式: 等价 --format json + errors 非零 exit 1 (CI gate 同款)",
    )
    args = parser.parse_args()

    report = analyze_all()
    fmt = "json" if args.check else args.format

    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())