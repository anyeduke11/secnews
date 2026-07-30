"""v1.8 Phase 8 — catchup API endpoint 单测.

覆盖 (10 用例):
  - D3.1 POST /api/catchup/run 触发成功 → 202 + run_id
  - D3.2 POST /api/catchup/run 缺 since → 400
  - D3.3 POST /api/catchup/run since 格式错 → 400
  - D3.4 POST /api/catchup/run 已有 manual 在跑 → 409
  - D3.5 GET  /api/catchup/status 返回 current + recent
  - D3.6 POST /api/catchup/abort 中止 manual → ok
  - D3.7 POST /api/catchup/abort 无 manual → ok=False
  - D3.8 POST /api/catchup/abort run_id 不存在 → 404
  - D3.9 POST /api/catchup/auto 不受 manual 锁约束
  - D3.10 GET  /api/catchup/runs/{run_id} 不存在 → 404
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import config
from backend.repository import db
from backend.services import catchup_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path, 通过 init_db() 应用全部 migrations."""
    test_db = tmp_path / "test_catchup_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def reset_catchup_module_state():
    """重置 catchup_service 的模块级状态."""
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None
    if catchup_service._lock.locked():
        try:
            catchup_service._lock.release()
        except RuntimeError:
            pass
    yield
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None


@pytest.fixture
def client(temp_db):
    """创建 FastAPI TestClient, 隔离 DB."""
    from backend.main import app

    with TestClient(app) as c:
        yield c


def _patch_execute_noop():
    """替换 _execute_catchup_run 为 noop, 避免测试中触发真抓取."""
    return patch.object(
        catchup_service,
        "_execute_catchup_run",
        new=AsyncMock(),
    )


# ---------------------------------------------------------------------------
# D3.1 — POST /api/catchup/run 触发成功
# ---------------------------------------------------------------------------
def test_post_run_returns_202_with_run_id(client):
    """正常触发 manual catchup, 期望 202 + run_id."""
    since = "2026-07-24T00:00:00+00:00"
    with _patch_execute_noop():
        resp = client.post(
            "/api/catchup/run",
            json={
                "since": since,
                "until": None,
                "categories": ["ai", "security"],
                "max_per_source": 15,
            },
        )
    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    assert body["run_id"] > 0
    assert body["status"] == "running"
    assert body["mode"] == "manual"
    assert body["since"] == since
    assert body["max_per_source"] == 15
    assert body["categories"] == ["ai", "security"]


