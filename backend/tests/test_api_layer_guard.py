"""API 层收口守卫 (Batch 2, DEV-0196)。

R3 规则 (docs/FEATURE_DECOMPOSITION_2026-09-12.md §3):
1. api 层**零直连 SQL** — AST 级检测 get_connection / sqlite3 连接 /
   execute / executemany 调用 (别名导入不漏), 数据访问只有 repository 一层
   (经 service 下沉), 违规即失败并指明文件。
2. api 层文件 **≤150 行** (backend/api/AGENTS.md 既有规格) — 存量超限文件
   入 _LINE_EXEMPTIONS 豁免清单, 新文件不在清单即失败; 清单必须单调收缩。
"""
from __future__ import annotations

import ast
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "api"
LINE_LIMIT = 150

# 存量超限豁免清单 (实测行数 @ 2026-09-12 Batch 2 收口, 供单调收缩跟踪) —
# 新文件禁止加入; knowledge_api/case_api/sources/secrets 均已于 Batch 3 R3 拆分, 本清单相应收缩。
# 收缩到 0 后本守卫的行数检查转为无条件生效。
_LINE_EXEMPTIONS: dict[str, int] = {
    "_registry.py": 271,
    "action_api.py": 236,
    "alerts.py": 156,
    "artifact_api.py": 198,
    "catchup.py": 353,
    "codegarden.py": 464,
    "codegarden_ops.py": 534,
    "content.py": 154,
    "deep_read.py": 151,
    "extract.py": 166,
    "favorites.py": 297,
    "history.py": 164,
    "info_filter_api.py": 159,
    "judgment_api.py": 184,
    "kl_pipeline_api.py": 241,
    "legacy_migrate_v1_api.py": 159,
    "mcp_adapters.py": 234,
    "mcp_agent_tools.py": 162,
    "mcp_config.py": 193,
    "mcp_phase5_tools.py": 202,
    "mcp_types.py": 342,
    "middleware.py": 202,
    "observability_router.py": 296,
    "quality.py": 300,
    "security.py": 214,
    "settings.py": 291,
    "skill_builder_api.py": 230,
    "skill_registry_api.py": 154,
    "skills.py": 177,
    "sync.py": 364,
    "todos.py": 332,
    "wiki_tools.py": 233,
}

# 禁止出现的调用尾缀 → 违规类别名 (仅用于报告文案, 不含任何可执行语句文本)
_FORBIDDEN_CALL_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("get_connection", "直接取连接"),
    ("connect", "直接建连接"),
    ("execute", "直接执行语句"),
    ("executemany", "直接批量执行语句"),
)


def _called_name(node: ast.AST) -> str:
    """调用表达式的点路径 (Name / Attribute 链), 其余返回空串."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _classify_call(name: str) -> str | None:
    for suffix, label in _FORBIDDEN_CALL_SUFFIXES:
        if name == suffix or name.endswith("." + suffix):
            return label
    return None


def _iter_sql_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(API_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            label = _classify_call(_called_name(node.func))
            if label is not None:
                rel = path.relative_to(API_DIR.parent)
                violations.append(f"{rel}:{node.lineno} {label}")
    return violations


def test_api_layer_has_no_direct_sql():
    """api 层禁止 get_connection / 直接连接 / execute 类调用 (AST 全量, rglob 覆盖子包)."""
    violations = _iter_sql_violations()
    assert not violations, (
        "api 层出现直连数据访问 (应下沉 service/repo, 见 R3):\n  " + "\n  ".join(violations)
    )


def test_api_layer_line_limit():
    """api 层文件 ≤150 行; 豁免清单只许收缩不许扩张."""
    violations: list[str] = []
    for path in sorted(API_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(API_DIR).as_posix()
        lines = len(path.read_text(encoding="utf-8").splitlines())
        exempt = _LINE_EXEMPTIONS.get(rel)
        if exempt is not None:
            assert lines <= exempt, (
                f"api/{rel} {lines} 行超出其豁免上限 {exempt} — "
                "豁免清单只许收缩, 超限请拆分而非调大上限"
            )
        elif lines > LINE_LIMIT:
            violations.append(f"api/{rel}: {lines} 行 > {LINE_LIMIT}")
    assert not violations, (
        "api 层新超限文件 (须拆分或显式入 _LINE_EXEMPTIONS 并说明原因):\n  "
        + "\n  ".join(violations)
    )
