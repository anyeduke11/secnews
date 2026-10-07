"""CORE_ROUTERS / CONDITIONAL_ROUTERS / EXTENSION_ROUTERS 完整性守卫。

v0.8.6 P0-8 / 审计 E11 (廉价修法): 此前 ``core/routers.py`` 的断言只查
core ∩ extension 重叠, **不查完整性** — 白名单 45 项中 8 项实为
``config.feature_*`` 条件注册 (谎报"永远注册"), 23 个无条件注册模块漏登记,
漂移不可检测 (R5: 白名单纪律形同虚设)。

本测试 AST 解析 ``backend/api/_registry.py`` 的 ``register_all``, 按**实际
注册方式**三分:

| 注册方式 | 权威表 |
|---|---|
| 顶层无条件 ``include_router`` | ``core.routers.CORE_ROUTERS`` |
| ``if config.feature_*:`` 块内 | ``core.routers.CONDITIONAL_ROUTERS`` |
| ``if is_extension_enabled(...)`` 块内 | ``extensions.EXTENSION_ROUTERS`` 展开集 |

三向**双向**核对 (实际 ⊆ 表 且 表 ⊆ 实际): 新增 router 漏登记、或白名单
躺着实际已条件化/删除的条目, 均立即 CI 红。这就是 E11 的机械化纪律:
**白名单不再靠自觉维护, 而是与注册面互为镜像**。
"""
from __future__ import annotations

import ast
from pathlib import Path

from backend.core.routers import CONDITIONAL_ROUTERS, CORE_ROUTERS
from backend.extensions import EXTENSION_ROUTERS

_REGISTRY = Path(__file__).resolve().parents[1] / "api" / "_registry.py"
# DEV-0287 (D5): _registry.py 拆三半区 (core/flags/extensions) — 扫描面同步,
# 三半区的 register_* 函数体分类并集 == 原 register_all 语义。
_REGISTRY_PARTS = (
    _REGISTRY.parent / "_registry_core.py",
    _REGISTRY.parent / "_registry_flags.py",
    _REGISTRY.parent / "_registry_extensions.py",
)


def _alias_map(tree: ast.AST) -> dict[str, str]:
    """import 别名 → 真模块名 (如 alert_api_v2 → alert_api)。"""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name.split(".")[-1]
    return aliases


def _module_of(expr: ast.expr, aliases: dict[str, str]) -> str | None:
    """include_router 第一参数 → 模块名。

    覆盖三种形态: ``X.router`` / ``X.router, tags=[...]`` /
    ``X.kl_router`` (mcp_phase5_tools 一个模块导出两个 router) —
    统一剥掉属性链, 取**根** Name 还原别名。
    """
    target = expr
    while isinstance(target, ast.Attribute):
        target = target.value
    if isinstance(target, ast.Name):
        return aliases.get(target.id, target.id)
    return None


def _classify_registry() -> tuple[set[str], set[str], set[str]]:
    """返回 (无条件集, feature 条件集, extension 条件集)。

    DEV-0287 (D5): 扫描面 = _registry.py 的 register_all + 三半区
    (_registry_core/_registry_flags/_registry_extensions) 的 register_*
    — 各文件分类并集 (注册语义按文件切分, 调用顺序不影响集合判定)。
    """
    unconditional: set[str] = set()
    by_flag: set[str] = set()
    by_extension: set[str] = set()
    for path in (_REGISTRY, *_REGISTRY_PARTS):
        if not path.exists():
            continue
        u, f, e = _classify_registry_file(path)
        unconditional |= u
        by_flag |= f
        by_extension |= e
    return unconditional, by_flag, by_extension


def _classify_registry_file(
    path: Path,
) -> tuple[set[str], set[str], set[str]]:
    """单文件 AST 分类 (原 _classify_registry 实现体)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = _alias_map(tree)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("register")
    )

    unconditional: set[str] = set()
    by_flag: set[str] = set()
    by_extension: set[str] = set()

    def add_include(call: ast.Call, bucket: set[str]) -> None:
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "include_router"
            and call.args
        ):
            mod = _module_of(call.args[0], aliases)
            if mod:
                bucket.add(mod)

    def walk(stmts: list[ast.stmt], bucket: set[str] | None) -> None:
        """bucket=None 表示顶层 (裸 include 即无条件); 非 None 为已定桶。"""
        for stmt in stmts:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                add_include(
                    stmt.value, unconditional if bucket is None else bucket
                )
            elif isinstance(stmt, ast.If):
                cond = ast.unparse(stmt.test)
                # 嵌套 if (bucket 已定): 条件叠加, 归外层分类 (保守);
                # 顶层 if: 按条件分类 — 混合条件 (config.feature_x and
                # is_extension_enabled) 归扩展域
                nxt = bucket if bucket is not None else (
                    by_extension if "is_extension_enabled" in cond else (
                        by_flag if "config.feature_" in cond else unconditional
                    )
                )
                walk(stmt.body, nxt)
                walk(stmt.orelse, nxt)

    walk(fn.body, None)
    return unconditional, by_flag, by_extension


def test_unconditional_registration_matches_core_routers():
    """顶层 include_router 的模块集合 == CORE_ROUTERS (双向)。"""
    unconditional, _, _ = _classify_registry()
    missing = unconditional - CORE_ROUTERS
    stale = CORE_ROUTERS - unconditional
    assert not missing, (
        f"以下模块在 _registry.py 无条件注册但未登记 CORE_ROUTERS "
        f"(E11 完整性: 白名单漏登记即失败):\n  {sorted(missing)}"
    )
    assert not stale, (
        f"CORE_ROUTERS 中以下条目在 _registry.py 并非无条件注册 "
        f"(谎报'永远注册' — 挪去 CONDITIONAL_ROUTERS 或删除):\n  {sorted(stale)}"
    )


def test_feature_flag_registration_matches_conditional_routers():
    """config.feature_* 分支内的模块集合 == CONDITIONAL_ROUTERS (双向)。"""
    _, by_flag, _ = _classify_registry()
    missing = by_flag - CONDITIONAL_ROUTERS
    stale = CONDITIONAL_ROUTERS - by_flag
    assert not missing, (
        f"以下模块按 config.feature_* 条件注册但未登记 CONDITIONAL_ROUTERS:\n"
        f"  {sorted(missing)}"
    )
    assert not stale, (
        f"CONDITIONAL_ROUTERS 中以下条目在 _registry.py 无对应 feature 分支:\n"
        f"  {sorted(stale)}"
    )


def test_extension_registration_matches_extension_routers():
    """is_extension_enabled 分支内的模块集合 == EXTENSION_ROUTERS 展开集 (双向)。"""
    _, _, by_ext = _classify_registry()
    declared = {m for mods in EXTENSION_ROUTERS.values() for m in mods}
    missing = by_ext - declared
    stale = declared - by_ext
    assert not missing, (
        f"以下模块按 is_extension_enabled 注册但未登记 EXTENSION_ROUTERS "
        f"(settings/features 端点会漏报):\n  {sorted(missing)}"
    )
    assert not stale, (
        f"EXTENSION_ROUTERS 中以下条目在 _registry.py 无对应 gate 分支:\n"
        f"  {sorted(stale)}"
    )


def test_three_tables_disjoint():
    """三表互斥 (import 期断言的测试镜像, 防断言被绕过)。"""
    ext = {m for mods in EXTENSION_ROUTERS.values() for m in mods}
    assert not CORE_ROUTERS & CONDITIONAL_ROUTERS
    assert not CORE_ROUTERS & ext
    assert not CONDITIONAL_ROUTERS & ext
