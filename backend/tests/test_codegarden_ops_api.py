"""Phase 2b CodeGarden API 单测 — 26 端点 (services + resources + dependencies + events + playbooks)."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api import codegarden_ops


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """独立临时 DB, 仅挂 Phase 2b router (避免 lifespan 启动 scheduler)."""
    db_file = tmp_path / "test_codegarden_ops_api.db"
    conn = sqlite3.connect(str(db_file))
    # 018: knowledge_tasks (restart/playbook/event 复用 knowledge_tasks 建任务)
    with open("backend/repository/migrations/018_knowledge.sql", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 019: cg_projects + skills ALTER (跳过 skills ALTER)
    with open("backend/repository/migrations/019_codegarden.sql", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    # 021: cg_services + cg_resources + cg_dependencies + cg_events
    with open("backend/repository/migrations/021_codegarden_phase2b.sql", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 060 (v0.4.0): cg_services.discovery_source (P5-4 校验状态)
    with open("backend/repository/migrations/060_v0.4_discovery_source.sql", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 080 (v0.7): audit_log (record_audit 表) — 取 audit_log 段 (从 CREATE TABLE 起)
    with open("backend/repository/migrations/080_v0.7_observability_tables.sql", encoding="utf-8") as f:
        obs_lines = f.read().splitlines()
    keep_lines = []
    started = False
    for ln in obs_lines:
        s = ln.strip()
        if s.startswith("CREATE TABLE IF NOT EXISTS audit_log"):
            started = True
        if started:
            keep_lines.append(ln)
    obs_sql = "\n".join(keep_lines)
    conn.executescript(obs_sql)
    # 013: encryption_keys (save_env_template 走 Fernet 加密需要默认主密钥)
    with open("backend/repository/migrations/013_secrets.sql", encoding="utf-8") as f:
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
    # 同时 patch 所有引用 get_connection 的 repo 模块
    import backend.repository.codegarden_orchestration_repo as orch_repo_mod
    import backend.repository.codegarden_resource_repo as rsc_repo_mod
    import backend.repository.codegarden_service_repo as svc_repo_mod
    monkeypatch.setattr(svc_repo_mod, "get_connection", _get_conn)
    monkeypatch.setattr(rsc_repo_mod, "get_connection", _get_conn)
    monkeypatch.setattr(orch_repo_mod, "get_connection", _get_conn)
    # service 层也直接 import get_connection (restart/playbook 走 asyncio.to_thread,
    # 未 patch 会命中真实 db 且在 worker 线程缓存 _tls.conn 泄漏到后续测试)
    import backend.services.codegarden_orchestration_service as orch_svc_mod
    import backend.services.codegarden_service_service as svc_svc_mod
    monkeypatch.setattr(svc_svc_mod, "get_connection", _get_conn)
    monkeypatch.setattr(orch_svc_mod, "get_connection", _get_conn)
    # observability_records 也直接 import get_connection (record_audit)
    import backend.observability_records as obs_mod
    monkeypatch.setattr(obs_mod, "get_connection", _get_conn)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(codegarden_ops.router)
    yield TestClient(app)


# ===========================================================================
# M2 Services (10 测试)
# ===========================================================================
def test_list_services_empty(client):
    r = client.get("/api/codegarden/services")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_service_returns_201(client):
    r = client.post("/api/codegarden/services", json={
        "name": "test-api", "type": "http", "runtime": "docker", "status": "running",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "test-api"
    assert data["type"] == "http"
    assert data["id"]


def test_create_service_invalid_type_returns_400(client):
    r = client.post("/api/codegarden/services", json={
        "name": "x", "type": "invalid", "runtime": "docker",
    })
    assert r.status_code == 400


def test_get_service_returns_404_when_not_exist(client):
    r = client.get("/api/codegarden/services/nonexistent-id")
    assert r.status_code == 404


def test_get_service_returns_record(client):
    create = client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "docker",
    })
    sid = create.json()["id"]
    r = client.get(f"/api/codegarden/services/{sid}")
    assert r.status_code == 200
    assert r.json()["name"] == "svc1"


def test_update_service(client):
    create = client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "docker",
    })
    sid = create.json()["id"]
    r = client.patch(f"/api/codegarden/services/{sid}", json={"status": "stopped"})
    assert r.status_code == 200
    assert r.json()["status"] == "stopped"


def test_delete_service(client):
    create = client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "docker",
    })
    sid = create.json()["id"]
    r = client.delete(f"/api/codegarden/services/{sid}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # 二次删除返回 404
    r2 = client.delete(f"/api/codegarden/services/{sid}")
    assert r2.status_code == 404


def test_get_topology(client):
    client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "docker",
    })
    r = client.get("/api/codegarden/services/topology")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 1


def test_restart_service_returns_202(client):
    create = client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "docker",
    })
    sid = create.json()["id"]
    r = client.post(f"/api/codegarden/services/{sid}/restart")
    assert r.status_code == 202
    assert "task_id" in r.json()


def test_get_logs_returns_200(client):
    """runtime=docker 但无 docker 命令时返回 error."""
    create = client.post("/api/codegarden/services", json={
        "name": "svc1", "type": "http", "runtime": "bare",
    })
    sid = create.json()["id"]
    r = client.get(f"/api/codegarden/services/{sid}/logs?tail=50")
    assert r.status_code == 200
    data = r.json()
    # bare runtime 不支持, 返回 error message
    assert "error" in data or "lines" in data


# ===========================================================================
# M3 Resources (8 测试)
# ===========================================================================
def test_list_resources_empty(client):
    r = client.get("/api/codegarden/resources")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_create_resource_returns_201(client):
    r = client.post("/api/codegarden/resources", json={
        "type": "domain", "value": "test.local", "status": "free",
    })
    assert r.status_code == 201
    assert r.json()["value"] == "test.local"


def test_get_resource_returns_404(client):
    r = client.get("/api/codegarden/resources/nonexistent-id")
    assert r.status_code == 404


def test_delete_resource(client):
    create = client.post("/api/codegarden/resources", json={
        "type": "domain", "value": "test.local",
    })
    rid = create.json()["id"]
    r = client.delete(f"/api/codegarden/resources/{rid}")
    assert r.status_code == 200


def test_allocate_port_returns_201(client):
    """分配端口 (preferred_port=8767; 8765/8766 已被本机外部进程占用, 2026-08-28 改)."""
    r = client.post("/api/codegarden/resources/allocate-port", json={
        "preferred_port": 8767,
    })
    assert r.status_code == 201
    assert r.json()["value"] == "8767"
    assert r.json()["status"] == "allocated"


def test_allocate_protected_port_8898_returns_403(client):
    r = client.post("/api/codegarden/resources/allocate-port", json={
        "preferred_port": 8898,
    })
    assert r.status_code == 403
    assert "受保护" in r.json()["detail"]


def test_release_port_returns_record(client):
    client.post("/api/codegarden/resources/allocate-port", json={"preferred_port": 8767})
    r = client.post("/api/codegarden/resources/release-port", json={"port": 8767})
    assert r.status_code == 200
    assert r.json()["status"] == "free"


def test_release_protected_port_8898_returns_403(client):
    r = client.post("/api/codegarden/resources/release-port", json={"port": 8898})
    assert r.status_code == 403
    assert "受保护" in r.json()["detail"]


# ===========================================================================
# M4 Dependencies (5 测试)
# ===========================================================================
def test_create_dependency_returns_201(client):
    r = client.post("/api/codegarden/dependencies", json={
        "source_type": "project", "source_id": "a",
        "target_type": "project", "target_id": "b",
        "dep_type": "code",
    })
    assert r.status_code == 201
    assert r.json()["source_id"] == "a"


def test_create_dependency_duplicate_returns_409(client):
    payload = {
        "source_type": "project", "source_id": "a",
        "target_type": "project", "target_id": "b",
        "dep_type": "code",
    }
    client.post("/api/codegarden/dependencies", json=payload)
    r = client.post("/api/codegarden/dependencies", json=payload)
    assert r.status_code == 409
    assert "已存在" in r.json()["detail"]


def test_list_dependencies_filter(client):
    client.post("/api/codegarden/dependencies", json={
        "source_type": "project", "source_id": "a",
        "target_type": "project", "target_id": "b",
        "dep_type": "code",
    })
    r = client.get("/api/codegarden/dependencies?source_id=a")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_delete_dependency(client):
    create = client.post("/api/codegarden/dependencies", json={
        "source_type": "project", "source_id": "a",
        "target_type": "project", "target_id": "b",
        "dep_type": "code",
    })
    did = create.json()["id"]
    r = client.delete(f"/api/codegarden/dependencies/{did}")
    assert r.status_code == 200


def test_dependency_crud_syncs_service_json(client):
    """service→service 依赖 CRUD 后, cg_services.dependencies 冗余列随真相源同步."""
    svc_a = client.post("/api/codegarden/services", json={
        "name": "dep-svc-a", "type": "http", "runtime": "docker",
    }).json()
    svc_b = client.post("/api/codegarden/services", json={
        "name": "dep-svc-b", "type": "http", "runtime": "docker",
    }).json()

    # 创建依赖 a→b 后, service a 的 dependencies 包含 b
    create = client.post("/api/codegarden/dependencies", json={
        "source_type": "service", "source_id": svc_a["id"],
        "target_type": "service", "target_id": svc_b["id"],
        "dep_type": "service",
    })
    assert create.status_code == 201
    got = client.get(f"/api/codegarden/services/{svc_a['id']}").json()
    assert got["dependencies"] == [svc_b["id"]]

    # 删除依赖后, dependencies 回空
    did = create.json()["id"]
    assert client.delete(f"/api/codegarden/dependencies/{did}").status_code == 200
    got = client.get(f"/api/codegarden/services/{svc_a['id']}").json()
    assert got["dependencies"] == []


def test_impact_analysis(client):
    """a→b, c→b, 修改 b 影响哪些 source? → a 和 c."""
    for src in ["a", "c"]:
        client.post("/api/codegarden/dependencies", json={
            "source_type": "project", "source_id": src,
            "target_type": "project", "target_id": "b",
            "dep_type": "code",
        })
    r = client.get("/api/codegarden/dependencies/impact?target_type=project&target_id=b")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    sources = {d["source_id"] for d in data["impacts"]}
    assert sources == {"a", "c"}


# ===========================================================================
# M4 Events (3 测试)
# ===========================================================================
def test_publish_event_returns_201(client):
    r = client.post("/api/codegarden/events", json={
        "event_type": "port_conflict",
        "source_type": "service",
        "source_id": "svc-1",
        "payload": {"port": 8080},
    })
    assert r.status_code == 201
    data = r.json()
    assert "event" in data
    assert data["event"]["status"] == "pending"
    assert "task_id" in data


def test_list_events_filter_by_status(client):
    client.post("/api/codegarden/events", json={
        "event_type": "port_conflict",
        "source_type": "service", "source_id": "a",
    })
    r = client.get("/api/codegarden/events?status=pending")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_publish_event_invalid_type_returns_400(client):
    r = client.post("/api/codegarden/events", json={
        "event_type": "invalid",
        "source_type": "service", "source_id": "a",
    })
    assert r.status_code == 400


# ===========================================================================
# M4 Playbooks (3 测试)
# ===========================================================================
def test_list_playbooks_returns_existing(client):
    """playbooks 列表至少包含 example.yml (Phase 2b I2 已初始化)."""
    r = client.get("/api/codegarden/playbooks")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    # 至少有一个 .yml 文件
    names = [pb.get("name") for pb in data.get("items", [])]
    assert "example" in names or any(n for n in names), f"应包含 example.yml: {names}"


def test_run_playbook_not_exist_returns_404(client):
    r = client.post("/api/codegarden/playbooks/nonexistent/run", json={"params": {}})
    assert r.status_code == 404


def test_run_playbook_returns_202(tmp_path, monkeypatch):
    """需 mock PLAYBOOKS_DIR, 用独立 fixture."""
    # 创建临时 playbook (Phase C 新引擎 schema: metadata + steps with kind=skill/api)
    pb_dir = tmp_path / "playbooks"
    pb_dir.mkdir()
    (pb_dir / "test-pb.yml").write_text(
        "kind: Playbook\nmetadata:\n  name: test-pb\n  desc: 'unit test playbook'\nsteps:\n"
        "  - id: step1\n    kind: api\n    action: GET /api/_dummy\n    output: api_result\n",
        encoding="utf-8",
    )

    # 重新初始化 DB + client
    db_file = tmp_path / "test_pb.db"
    conn = sqlite3.connect(str(db_file))
    # 018: knowledge_tasks (playbook_run 复用 knowledge_tasks 建任务)
    with open("backend/repository/migrations/018_knowledge.sql", encoding="utf-8") as f:
        conn.executescript(f.read())
    with open("backend/repository/migrations/019_codegarden.sql", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    with open("backend/repository/migrations/021_codegarden_phase2b.sql", encoding="utf-8") as f:
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
    import backend.repository.codegarden_orchestration_repo as orch_repo_mod
    import backend.repository.codegarden_resource_repo as rsc_repo_mod
    import backend.repository.codegarden_service_repo as svc_repo_mod
    monkeypatch.setattr(svc_repo_mod, "get_connection", _get_conn)
    monkeypatch.setattr(rsc_repo_mod, "get_connection", _get_conn)
    monkeypatch.setattr(orch_repo_mod, "get_connection", _get_conn)

    # patch PLAYBOOKS_DIR
    import backend.services.codegarden_orchestration_service as orch_svc_mod
    monkeypatch.setattr(orch_svc_mod, "PLAYBOOKS_DIR", pb_dir)
    # service 层直接 import get_connection: playbook_run 走 asyncio.to_thread,
    # 未 patch 会命中真实 db (缺 knowledge_tasks) 并泄漏 _tls.conn
    import backend.services.codegarden_service_service as svc_svc_mod
    monkeypatch.setattr(svc_svc_mod, "get_connection", _get_conn)
    monkeypatch.setattr(orch_svc_mod, "get_connection", _get_conn)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(codegarden_ops.router)
    c = TestClient(app)

    r = c.post("/api/codegarden/playbooks/test-pb/run", json={"params": {}})
    assert r.status_code == 202
    data = r.json()
    assert data["playbook_name"] == "test-pb"
    assert "task_id" in data


# ===========================================================================
# M3 env_template audit (Batch ⑦ T2 — codegarden secrets 全量审计)
# ===========================================================================
def test_save_env_template_writes_audit_log(client):
    """save_env_template 落 audit_log (action=codegarden.env_template.save)."""
    r = client.post("/api/codegarden/resources/env-templates", json={
        "name": "production",
        "env_vars": {"API_KEY": "secret-value", "DEBUG": "false"},
        "owner_project_id": None,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    # cg_resources 行: value=模板名, type=env_template
    assert body["value"] == "production"
    assert body["type"] == "env_template"

    # 验 audit_log — 直接走 monkeypatch 后的 get_connection
    from backend.repository import db as db_mod
    probe = db_mod.get_connection()
    try:
        row = probe.execute(
            "SELECT action, target, detail FROM audit_log "
            "WHERE action='codegarden.env_template.save' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        probe.close()
    assert row is not None, "audit_log 未写入 env_template.save"
    assert row["action"] == "codegarden.env_template.save"
    assert row["target"].startswith("resource:")
    import json as _json
    detail = _json.loads(row["detail"])
    assert detail["name"] == "production"
    assert detail["var_count"] == 2
