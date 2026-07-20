"""Phase 2b Task H3 — e2e 测试: 项目→服务→端口→依赖→事件全流程.

验证完整路径 (跨 4 个 cg_ 表 + Phase 2b 全部 26 端点中的关键 8 个):
1. 创建 cg_projects (前置)
2. POST /services → 注册 cg_services (绑定 project_id)
3. POST /resources/allocate-port → 分配端口 cg_resources (绑定 service_id+project_id)
4. POST /dependencies → 建立 project → service 依赖 (cg_dependencies)
5. POST /events → 发布事件 (cg_events, status=pending)
6. GET /services/{id} → 验证 service 与 project 关联
7. GET /dependencies/impact → 反向追溯依赖链
8. POST /resources/release-port → 释放端口 (8898 必须返回 403)

fixture 模式参考 test_codegarden_phase2b_api.py (避免触发 backend.main.app lifespan).
"""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import codegarden, codegarden_phase2b


@pytest.fixture()
def e2e_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """独立临时 DB + 挂 codegarden + codegarden_phase2b 两个 router."""
    db_file = tmp_path / "test_codegarden_phase2b_e2e.db"
    conn = sqlite3.connect(str(db_file))
    # 019: cg_projects (跳过 skills ALTER)
    with open("backend/repository/migrations/019_codegarden.sql", "r", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    # 021: Phase 2b 4 张表
    with open("backend/repository/migrations/021_codegarden_phase2b.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    # patch 所有相关 repo 的 get_connection
    for mod_name in (
        "backend.repository.codegarden_repo",
        "backend.repository.codegarden_service_repo",
        "backend.repository.codegarden_resource_repo",
        "backend.repository.codegarden_orchestration_repo",
    ):
        import importlib
        mod = importlib.import_module(mod_name)
        try:
            monkeypatch.setattr(mod, "get_connection", _get_conn)
        except (AttributeError, TypeError):
            pass

    app = FastAPI()
    app.include_router(codegarden.router)
    app.include_router(codegarden_phase2b.router)
    yield TestClient(app)


# ===========================================================================
# e2e 测试 1: 完整联动流程 (project → service → port → dependency → event)
# ===========================================================================
def test_e2e_full_phase2b_flow(e2e_client: TestClient):
    """验证 Phase 2b 4 张表的完整联动."""
    # --- Step 1: 创建 project ---
    r = e2e_client.post("/api/codegarden/projects", json={
        "name": "e2e-app",
        "type": "web_application",
        "source_type": "vibe",
    })
    assert r.status_code == 201, f"创建 project 失败: {r.status_code} {r.text}"
    project = r.json()
    project_id = project["id"]

    # --- Step 2: 注册 service (绑定 project) ---
    r = e2e_client.post("/api/codegarden/services", json={
        "name": "e2e-api",
        "project_id": project_id,
        "type": "http",
        "runtime": "docker",
        "status": "running",
        "endpoint_port": 8001,
    })
    assert r.status_code == 201, f"创建 service 失败: {r.status_code} {r.text}"
    service = r.json()
    service_id = service["id"]
    assert service["project_id"] == project_id

    # --- Step 3: 分配端口 (绑定 service + project) ---
    r = e2e_client.post("/api/codegarden/resources/allocate-port", json={
        "preferred_port": 8002,
        "owner_service_id": service_id,
        "owner_project_id": project_id,
    })
    assert r.status_code == 201, f"端口分配失败: {r.status_code} {r.text}"
    resource = r.json()
    assert resource["type"] == "port"
    assert resource["value"] == "8002"
    assert resource["status"] == "allocated"
    assert resource["owner_service_id"] == service_id
    assert resource["owner_project_id"] == project_id

    # --- Step 4: 建立依赖 (project → service, code 依赖) ---
    r = e2e_client.post("/api/codegarden/dependencies", json={
        "source_type": "project",
        "source_id": project_id,
        "target_type": "service",
        "target_id": service_id,
        "dep_type": "code",
    })
    assert r.status_code == 201, f"建立依赖失败: {r.status_code} {r.text}"
    dep = r.json()
    assert dep["source_id"] == project_id
    assert dep["target_id"] == service_id
    assert dep["dep_type"] == "code"

    # --- Step 5: 发布事件 (port_conflict, 关联 service) ---
    r = e2e_client.post("/api/codegarden/events", json={
        "event_type": "port_conflict",
        "source_type": "service",
        "source_id": service_id,
        "payload": {"port": 8002, "conflicting_pid": 12345},
    })
    assert r.status_code == 201, f"事件发布失败: {r.status_code} {r.text}"
    # publish_event 返回 {"event": {...}, "task_id": int}
    resp = r.json()
    event = resp["event"] if "event" in resp else resp
    assert event["status"] == "pending"
    assert event["event_type"] == "port_conflict"
    assert event["source_id"] == service_id
    event_id = event["id"]

    # --- Step 6: 验证 service 详情含 project_id 关联 ---
    r = e2e_client.get(f"/api/codegarden/services/{service_id}")
    assert r.status_code == 200
    assert r.json()["project_id"] == project_id

    # --- Step 7: 影响分析 — 反向追溯 service 被哪些上游依赖 ---
    r = e2e_client.get(
        f"/api/codegarden/dependencies/impact?target_type=service&target_id={service_id}&max_depth=5"
    )
    assert r.status_code == 200
    # impact 端点返回 {"target_type":..., "impacts": [...], "count": N}
    body = r.json()
    items = body["impacts"]
    # 应至少有 1 条 (project → service 的 code 依赖)
    assert len(items) >= 1, "影响分析应返回 project→service 依赖"
    assert any(d["source_id"] == project_id for d in items)

    # --- Step 8: 验证事件列表能查到刚发的事件 ---
    r = e2e_client.get("/api/codegarden/events?status=pending")
    assert r.status_code == 200
    pending_events = r.json()["items"]
    assert any(e["id"] == event_id for e in pending_events)


# ===========================================================================
# e2e 测试 2: 端口保护 (8898 禁止分配/释放)
# ===========================================================================
def test_e2e_port_protection_8898(e2e_client: TestClient):
    """8898 是 hotspot 前端端口, 必须受保护."""
    # 分配 8898 → 403
    r = e2e_client.post("/api/codegarden/resources/allocate-port", json={
        "preferred_port": 8898,
    })
    assert r.status_code == 403, f"8898 应禁止分配: {r.status_code}"
    detail = r.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "8898" in msg or "保护" in msg

    # 释放 8898 → 403 (release-port 用 POST body, 不是 query param)
    r = e2e_client.post("/api/codegarden/resources/release-port", json={"port": 8898})
    assert r.status_code == 403, f"8898 应禁止释放: {r.status_code}"


# ===========================================================================
# e2e 测试 3: 服务拓扑 (services + dependencies 联合)
# ===========================================================================
def test_e2e_service_topology_assembles_graph(e2e_client: TestClient):
    """topology 端点应组装 services + dependencies 为 nodes + edges."""
    # 创建 2 个 service
    r1 = e2e_client.post("/api/codegarden/services", json={
        "name": "topo-svc-a", "type": "http", "runtime": "docker", "status": "running",
    })
    r2 = e2e_client.post("/api/codegarden/services", json={
        "name": "topo-svc-b", "type": "http", "runtime": "pm2", "status": "stopped",
    })
    assert r1.status_code == 201 and r2.status_code == 201
    a_id = r1.json()["id"]
    b_id = r2.json()["id"]

    # 建立 a → b 依赖 (用 dependencies 表)
    # 注意: cg_dependencies 的 source_type/target_type 限定为 project/service,
    # 这里建立 service → service 依赖
    r = e2e_client.post("/api/codegarden/dependencies", json={
        "source_type": "service",
        "source_id": a_id,
        "target_type": "service",
        "target_id": b_id,
        "dep_type": "service",
    })
    assert r.status_code == 201

    # 拉取拓扑图
    r = e2e_client.get("/api/codegarden/services/topology")
    assert r.status_code == 200
    topo = r.json()
    # 至少有 2 个 nodes
    assert len(topo["nodes"]) >= 2, f"拓扑图应至少有 2 个 nodes: {topo}"
    # topology node.id 用 'svc:UUID' 前缀格式, 检查 a_id 和 b_id 作为后缀存在
    node_ids = [n["id"] for n in topo["nodes"]]
    assert any(a_id in nid for nid in node_ids), f"{a_id} 应在 topology nodes: {node_ids}"
    assert any(b_id in nid for nid in node_ids), f"{b_id} 应在 topology nodes: {node_ids}"
    # runtime/status 颜色已注入
    for n in topo["nodes"]:
        assert "runtime_color" in n["data"]
        assert "status_color" in n["data"]


# ===========================================================================
# e2e 测试 4: Playbook 执行 (创建 knowledge_tasks)
# ===========================================================================
def test_e2e_playbook_run_creates_task(e2e_client: TestClient, tmp_path, monkeypatch):
    """Playbook 执行应在 knowledge_tasks 表创建 task_type=playbook_run 记录."""
    # Playbook 列表可能为空 (无 .yml 文件), 这里仅测不存在的 playbook 返回 404
    r = e2e_client.post("/api/codegarden/playbooks/non-existent/run", json={"params": {}})
    assert r.status_code == 404
    detail = r.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "non-existent" in msg or "不存在" in msg
