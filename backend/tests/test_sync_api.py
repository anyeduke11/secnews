"""Phase 42 Sync API 测试 (end-to-end, in-memory DB)。

覆盖:
- status: 未配置时返回 configured=False
- config upsert/delete (master_key 验证 + webdav_password 加密)
- test connection (mock WebDAVClient)
- auto: 切换 auto_sync_enabled
- bundle preview
- history
- push/pull/bidirectional: WebDAV mock
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator:
    db_file = tmp_path / "test_sync_api.db"
    setup_conn = sqlite3.connect(str(db_file))
    setup_conn.execute("PRAGMA journal_mode=WAL")
    setup_conn.execute("PRAGMA foreign_keys=ON")
    setup_conn.execute("PRAGMA busy_timeout=30000")

    from backend.repository import db as db_mod

    db_mod.apply_migrations(setup_conn)
    setup_conn.close()

    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    shared_conn = sqlite3.connect(str(db_file), check_same_thread=False, timeout=30.0)
    shared_conn.row_factory = sqlite3.Row
    shared_conn.execute("PRAGMA journal_mode=WAL")
    shared_conn.execute("PRAGMA foreign_keys=ON")
    shared_conn.execute("PRAGMA busy_timeout=30000")

    def _get_conn():
        return shared_conn

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.sync import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    shared_conn.close()


MASTER_KEY = "test-master-key-strong-1234"


def _setup_master_key(client):
    """通过 /api/secrets/setup 设主密钥 (复用 secrets 测试的 pattern)。"""
    # 直接走 DB 即可, 不用经过 secrets API
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    repo = EncryptionKeyRepository()
    if not repo.is_setup():
        repo.setup_default(master_key=MASTER_KEY)


def test_status_not_configured(client):
    r = client.get("/api/sync/status")
    assert r.status_code == 200
    assert r.json()["status"]["configured"] is False


def test_config_requires_setup(client):
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "app-pwd",
        "master_key": MASTER_KEY,
    })
    assert r.status_code == 409  # 主密钥未初始化


def test_config_wrong_master_key(client):
    _setup_master_key(client)
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "app-pwd",
        "master_key": "wrong-master-key-1234",
    })
    assert r.status_code == 401


def test_config_upsert_success(client):
    _setup_master_key(client)
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
        "auto_sync_enabled": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["config"]["webdav_url"] == "https://dav.jianguoyun.com/dav"
    assert data["config"]["auto_sync_enabled"] is True
    assert data["config"]["has_password"] is True
    assert "device_id" in data["config"]


def test_config_upsert_first_time_without_password_409(client):
    """首次配置不提供 webdav_password → 409 拒绝 (必须提供)。"""
    _setup_master_key(client)
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        # webdav_password 故意省略
        "master_key": MASTER_KEY,
    })
    assert r.status_code == 409, r.text
    assert "首次配置必须提供" in r.json()["detail"]["message"]


def test_config_upsert_existing_without_password_preserves(client):
    """已配置 + 不传 webdav_password → 保留原密文, 其他字段可更新。"""
    _setup_master_key(client)
    # 首次配置 (有密码)
    r1 = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "old-password",
        "master_key": MASTER_KEY,
    })
    assert r1.status_code == 200
    # 抓取已存密文用于对比
    from backend.repository.sync_configs_repo import SyncConfigRepository
    old = SyncConfigRepository().get_default()
    assert old is not None and old.webdav_password_encrypted is not None
    old_cipher = old.webdav_password_encrypted
    old_salt = old.webdav_password_salt

    # 第二次配置: 改 url + 不传 password → 保留原密文
    r2 = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav-renamed",
        "webdav_username": "new@x.com",
        "master_key": MASTER_KEY,
        "auto_sync_enabled": True,
    })
    assert r2.status_code == 200, r2.text
    cfg = r2.json()["config"]
    assert cfg["webdav_url"] == "https://dav.jianguoyun.com/dav-renamed"
    assert cfg["webdav_username"] == "new@x.com"
    assert cfg["has_password"] is True
    # 密文字节未变 (没重新加密)
    new = SyncConfigRepository().get_default()
    assert new.webdav_password_encrypted == old_cipher
    assert new.webdav_password_salt == old_salt


def test_config_upsert_existing_with_new_password_replaces(client):
    """已配置 + 提供新 webdav_password → 重新加密 (密文会变)。"""
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "old-password",
        "master_key": MASTER_KEY,
    })
    from backend.repository.sync_configs_repo import SyncConfigRepository
    old_cipher = SyncConfigRepository().get_default().webdav_password_encrypted
    # 用新密码 + 正确 master_key 重新配置
    r2 = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "new-password-2",
        "master_key": MASTER_KEY,
    })
    assert r2.status_code == 200, r2.text
    new_cipher = SyncConfigRepository().get_default().webdav_password_encrypted
    # 密文字节一定不同 (重新生成 salt + 重新加密)
    assert new_cipher != old_cipher


def test_config_upsert_existing_wrong_master_key_401(client):
    """已配置 + 改其他字段时主密钥错 → 401 (master_key 始终必填验证)。"""
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "p",
        "master_key": MASTER_KEY,
    })
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "master_key": "wrong-password-12345678",
    })
    assert r.status_code == 401


def test_config_delete(client):
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
    })
    r = client.delete("/api/sync/config")
    assert r.status_code == 200
    r2 = client.get("/api/sync/status")
    assert r2.json()["status"]["configured"] is False


def test_config_delete_404_when_no_config(client):
    r = client.delete("/api/sync/config")
    assert r.status_code == 404


def test_test_connection(client):
    with patch("backend.api.sync.WebDAVClient") as MockClient:
        instance = MockClient.return_value
        instance.test_connection = AsyncMock(return_value=(True, "连接成功"))
        r = client.post("/api/sync/test", json={
            "webdav_url": "https://dav.jianguoyun.com/dav",
            "webdav_username": "u@x.com",
            "webdav_password": "my-app-password",
        })
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auto_toggle(client):
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
        "auto_sync_enabled": False,
    })
    r = client.post("/api/sync/auto", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["auto_sync_enabled"] is True
    r2 = client.get("/api/sync/status")
    assert r2.json()["status"]["auto_sync_enabled"] is True


def test_auto_toggle_without_config(client):
    r = client.post("/api/sync/auto", json={"enabled": True})
    assert r.status_code == 404


def test_bundle_preview(client):
    _setup_master_key(client)
    r = client.get("/api/sync/bundle/preview")
    assert r.status_code == 200
    data = r.json()["preview"]
    assert data["version"] == "1.0"
    assert "record_counts" in data
    for key in ("favorites", "todos", "skills", "custom_sources", "secrets"):
        assert key in data["record_counts"]


def test_history_empty(client):
    r = client.get("/api/sync/history")
    assert r.status_code == 200
    assert r.json()["history"] == []


def test_push_without_config(client):
    r = client.post("/api/sync/push", json={"master_key": MASTER_KEY})
    assert r.status_code == 409  # 未配置


def test_pull_without_config(client):
    r = client.post("/api/sync/pull", json={"master_key": MASTER_KEY})
    assert r.status_code == 409


def test_bidirectional_without_config(client):
    r = client.post("/api/sync/bidirectional", json={"master_key": MASTER_KEY})
    assert r.status_code == 409


def test_push_wrong_master_key(client):
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
    })
    # 错密码 → 解密 webdav password 失败 → 400
    r = client.post("/api/sync/push", json={"master_key": "wrong-master-key-1234"})
    assert r.status_code == 400


def test_push_success_mocked(client):
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
    })
    with patch("backend.services.sync_service.WebDAVClient") as MockClient:
        instance = MockClient.return_value
        instance.mkdir = AsyncMock(return_value=True)
        instance.upload = AsyncMock(return_value=201)
        r = client.post("/api/sync/push", json={"master_key": MASTER_KEY})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["direction"] == "push"
    assert data["status"] == "success"
    # history 应有 1 条
    h = client.get("/api/sync/history").json()["history"]
    assert len(h) == 1
    assert h[0]["direction"] == "push"
    assert h[0]["status"] == "success"


def test_push_locked_vault_with_secrets_rejected(client):
    """P1: secrets vault 锁定且存在 secrets 时, push 必须明确拒绝。

    锁定态 build_bundle 会把 secrets 密文置 None, apply 端跳过 → 静默丢失/
    覆盖对端 secrets。修复后 push 在 WebDAV 交互前即报错提示解锁。
    """
    _setup_master_key(client)
    client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
    })
    # 直接插入一条 secrets (vault 未解锁状态)
    from backend.repository.db import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT INTO llm_secrets (name, model, base_url, api_key_encrypted, "
        "encryption_key_id, created_at, updated_at) "
        "VALUES ('test-secret', 'gpt-4o-mini', 'https://api.openai.com', "
        "X'deadbeef', 1, '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00')"
    )
    # vault 未解锁 → push 应被拒绝 (无需 WebDAV mock, 检查在交互前)
    r = client.post("/api/sync/push", json={"master_key": MASTER_KEY})
    assert r.status_code in (400, 409), r.text
    assert "解锁" in r.json()["detail"]["message"]


def _seed_merged_state(client, items):
    """建默认配置 + 直接写入含 favorites 记录的 merged bundle, 返回 config_id。"""
    _setup_master_key(client)
    r = client.post("/api/sync/config", json={
        "webdav_url": "https://dav.jianguoyun.com/dav",
        "webdav_username": "u@x.com",
        "webdav_password": "my-app-password",
        "master_key": MASTER_KEY,
    })
    assert r.status_code == 200, r.text
    from backend.repository.sync_configs_repo import SyncConfigRepository
    from backend.repository.sync_states_repo import SyncStateRepository

    cfg = SyncConfigRepository().get_default()
    assert cfg is not None
    bundle = {"version": "1.7", "records": {"favorites": items}}
    SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))
    return cfg.id


def test_conflicts_resolve_marks_matching_key(client):
    """单条裁决: 只标记 record_key 匹配的 item (P2-2 表征测试)。"""
    cfg_id = _seed_merged_state(client, [
        {"hotspot_id": "f1", "title": "a"},
        {"hotspot_id": "f2", "title": "b"},
    ])
    r = client.post("/api/sync/conflicts/resolve", json={
        "record_type": "favorites", "record_key": "f2", "choice": "remote",
    })
    assert r.status_code == 200, r.text
    assert r.json()["resolved"] is True
    from backend.repository.sync_states_repo import SyncStateRepository

    state = SyncStateRepository().get(cfg_id)
    items = json.loads(state["bundle_json"])["records"]["favorites"]
    assert items[0].get("_conflict_resolved") is None
    assert items[1]["_conflict_resolved"] == "remote"


def test_conflicts_resolve_missing_key_404(client):
    """单条裁决: record_key 不存在 → 404, 不写回。"""
    _seed_merged_state(client, [{"hotspot_id": "f1", "title": "a"}])
    r = client.post("/api/sync/conflicts/resolve", json={
        "record_type": "favorites", "record_key": "nope", "choice": "local",
    })
    assert r.status_code == 404


def test_conflicts_auto_resolve_marks_all_items(client):
    """批量裁决 (简化版): 全表统一标记, count = 条数; pk 列不参与匹配。

    P2-2: auto-resolve 语义即"不逐条指定 record_key" — 死变量 pk_map 已删,
    本测试锁定删除前后行为一致。
    """
    cfg_id = _seed_merged_state(client, [
        {"hotspot_id": "f1", "title": "a"},
        {"hotspot_id": "f2", "title": "b"},
        {"hotspot_id": "f3", "title": "c"},
    ])
    r = client.post("/api/sync/conflicts/auto-resolve", json={
        "record_type": "favorites", "choice": "local",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved"] is True and body["count"] == 3
    from backend.repository.sync_states_repo import SyncStateRepository

    state = SyncStateRepository().get(cfg_id)
    items = json.loads(state["bundle_json"])["records"]["favorites"]
    assert all(i["_conflict_resolved"] == "local" for i in items)


def test_conflicts_auto_resolve_unknown_table_404(client):
    """批量裁决: 表不存在 → 404。"""
    _seed_merged_state(client, [{"hotspot_id": "f1"}])
    r = client.post("/api/sync/conflicts/auto-resolve", json={
        "record_type": "nonexistent_table", "choice": "local",
    })
    assert r.status_code == 404
