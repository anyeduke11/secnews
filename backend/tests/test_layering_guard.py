"""分层守卫 — services/scheduler/collectors/repository 禁止 import backend.api (DEV-0191)。

事件总线 (publish_event) 自 api/events.py 下沉 backend/core/events.py 后,
反向依赖禁令「service 层禁 import backend.api」(backend/services/AGENTS.md)
从此可以机械断言: 本测试 AST 全量扫描四层源码, 注释/docstring 不误报。

新增反向依赖会直接失败并指明文件:行号 — 修复方式统一为把被依赖的
基础设施下沉到 backend/core/ 或 backend/services/, 而非在本测试加白名单。
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
GUARDED_DIRS = ("services", "scheduler", "collectors", "repository")


def _iter_api_import_violations() -> list[str]:
    violations: list[str] = []
    for name in GUARDED_DIRS:
        root = BACKEND / name
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                targets: list[str] = []
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:
                        targets = [node.module]
                for target in targets:
                    if target == "backend.api" or target.startswith("backend.api."):
                        rel = path.relative_to(BACKEND)
                        violations.append(f"{rel}:{node.lineno} imports {target}")
    return violations


def test_no_reverse_dependency_on_api_layer():
    """services/scheduler/collectors/repository 四层不得 import backend.api."""
    violations = _iter_api_import_violations()
    assert not violations, (
        "发现 services/scheduler/collectors/repository → api 反向依赖 "
        "(应把基础设施下沉 backend/core/ 而非 import api 层):\n  " + "\n  ".join(violations)
    )


def test_event_bus_lives_in_core_not_api():
    """事件总线唯一真相源在 core/events.py; api/events.py 只留 SSE 端点."""
    api_events = (BACKEND / "api" / "events.py").read_text(encoding="utf-8")
    core_events = (BACKEND / "core" / "events.py").read_text(encoding="utf-8")
    assert "async def publish_event" in core_events, "core/events.py 必须定义 publish_event"
    assert "async def publish_event" not in api_events, (
        "api/events.py 不得再定义 publish_event (会重新制造 services→api 反向依赖的口子)"
    )
