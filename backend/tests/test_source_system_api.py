"""source_system_api 测试 (数据源治理 T2).

锁定的契约 (设计稿 §3.3 + 任务书):
1. DELETE 不带 reason → 422 拒绝 (审计强制, 破坏性动作必须留原因)
2. DELETE 带 reason → 先审计 (crawler_sources 层, executed_by=owner) 再删,
   且级联删同名 source_stats 行 (含跨类目重复行)
3. PATCH toggle enabled → 生效 + 审计
4. GET /system → 注册层列表, 含 media_kind/status/enabled/notes 字段
5. 未知 sid → 404

执行:
    python -m pytest backend/tests/test_source_system_api.py -v
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.source_system_api import router as system_router
from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_system_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    app = FastAPI()
    app.include_router(system_router)
    yield TestClient(app)
    db.close_db()


def _insert_crawler_source(
    sid: str,
    *,
    name: str | None = None,
    status: str = "active",
    enabled: int = 1,
    media_kind: str = "web",
    notes: str | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, status, priority, enabled,
             consecutive_failures, health_score, media_kind, notes,
             created_at, updated_at)
        VALUES (?, 'security', ?, 'html', ?, 50, ?, 0, 1.0, ?, ?,
                datetime('now'), datetime('now'))
        """,
        (sid, name or sid, status, enabled, media_kind, notes),
    )


def _insert_stat(name: str, *, status: str = "dead", total_items: int = 0,
                 category: str = "security") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO source_stats (category, source_name, source_url, status, total_items, updated_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (category, name, f"https://example.com/{name}", status, total_items),
    )


def _seed_all() -> None:
    _insert_crawler_source("security:待删源", name="待删源", status="retired", enabled=0)
    _insert_crawler_source("security:保留源", name="保留源")
    _insert_stat("待删源")
    _insert_stat("待删源", category="ai", total_items=5)  # 跨类目同名重复行
    _insert_stat("保留源", total_items=99)


def _audit_count(conn, ident: str | None = None) -> int:
    if ident is None:
        return conn.execute("SELECT COUNT(*) FROM source_cleanup_log").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM source_cleanup_log WHERE source_ident = ?", (ident,)
    ).fetchone()[0]


class TestDeleteSystemSource:
    def test_delete_without_reason_rejected_422(self, client):
        _seed_all()
        before = get_connection().execute(
            "SELECT COUNT(*) FROM crawler_sources"
        ).fetchone()[0]

        resp = client.delete("/api/sources/system/security:待删源")

        assert resp.status_code == 422
        assert _audit_count(get_connection()) == 0, "拒绝时不得留审计"
        assert get_connection().execute(
            "SELECT COUNT(*) FROM crawler_sources"
        ).fetchone()[0] == before

    def test_delete_audits_then_cascades_same_name_stats(self, client):
        _seed_all()

        resp = client.delete(
            "/api/sources/system/security:待删源",
            params={"reason": "长期无产出, owner 手动清理"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["stats_rows_deleted"] == 2, "同名统计行跨类目级联删除"

        conn = get_connection()
        assert conn.execute(
            "SELECT COUNT(*) FROM crawler_sources WHERE id='security:待删源'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM source_stats WHERE source_name='待删源'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM source_stats WHERE source_name='保留源'"
        ).fetchone()[0] == 1, "非同名行不受波及"

        logs = conn.execute(
            "SELECT source_layer, source_ident, reason, executed_by FROM source_cleanup_log"
        ).fetchall()
        assert len(logs) == 1
        assert logs[0]["source_layer"] == "crawler_sources"
        assert logs[0]["source_ident"] == "待删源"
        assert logs[0]["reason"] == "长期无产出, owner 手动清理"
        assert logs[0]["executed_by"] == "owner"

    def test_delete_unknown_sid_404(self, client):
        resp = client.delete("/api/sources/system/nope", params={"reason": "x"})
        assert resp.status_code == 404


class TestToggleSystemSource:
    def test_patch_toggles_enabled_and_audits(self, client):
        _seed_all()

        resp = client.patch(
            "/api/sources/system/security:保留源", json={"enabled": False}
        )

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "id": "security:保留源", "enabled": False}
        conn = get_connection()
        assert conn.execute(
            "SELECT enabled FROM crawler_sources WHERE id='security:保留源'"
        ).fetchone()[0] == 0
        assert _audit_count(conn, "保留源") == 1
        reason = conn.execute(
            "SELECT reason FROM source_cleanup_log WHERE source_ident='保留源'"
        ).fetchone()[0]
        assert "enabled=false" in reason

    def test_patch_unknown_sid_404(self, client):
        resp = client.patch("/api/sources/system/nope", json={"enabled": True})
        assert resp.status_code == 404


class TestListSystemSources:
    def test_get_returns_registry_shape_for_matrix(self, client):
        _seed_all()

        resp = client.get("/api/sources/system")

        assert resp.status_code == 200
        sources = resp.json()["sources"]
        by_id = {s["id"]: s for s in sources}
        # 全链迁移自带 2 个 YouTube 多媒体种子行, 这里只锁定 seed 行的契约
        assert {"security:待删源", "security:保留源"} <= set(by_id)
        row = by_id["security:保留源"]
        # 前端矩阵消费的字段契约
        for key in ("media_kind", "status", "enabled", "notes", "name", "category"):
            assert key in row
        assert row["media_kind"] == "web"
        assert row["enabled"] == 1
        disabled = by_id["security:待删源"]
        assert disabled["enabled"] == 0
        assert disabled["status"] == "retired"
