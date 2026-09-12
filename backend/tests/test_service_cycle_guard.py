"""R4 守卫 — backend/services 域模块依赖图无环检测 (AST 静态扫描).

背景 (Batch 4): services 域曾存在模块级硬环 ``action_service ⇄ run_service``
(action.start 桥接调 create_or_replay ⇄ run_service.__init__ 反向惰性 import
ActionService)。已通过 ``backend/services/run_orchestrator.py`` 桥接解环:

    action_service → run_orchestrator → run_service  (单向无环)

本守卫机械化该不变量, 防回潮:

1. AST 扫描 ``backend/services/**/*.py`` 的**全部** import 语句 —
   含模块级 import 与函数内惰性 import (惰性 import 正是历史上藏环的地方,
   不豁免); ``if TYPE_CHECKING:`` 块内的 import 同样计入 (保守策略,
   注解-only 的环虽不炸 import 也在图上显形, 由白名单显式登记)。
2. 节点归并: ``backend.services.*`` 子树内, 任意深度模块归并到其顶层模块 —
   ``backend.services.ai_hub.prompts`` → 节点 ``backend.services.ai_hub``。
   **ai_hub 包内部视为一个节点**: R6 红线不拆 ai_hub, 其内部环不在本守卫
   范围 (ai_hub 子包自身的 import 关系由 R6 治理, 此处折叠为单点)。
3. ``from X import y`` 精确化: ``y`` 仅当其为扫描集内的真实子模块时才追加
   ``X.y`` 边 (纯属性引用不构成对 ``X.y`` 的运行时依赖); 相对 import
   (``level > 0``) 按所在包解析为绝对路径。
4. 手写 Tarjan SCC 求强连通分量 (禁 networkx, 零新依赖), 多节点 SCC = 环;
   每个环必须落在 ``_ALLOWED_CYCLES`` 白名单内 (白名单只许收缩, 不许扩张),
   否则测试失败并列出环路径。
"""
from __future__ import annotations

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# 白名单 — 只许收缩, 不许扩张; 新增条目必须在注释里写明解不了的原因
# ---------------------------------------------------------------------------
_ALLOWED_CYCLES: set[frozenset[str]] = {
    # skill_registry ⇄ skill_runner (登记于 Batch 4 R4 首扫):
    # runner→registry 方向是模块级契约消费 (dispatch.py/core.py 顶层 import
    # SkillDef/ServiceTarget/Step 类型, 方向正确); registry→runner 方向是
    # SkillRegistry.execute() (core.py, B2.3) 内**函数级惰性** import
    # SkillRunner 供缺省执行 + TYPE_CHECKING 注解引用 SkillRunResult —
    # 这是 v0.8 SK 域文档化的反依赖设计 ("反向依赖禁令: 顶层不 import
    # backend.services.skill_runner", core.py docstring), 解环需反转 execute()
    # 的缺省 runner 注入接口 (涉及 SK 域公共接口与 B5 worker 调用方),
    # 非纯 import 方向梳理, 登记为已知债。收缩路径: execute() 改强制注入
    # runner 后删除本条目。
    frozenset({"backend.services.skill_registry", "backend.services.skill_runner"}),
}

#: 守卫明确禁止回潮的历史环 — 即便有人误加白名单也必须失败 (白名单收缩哨兵)
_FORBIDDEN_CYCLES: set[frozenset[str]] = {
    frozenset({"backend.services.action_service", "backend.services.run_service"}),
}

_SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"


# ---------------------------------------------------------------------------
# 纯函数 helpers (可独立单测)
# ---------------------------------------------------------------------------
def node_of(module: str) -> str:
    """模块路径 → 依赖图节点: backend.services.X.Y.Z → backend.services.X."""
    parts = module.split(".")
    if len(parts) >= 3 and parts[0] == "backend" and parts[1] == "services":
        return ".".join(parts[:3])
    return module


def module_name_of(py_file: Path, root: Path) -> str:
    """文件 → 模块路径 (__init__.py 归并为所在包)."""
    rel = py_file.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(["backend", "services", *parts]) if parts else "backend.services"


def resolve_relative(package: str, node: ast.ImportFrom) -> str | None:
    """相对 import (level>0) → 绝对模块路径; 解析失败返回 None."""
    if node.level == 0:
        return node.module
    pkg_parts = package.split(".") if package else []
    # level=1 → 当前包; level=2 → 上一级包, 以此类推
    up = node.level - 1
    if up > len(pkg_parts):
        return None
    base = pkg_parts[: len(pkg_parts) - up] if up else pkg_parts
    parts = [*base, *(node.module.split(".") if node.module else [])]
    return ".".join(parts) if parts else None


def import_targets(
    tree: ast.AST,
    module: str,
    known_modules: set[str],
) -> list[str]:
    """收集一个模块 AST 内全部 import 的目标模块路径 (含惰性/TYPE_CHECKING)."""
    package = module.rsplit(".", 1)[0] if "." in module else module
    targets: list[str] = []
    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                targets.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom):
            base = resolve_relative(package, stmt)
            if base is None:
                continue
            targets.append(base)
            for alias in stmt.names:
                sub = f"{base}.{alias.name}"
                # 精确化: 仅真实子模块 (出现在扫描集内) 才追加 X.y 边
                if sub in known_modules:
                    targets.append(sub)
    return targets


def tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    """手写 Tarjan 强连通分量 (迭代式, 避免深图递归爆栈).

    返回全部 SCC; 单节点 SCC (无自环) 也在列, 调用方按 len>1 过滤.
    """
    index_counter = [0]
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []

    for start in sorted(graph):
        if start in index:
            continue
        # 迭代 DFS: 工作栈元素 = (节点, 已展开到的后继下标)
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            v, pi = work.pop()
            if pi == 0:
                index[v] = lowlink[v] = index_counter[0]
                index_counter[0] += 1
                stack.append(v)
                on_stack.add(v)
            successors = sorted(graph.get(v, ()))
            recursed = False
            for i in range(pi, len(successors)):
                w = successors[i]
                if w not in index:
                    work.append((v, i + 1))
                    work.append((w, 0))
                    recursed = True
                    break
                if w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])
            if recursed:
                continue
            if lowlink[v] == index[v]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                sccs.append(comp)
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])
    return sccs


def build_services_graph(root: Path) -> dict[str, set[str]]:
    """扫描 backend/services/**/*.py → 节点级 (顶层模块) 依赖图 (域内边)."""
    files = sorted(root.rglob("*.py"))
    modules: dict[Path, str] = {}
    for f in files:
        modules[f] = module_name_of(f, root)
    known_modules = set(modules.values())

    graph: dict[str, set[str]] = {}
    for f, module in modules.items():
        self_node = node_of(module)
        graph.setdefault(self_node, set())
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for target in import_targets(tree, module, known_modules):
            target_node = node_of(target)
            if target_node != self_node and target_node.startswith("backend.services."):
                graph[self_node].add(target_node)
    return graph


def find_cycles(graph: dict[str, set[str]]) -> list[frozenset[str]]:
    """多节点 SCC 即环, 以 frozenset 表示 (无序, 便于白名单比对)."""
    return [
        frozenset(comp)
        for comp in tarjan_scc(graph)
        if len(comp) > 1
    ]


# ---------------------------------------------------------------------------
# 守卫断言
# ---------------------------------------------------------------------------
def test_services_dependency_graph_has_no_cycles_beyond_whitelist() -> None:
    graph = build_services_graph(_SERVICES_DIR)
    cycles = find_cycles(graph)
    unexpected = [c for c in cycles if c not in _ALLOWED_CYCLES]
    assert not unexpected, (
        "backend/services 域发现白名单外的模块依赖环 (含函数内惰性 import): "
        f"{sorted(sorted(c) for c in unexpected)}; "
        "解法: 理顺 import 方向 (桥接/注入), 或在 _ALLOWED_CYCLES 登记"
        "并注明解不了的原因 (白名单只许收缩)"
    )


def test_action_run_cycle_does_not_reappear() -> None:
    """历史环 action⇄run 的显式回潮哨兵 (独立于白名单机制)."""
    graph = build_services_graph(_SERVICES_DIR)
    cycles = find_cycles(graph)
    forbidden = [c for c in cycles if c in _FORBIDDEN_CYCLES]
    assert not forbidden, (
        "action_service ⇄ run_service 模块级环回潮 — 应经 "
        "backend/services/run_orchestrator 桥接, 不得重新互相 import: "
        f"{sorted(sorted(c) for c in forbidden)}"
    )
    # 且不在白名单里 (保证白名单只许收缩不被该环污染)
    assert _FORBIDDEN_CYCLES.isdisjoint(_ALLOWED_CYCLES)


def test_skill_cycle_is_the_only_whitelisted_entry() -> None:
    """当前白名单应恰为 skill_registry⇄skill_runner 一条 (收缩哨兵)."""
    graph = build_services_graph(_SERVICES_DIR)
    cycles = find_cycles(graph)
    assert set(cycles) == _ALLOWED_CYCLES, (
        f"实际环 {sorted(sorted(c) for c in cycles)} 与白名单 "
        f"{sorted(sorted(c) for c in _ALLOWED_CYCLES)} 不一致 — "
        "环被解掉请同步收缩白名单; 出现新环请先解环"
    )


# ---------------------------------------------------------------------------
# helper 单测 (合成图, 不触文件系统)
# ---------------------------------------------------------------------------
def test_node_of_folds_submodules_to_top_level_module() -> None:
    assert node_of("backend.services.ai_hub.prompts") == "backend.services.ai_hub"
    assert node_of("backend.services.ai_hub.service") == "backend.services.ai_hub"
    assert node_of("backend.services.run_service") == "backend.services.run_service"
    # 域外模块保持原样 (不参与域内边)
    assert node_of("backend.repository.run_repo") == "backend.repository.run_repo"


def test_tarjan_detects_synthetic_cycle() -> None:
    graph = {
        "a": {"b"},
        "b": {"c"},
        "c": {"a", "d"},
        "d": set(),
    }
    cycles = find_cycles(graph)
    assert frozenset({"a", "b", "c"}) in cycles
    assert all("d" not in c for c in cycles)


def test_tarjan_acyclic_graph_yields_no_cycle() -> None:
    graph = {
        "action_service": {"orchestrator"},
        "orchestrator": {"run_service"},
        "run_service": set(),
    }
    assert find_cycles(graph) == []


def test_import_targets_counts_lazy_and_type_checking_imports() -> None:
    src = (
        "import hashlib\n"
        "from backend.repository.run_repo import RunRepository\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from backend.services.skill_runner import SkillRunResult\n"
        "def f():\n"
        "    from backend.services.run_orchestrator import create_run_for_action_start\n"
        "    return create_run_for_action_start\n"
    )
    tree = ast.parse(src)
    known = {"backend.services.skill_runner", "backend.services.run_orchestrator"}
    targets = import_targets(tree, "backend.services.fake", known)
    assert "backend.repository.run_repo" in targets
    assert "backend.services.skill_runner" in targets  # TYPE_CHECKING 计入
    assert "backend.services.run_orchestrator" in targets  # 函数内惰性计入
