"""test_cve_compliance_routes.py — CVE 分析/合规矩阵路由契约测试。

回归防线: cve_analytics.py 与 compliance.py 曾漏 ``/api`` prefix, 路由暴露在
``/cve/*`` ``/compliance/*``, 而前端统一请求 ``/api/cve/*`` ``/api/compliance/*``
全部 404 (2026-09-19 修复, 症状: 热力图空白 / ATT&CK 按钮恒 disabled /
合规矩阵永久 loading)。静态断言注册路径, 防同类回归。
"""
from __future__ import annotations

from fastapi import FastAPI

from backend.api import register_routers
from backend.tests.test_feature_gates import _route_paths

EXPECTED_PATHS = (
    "/api/cve/heatmap",
    "/api/cve/recent",
    "/api/cve/attack-mapping",
    "/api/cve/attack-data/load",
    "/api/compliance/frameworks",
    "/api/compliance/matrix",
    "/api/compliance/controls/{event_type}",
)


def test_cve_and_compliance_routes_registered_under_api() -> None:
    app = FastAPI()
    register_routers(app)
    paths = _route_paths(app)
    for p in EXPECTED_PATHS:
        assert p in paths, f"{p} 未注册 — 对应 leaf router 可能漏 /api prefix"