# ---------------------------------------------------------------------------
# D3.2 — POST /api/catchup/run 缺 since → 400
# ---------------------------------------------------------------------------
def test_post_run_missing_since_returns_400(client):
    """since 必填, 缺了报 400."""
    resp = client.post(
        "/api/catchup/run",
        json={"until": None, "categories": [], "max_per_source": 10},
    )
    # Pydantic 422 (validation error) 算作参数错误, 服务端业务错误用 400
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# D3.3 — POST /api/catchup/run since 格式错 → 400/422
# ---------------------------------------------------------------------------
def test_post_run_invalid_since_format_returns_400(client):
    """since 不是合法 ISO 8601 → 422."""
    resp = client.post(
        "/api/catchup/run",
        json={"since": "not-a-date", "until": None, "categories": [], "max_per_source": 10},
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# D3.4 — POST /api/catchup/run 已有 manual 在跑 → 409
# ---------------------------------------------------------------------------
def test_post_run_conflict_when_manual_active(client):
    """当前 manual 在跑时, 再 enqueue manual 应返回 409."""
    # 模拟一个 manual 正在跑: 占 lock + _current_manual_run
    catchup_service._current_manual_run = 999
    with patch.object(catchup_service, "_lock") as mock_lock:
        mock_lock.locked.return_value = True
        # mock_lock 不再是真实的 Lock, 所以 _lock.locked() 会返回 True
        resp = client.post(
            "/api/catchup/run",
            json={"since": "2026-07-24T00:00:00+00:00", "until": None,
                  "categories": [], "max_per_source": 10},
        )
    assert resp.status_code == 409
    body = resp.json()
    # detail 可能是 dict 或直接 message
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        assert "active_run_id" in detail or "message" in detail


# ---------------------------------------------------------------------------
# D3.5 — GET /api/catchup/status
# ---------------------------------------------------------------------------
def test_get_status_returns_current_and_recent(client):
    """GET /api/catchup/status 返回 current + recent + last_orphan_recovery_at."""
    since = "2026-07-24T00:00:00+00:00"
    with _patch_execute_noop():
        # 先创建 2 条 run (1 manual + 1 auto)
        r1 = client.post("/api/catchup/run", json={
            "since": since, "until": None, "categories": [], "max_per_source": 10,
        })
        assert r1.status_code == 202
        r2 = client.post("/api/catchup/auto", json={
            "since": since, "until": None, "categories": [], "max_per_source": 10,
        })
        assert r2.status_code == 202

    # 状态查询
    resp = client.get("/api/catchup/status?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "current_running" in body
    assert "recent" in body
    assert "current_manual_run_id" in body
    assert "last_orphan_recovery_at" in body
    # 预期 2 条：1 manual + 1 auto (v1.8: 测试中启动钩子自动追抓已被
    # conftest._disable_startup_catchup 关闭, 不再产生额外 run)
    assert body["total_recent"] == 2
    assert len(body["recent"]) == 2
    # current_running 应是最近一条
    assert body["current_running"] is not None
    assert body["current_running"]["status"] == "running"


# ---------------------------------------------------------------------------
# D3.6 — POST /api/catchup/abort 中止 manual
# ---------------------------------------------------------------------------
def test_post_abort_cancels_current_manual(client):
    """abort 中止当前 manual, 返回 ok=True + aborted_run_id."""
    since = "2026-07-24T00:00:00+00:00"
    with _patch_execute_noop():
        r1 = client.post("/api/catchup/run", json={
            "since": since, "until": None, "categories": [], "max_per_source": 10,
        })
    run_id = r1.json()["run_id"]

    # 中止
    resp = client.post("/api/catchup/abort", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["aborted_run_id"] == run_id

    # DB 状态应为 aborted
    detail = client.get(f"/api/catchup/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "aborted"


# ---------------------------------------------------------------------------
# D3.7 — POST /api/catchup/abort 无 manual → ok=False
# ---------------------------------------------------------------------------
def test_post_abort_no_current_returns_ok_false(client):
    """没有 manual 在跑时, abort 返回 ok=False + aborted_run_id=None."""
    # 不创建任何 run
    resp = client.post("/api/catchup/abort", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["aborted_run_id"] is None


# ---------------------------------------------------------------------------
# D3.8 — POST /api/catchup/abort run_id 不存在 → 404
# ---------------------------------------------------------------------------
def test_post_abort_unknown_run_id_returns_404(client):
    """abort 指定 run_id=99999, 不存在 → 404."""
    resp = client.post("/api/catchup/abort", json={"run_id": 99999})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# D3.9 — POST /api/catchup/auto 不受 manual 锁约束
# ---------------------------------------------------------------------------
def test_post_auto_does_not_block_on_manual(client):
    """即使有 manual 在跑, auto 仍能 enqueue."""
    # 占 manual
    catchup_service._current_manual_run = 888
    with _patch_execute_noop():
        resp = client.post(
            "/api/catchup/auto",
            json={"since": "2026-07-24T00:00:00+00:00", "until": None,
                  "categories": [], "max_per_source": 10},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["mode"] == "auto"
    assert body["run_id"] > 0


# ---------------------------------------------------------------------------
# D3.10 — GET /api/catchup/runs/{run_id} 不存在 → 404
# ---------------------------------------------------------------------------
def test_get_run_unknown_id_returns_404(client):
    """GET /api/catchup/runs/99999 → 404."""
    resp = client.get("/api/catchup/runs/99999")
    assert resp.status_code == 404
