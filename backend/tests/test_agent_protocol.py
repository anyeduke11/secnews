"""v1.7 Phase 5 — Agent 协议契约测试.

与 test_agent_cli.py 互补:
- test_agent_cli.py: 客户端行为 (mock HTTP, 验证请求格式)
- test_agent_protocol.py: 后端端点协议契约 (端到端验证请求/响应 schema)

覆盖 plan Task 5.4 Step 4 要求的协议层测试.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.services import agent_task_service as ats

import backend.services.knowledge_sync as ks


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_agent_protocol.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()

    # 任务文件目录
    tasks_root = tmp_path / "tasks"
    monkeypatch.setattr(ats, "TASKS_DIR", tasks_root)
    monkeypatch.setattr(ats, "PENDING_DIR", tasks_root / "pending")
    monkeypatch.setattr(ats, "DONE_DIR", tasks_root / "done")
    monkeypatch.setattr(ats, "FAILED_DIR", tasks_root / "failed")

    # knowledge 目录
    knowledge_root = tmp_path / "knowledge"
    items_dir = knowledge_root / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ks, "KNOWLEDGE_DIR", knowledge_root)
    monkeypatch.setattr(ks, "ITEMS_DIR", items_dir)

    yield {"db": test_db, "items_dir": items_dir}
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 协议层: GET /api/agent/tasks
# ---------------------------------------------------------------------------
class TestTasksEndpointProtocol:
    """GET /api/agent/tasks 端点协议契约."""

    def test_response_envelope(self, client):
        """响应必须是 {version, tasks} 字典."""
        r = client.get("/api/agent/tasks")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert "version" in body
        assert "tasks" in body
        assert body["version"] == "1.7.0"
        assert isinstance(body["tasks"], list)

    def test_task_item_schema(self, client):
        """每个 task 必须包含 task_id/task_type/status/target_type/target_id/priority/created_at/params."""
        ats.create_task("extract", "hotspot", "h-1")
        r = client.get("/api/agent/tasks")
        tasks = r.json()["tasks"]
        assert len(tasks) == 1
        t = tasks[0]
        # 必填字段
        for key in ("task_id", "task_type", "status", "target_type", "target_id", "priority", "created_at", "params"):
            assert key in t, f"missing field: {key}"
        # 类型
        assert isinstance(t["task_id"], int)
        assert t["task_type"] == "extract"
        assert t["status"] == "pending"
        assert isinstance(t["priority"], int)
        assert isinstance(t["params"], dict)

    def test_limit_param_respected(self, client):
        """limit 参数应限制返回条数."""
        for i in range(5):
            ats.create_task("extract", "hotspot", f"h-{i}")
        r = client.get("/api/agent/tasks", params={"limit": 3})
        assert len(r.json()["tasks"]) == 3

    def test_limit_bounds(self, client):
        """limit 必须 1-50."""
        # 过小
        r = client.get("/api/agent/tasks", params={"limit": 0})
        assert r.status_code == 422  # FastAPI 验证失败
        # 过大
        r = client.get("/api/agent/tasks", params={"limit": 100})
        assert r.status_code == 422

    def test_status_filter_semantics(self, client):
        """status=pending 只返回 pending; status=done 只返回 done."""
        ats.create_task("extract", "hotspot", "h-1")
        r1 = ats.create_task("compile", "knowledge", "k-1")
        ats.complete_task(r1["task_id"], "done")

        r = client.get("/api/agent/tasks", params={"status": "pending"})
        tasks = r.json()["tasks"]
        assert {t["task_type"] for t in tasks} == {"extract"}

        r = client.get("/api/agent/tasks", params={"status": "done"})
        tasks = r.json()["tasks"]
        assert {t["task_type"] for t in tasks} == {"compile"}


# ---------------------------------------------------------------------------
# 协议层: POST /api/agent/knowledge
# ---------------------------------------------------------------------------
class TestKnowledgeEndpointProtocol:
    """POST /api/agent/knowledge 端点协议契约."""

    def test_minimal_payload(self, client):
        """最小 payload (仅 item_id + lifecycle) 也能写入."""
        r = client.post("/api/agent/knowledge", json={
            "item_id": "min-1",
            "lifecycle": "signal",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["item_id"] == "min-1"
        assert body["lifecycle"] == "signal"

    def test_response_envelope(self, client):
        """响应必须是 {success, item_id, lifecycle}."""
        r = client.post("/api/agent/knowledge", json={
            "item_id": "x",
            "lifecycle": "generate",
        })
        body = r.json()
        assert set(body.keys()) >= {"success", "item_id", "lifecycle"}

    def test_missing_item_id_rejected(self, client):
        """缺少 item_id 必填字段应返回 422."""
        r = client.post("/api/agent/knowledge", json={"lifecycle": "signal"})
        assert r.status_code == 422

    def test_invalid_lifecycle_accepted_anyway(self, client):
        """任意 lifecycle 字符串都接受 (后端不强制枚举, 留给前端校验)."""
        r = client.post("/api/agent/knowledge", json={
            "item_id": "x",
            "lifecycle": "custom-stage",
        })
        assert r.status_code == 200
        assert r.json()["lifecycle"] == "custom-stage"

    def test_write_creates_md_file(self, client, temp_db):
        """写回必须落地 .md 文件 (双向环: DB ↔ .md)."""
        r = client.post("/api/agent/knowledge", json={
            "item_id": "proto-md-1",
            "title": "Protocol Test",
            "lifecycle": "signal",
            "tags": ["protocol"],
        })
        assert r.status_code == 200
        md = temp_db["items_dir"] / "proto-md-1.md"
        assert md.exists()
        content = md.read_text(encoding="utf-8")
        assert "Protocol Test" in content
        assert "lifecycle: \"signal\"" in content


# ---------------------------------------------------------------------------
# 协议层: POST /api/agent/tasks/{id}/complete
# ---------------------------------------------------------------------------
class TestCompleteEndpointProtocol:
    """POST /api/agent/tasks/{id}/complete 端点协议契约."""

    def test_done_status(self, client):
        """status=done 标记任务完成."""
        r1 = ats.create_task("publish", "knowledge", "k-1")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={"status": "done", "result": {"ok": True}, "error": ""},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["status"] == "done"

    def test_failed_status(self, client):
        """status=failed 标记任务失败."""
        r1 = ats.create_task("publish", "knowledge", "k-2")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={"status": "failed", "error": "boom"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "failed"

    def test_processing_status_accepted(self, client):
        """status=processing (新增) 也应接受."""
        r1 = ats.create_task("publish", "knowledge", "k-3")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={"status": "processing"},
        )
        assert r.status_code == 200

    def test_invalid_status_rejected(self, client):
        """非法 status 应返回 400."""
        r1 = ats.create_task("publish", "knowledge", "k-4")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={"status": "weird"},
        )
        assert r.status_code == 400

    def test_nonexistent_task_404(self, client):
        """不存在的 task_id 返回 404."""
        r = client.post(
            "/api/agent/tasks/99999/complete",
            json={"status": "done"},
        )
        assert r.status_code == 404

    def test_default_status_is_done(self, client):
        """不传 status 时默认 done."""
        r1 = ats.create_task("publish", "knowledge", "k-5")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "done"


# ---------------------------------------------------------------------------
# 协议层: GET /api/agent/tasks/{id}
# ---------------------------------------------------------------------------
class TestGetTaskEndpointProtocol:
    """GET /api/agent/tasks/{id} 端点协议契约."""

    def test_get_existing_task(self, client):
        """查询存在的 task 返回完整 task dict."""
        r1 = ats.create_task("extract", "hotspot", "h-99")
        r = client.get(f"/api/agent/tasks/{r1['task_id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["task_id"] == r1["task_id"]
        assert body["task_type"] == "extract"
        assert body["status"] == "pending"
        assert body["target_id"] == "h-99"

    def test_get_nonexistent_404(self, client):
        """查询不存在的 task 返回 404."""
        r = client.get("/api/agent/tasks/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 协议层: 错误格式
# ---------------------------------------------------------------------------
class TestErrorFormatProtocol:
    """所有错误响应格式应符合 project_memory §"API错误响应格式统一"."""

    def test_404_error_format(self, client):
        """404 错误响应包含 detail 字段."""
        r = client.get("/api/agent/tasks/99999")
        body = r.json()
        assert "detail" in body

    def test_400_error_format(self, client):
        """400 错误响应包含 detail 字段."""
        r1 = ats.create_task("publish", "knowledge", "k-err")
        r = client.post(
            f"/api/agent/tasks/{r1['task_id']}/complete",
            json={"status": "weird"},
        )
        body = r.json()
        assert "detail" in body
        # detail 可以是字符串或 dict
        assert body["detail"] is not None
