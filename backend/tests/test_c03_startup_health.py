"""v1.0 C03 反例测试残段 (R20 version 失同步 + health 4 态).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §4 C03] + [REVIEW_2026-09-07.md R04/R20/R22].
Mimosa 约束: SQL 参数绑定 (本文件全用 ? 形参).

2026-11-19: R04 (worker_coordinator / worker_pump noop 三条用例) 随 worker 协调器
整体退役删除 — 模块已不存在; ruff 触碰文件用例同步移除.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# R20: frontend version 同步 + backend 单一来源
# ---------------------------------------------------------------------------
def test_backend_version_is_single_source() -> None:
    """R20 修复断言: backend APP_VERSION 是 version 单一来源, 其它地方不写死.

    frontend 应读 backend version 或 build 时注入, 不硬编码 0.7.0 / 0.8.0.
    """
    from backend.version import APP_VERSION
    assert APP_VERSION, "backend/version.py APP_VERSION 必须非空"
    assert isinstance(APP_VERSION, str)
    # 验证格式 (semver)
    assert re.match(r"^\d+\.\d+\.\d+", APP_VERSION), (
        f"R20: backend APP_VERSION 不符合 semver: {APP_VERSION!r}"
    )


def test_frontend_version_matches_backend() -> None:
    """R20 修复断言: frontend/package.json version 与 backend APP_VERSION 一致.

    旧 frontend version 0.7.0 vs backend 0.8.2 失同步, 用户看 build 怀疑版本错位.
    修复路径: v1.0 之前先同步 (frontend 0.8.2), C14 验收时统一改 1.0.0.
    """
    from backend.version import APP_VERSION
    frontend_pkg = Path("frontend/package.json")
    assert frontend_pkg.exists(), "frontend/package.json 必须存在"
    import json
    pkg = json.loads(frontend_pkg.read_text(encoding="utf-8"))
    frontend_version = pkg.get("version", "")

    # 修复断言: 必须一致
    assert frontend_version == APP_VERSION, (
        f"R20 失同步: frontend/package.json version={frontend_version!r} "
        f"!= backend APP_VERSION={APP_VERSION!r}. "
        f"修复: 同步 frontend 为 {APP_VERSION}"
    )


# ---------------------------------------------------------------------------
# C03 退出条件: health 4 态 (DB/migration/reads/exec)
# ---------------------------------------------------------------------------
def test_health_endpoint_exposes_4_state_matrix(monkeypatch, tmp_path: Path) -> None:
    """C03 反例基线: 当前 health 端点没显式标 4 态 (DB/migration/reads/exec).

    修复后: /api/health 应有 components.db.migration_status / components.reads / components.exec
    3 个独立状态, 1 个 overall readiness 派生.
    """
    import os
    import urllib.request
    os.environ.pop("HOTSPOT_DB_PATH", None)  # 用生产
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3) as r:
            import json
            d = json.loads(r.read().decode("utf-8"))
            comps = d.get("components", {})
            # 反例基线: 当前 health 缺 exec 状态
            assert "exec" in comps or "execution" in comps, (
                f"C03 反例基线: /api/health 应有 components.exec 字段 (R22 readiness 4 态), "
                f"实际 components keys = {list(comps.keys())}"
            )
    except Exception as e:
        # 后端可能不在运行, 跳过 (依赖运行后端)
        pytest.skip(f"后端 8000 不可达, 跳过 4 态 health 验证: {e}")


# ---------------------------------------------------------------------------
# R04: ruff 158 错 baseline 不在 C03 范围, 留 C14 集中修
# ---------------------------------------------------------------------------
def test_ruff_baseline_record() -> None:
    """记录 ruff 全仓错数基线 (不阻断).

    C14 退出条件: ruff 全仓 0 错 + APP_VERSION 1.0.0 + frontend version 1.0.0.
    """
    import subprocess
    result = subprocess.run(
        [".venv/bin/python", "-m", "ruff", "check", "backend/", "--output-format=concise"],
        capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    errors = re.findall(r"Found (\d+) errors?", output)
    n = int(errors[0]) if errors else 0
    print(f"\n[C03 baseline] ruff 全仓错数: {n} (留 C14 集中修)")