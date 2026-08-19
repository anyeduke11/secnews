"""test_feature_gates.py — 扩展门控组合测试 (v0.4.3, ~30 用例)。

覆盖 3 种配置矩阵:
- 全关 (core-only): core 路由全可达, 扩展路由全 404
- 全开 (all-on): 扩展路由可达
- 逐扩展开关: 每个扩展独立验证

实现方式: monkeypatch ``backend.extensions._load_gates`` + 重建 FastAPI app
并重新调用 ``register_routers`` (路由注册是 import 期行为, 不能复用模块级 app)。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers

ALL_OFF = {
    "codegarden": False, "mcp": False, "sync": False,
    "tech_stack": False, "security_graph": False,
}
ALL_ON = dict.fromkeys(ALL_OFF, True)

# 代表性子路径 (从 ALL_OFF 构建中实测存在)
CORE_PATHS = [
    "/api/health",
    "/api/knowledge/items",
    "/api/search",
    "/api/todos",
    "/api/hotspots",
    "/api/trends",
    "/api/categories",
    "/api/favorites",
    "/api/content/calendar",
    "/api/export",
    "/api/refresh",
    "/api/cache/clear",
    "/api/events",
    "/api/attention/events",
    "/api/kl/metrics",
    "/api/kl/compounding",
    "/api/settings/features",
    "/api/secrets/status",
    "/api/skills",
    "/api/bid-alert/summary",
    "/api/weekly-report",
    "/api/tags",
    "/api/annotations",
    "/api/digests/latest",
    "/api/catchup/status",
    "/api/alerts/rules",
    "/api/llm/status",
]

EXTENSION_PATHS = {
    "codegarden": [
        "/api/codegarden/projects",
        "/api/codegarden/services",
        "/api/codegarden/drift/assessments",
        "/api/cve/sync",
    ],
    "mcp": [
        "/api/mcp/status",
        "/api/mcp/tools",
        "/api/profile",
        "/api/cubox/sync",
    ],
    "sync": ["/api/sync/status", "/api/sync/config"],
    "tech_stack": ["/api/tech-stack", "/api/tech-stack/impact"],
}

# job→扩展归属 (与 scheduler.py _JOB_EXT_MAP 一致)
JOB_EXT_MAP = {
    "sync": "sync",
    "cg_upstream_sync": "codegarden",
    "cg_service_scan": "codegarden",
    "cg_event_process": "codegarden",
    "cg_drift_assess": "tech_stack",
    "mitre_sync": "security_graph",
    "cve_sync_to_security": "security_graph",
}


def _route_paths(app: FastAPI) -> set[str]:
    """递归收集全部注册路径 (含 _IncludedRouter 嵌套)。"""
    paths: set[str] = set()
    stack = list(app.routes)
    while stack:
        r = stack.pop()
        path = getattr(r, "path", None)
        if path:
            paths.add(path)
            continue
        router = getattr(r, "original_router", None) or getattr(r, "router", None)
        if router is not None:
            stack.extend(router.routes)
    return paths


def build_app(monkeypatch: pytest.MonkeyPatch, gates: dict) -> FastAPI:
    """按给定 gates 重建 app — patch 贯穿 app 生命周期 (端点请求时仍生效)。"""
    import backend.extensions as extensions

    extensions.reset_gates()
    monkeypatch.setattr(
        extensions, "_load_gates", lambda: {**ALL_OFF, **gates}
    )
    app = FastAPI()
    register_routers(app)
    return app


@pytest.fixture(autouse=True)
def _reset_gates():
    """每个用例后清空缓存, 防止状态泄漏。"""
    yield
    from backend.extensions import reset_gates
    reset_gates()


class TestCoreRoutes:
    """core 路由在任意配置下都注册。"""

    def test_core_superset_under_all_on(self, monkeypatch):
        """全开配置下 core 路径全集仍是子集 (core 永不消失)。"""
        core = _route_paths(build_app(monkeypatch, ALL_OFF))
        all_on = _route_paths(build_app(monkeypatch, ALL_ON))
        missing = core - all_on
        assert not missing, f"core paths missing under ALL_ON: {sorted(missing)[:5]}"

    @pytest.mark.parametrize("path", CORE_PATHS)
    def test_core_always_registered(self, path, monkeypatch):
        app = build_app(monkeypatch, ALL_OFF)
        assert path in _route_paths(app), f"{path} should be registered (core)"

    def test_core_endpoints_not_404(self, monkeypatch, temp_db):
        """全关时核心端点实际可访问 (非 404)。"""
        app = build_app(monkeypatch, ALL_OFF)
        with TestClient(app) as client:
            for path in ["/api/health", "/api/settings/features", "/api/hotspots"]:
                resp = client.get(path)
                assert resp.status_code != 404, f"{path} should not be 404"


class TestExtensionGating:
    """扩展路由按 flag 注册/隐藏。"""

    @pytest.mark.parametrize("ext", list(EXTENSION_PATHS))
    def test_disabled_extension_404(self, ext, monkeypatch):
        app = build_app(monkeypatch, ALL_OFF)
        paths = _route_paths(app)
        for p in EXTENSION_PATHS[ext]:
            assert p not in paths, f"{p} should be hidden (extension {ext} off)"

    @pytest.mark.parametrize("ext", list(EXTENSION_PATHS))
    def test_enabled_extension_registered(self, ext, monkeypatch):
        gates = {**ALL_OFF, ext: True}
        app = build_app(monkeypatch, gates)
        paths = _route_paths(app)
        for p in EXTENSION_PATHS[ext]:
            assert p in paths, f"{p} should be registered (extension {ext} on)"

    def test_all_on_registers_all_extensions(self, monkeypatch):
        app = build_app(monkeypatch, ALL_ON)
        paths = _route_paths(app)
        for ext, ps in EXTENSION_PATHS.items():
            for p in ps:
                assert p in paths, f"{p} should be registered when all extensions on"

    def test_sync_default_enabled(self):
        """feature_gates.toml 默认 sync=true — 不注入时 sync 路由在。"""
        app = FastAPI()
        register_routers(app)
        assert "/api/sync/status" in _route_paths(app)


class TestJobGating:
    """scheduler job 按扩展归属过滤。"""

    @pytest.mark.parametrize("job_id,ext", list(JOB_EXT_MAP.items()))
    def test_job_disabled_when_extension_off(self, job_id, ext, monkeypatch):
        monkeypatch.setattr("backend.extensions._load_gates", lambda: ALL_OFF)
        from backend.scheduler.scheduler import _is_job_enabled
        assert not _is_job_enabled(job_id), f"{job_id} should be disabled (ext {ext} off)"

    @pytest.mark.parametrize("job_id", list(JOB_EXT_MAP))
    def test_job_enabled_when_extension_on(self, job_id, monkeypatch):
        gates = {**ALL_OFF, JOB_EXT_MAP[job_id]: True}
        monkeypatch.setattr("backend.extensions._load_gates", lambda: gates)
        from backend.scheduler.scheduler import _is_job_enabled
        assert _is_job_enabled(job_id), f"{job_id} should be enabled (ext on)"

    def test_core_jobs_never_gated(self, monkeypatch):
        monkeypatch.setattr("backend.extensions._load_gates", lambda: ALL_OFF)
        from backend.scheduler.scheduler import _is_job_enabled
        for core_id in ["collect_all", "trend_rebuild", "daily_snapshot", "digest_generator"]:
            assert _is_job_enabled(core_id), f"core job {core_id} must always run"

    def test_registered_job_count_matches_scheduler(self):
        """scheduler.py 中 add_job 数 = 43 (含 2 个新复利驱动器)。"""
        import ast
        from pathlib import Path
        src = Path("backend/scheduler/scheduler.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        n = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_job"
        )
        assert n == 43


class TestFeaturesEndpoint:
    """/api/settings/features 返回与 gates 一致。"""

    def test_all_off(self, monkeypatch):
        app = build_app(monkeypatch, ALL_OFF)
        with TestClient(app) as client:
            data = client.get("/api/settings/features").json()
        assert data["codegarden"] is False
        assert data["mcp"] is False
        assert data["sync"] is False
        assert data["tech_stack"] is False
        assert data["security_graph"] is False

    def test_all_on(self, monkeypatch):
        app = build_app(monkeypatch, ALL_ON)
        with TestClient(app) as client:
            data = client.get("/api/settings/features").json()
        assert data["codegarden"] is True
        assert data["mcp"] is True
        assert data["enabled_extensions"] == ["codegarden", "mcp", "sync", "tech_stack"]


class TestExtensionsModule:
    """extensions 模块自检。"""

    def test_is_extension_enabled_reads_toml(self, monkeypatch):
        from backend.extensions import is_extension_enabled, reset_gates
        # 绕过 conftest 的全开 env, 读真实 feature_gates.toml 默认值
        monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
        reset_gates()
        try:
            assert is_extension_enabled("codegarden") is False
            assert is_extension_enabled("mcp") is False
            assert is_extension_enabled("sync") is True
        finally:
            reset_gates()

    def test_core_extension_no_overlap(self):
        from backend.core.routers import CORE_ROUTERS
        from backend.extensions import EXTENSION_ROUTERS
        ext = {m for mods in EXTENSION_ROUTERS.values() for m in mods}
        assert not (CORE_ROUTERS & ext)

    def test_env_override(self, monkeypatch):
        import backend.extensions as extensions
        monkeypatch.setenv(
            "HOTSPOT_FEATURE_GATES",
            '{"extensions": {"codegarden": true, "mcp": true}}',
        )
        extensions.reset_gates()
        try:
            assert extensions.is_extension_enabled("codegarden") is True
            assert extensions.is_extension_enabled("sync") is True  # TOML 值保留
        finally:
            extensions.reset_gates()