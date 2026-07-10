"""Phase 8 需求 8.2: 采集间隔驱动前端刷新 — /api/health 单测。

新增字段：
- collect_interval_seconds (int, 来自 config.collect_interval_seconds)

策略
----
- 直接构造 TestClient(backend.main:app), 触发 lifespan。
- init_db / scheduler / warmup 都走真实路径, 确保端到端可访问。
"""
from __future__ import annotations


def test_health_exposes_collect_interval():
    """Phase 8 Addendum 需求 8.2: /api/health 必须暴露 collect_interval_seconds"""
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "collect_interval_seconds" in data
    assert isinstance(data["collect_interval_seconds"], int)
    assert data["collect_interval_seconds"] > 0
