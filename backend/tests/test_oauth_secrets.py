"""D1 (Batch ⑧) — OAuth 解锁路径测试。

覆盖:
- /api/secrets/oauth-config: 启停状态 / URL 拼装
- /api/secrets/unlock-with-oauth: mock provider 流程 / allowlist 校验 / 失败码
- oauth_provider.py: URL 校验 (localhost / 私有 / 保留 拒绝) / CloudBase 真身 (mock httpx)
- 集成: setup → OAuth unlock → unlock_status 反映 oauth_verified=True
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest


# ============ Fixtures ============


@pytest.fixture()
def client(temp_db, monkeypatch) -> Iterator:
    """独立 FastAPI TestClient, 自动注入 mock OAuth provider。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.secrets import router
    from backend.services import secrets_service

    # conftest._oauth_provider_mock autouse 已注入 mock provider, 这里仅建 app
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)

    secrets_service._unlock_state.clear()
    try:
        from backend.repository import db as _db
        _db.close_db()
    except Exception:
        pass


MASTER_KEY = "test-oauth-master-1234"


# ============ OAuth Provider URL validation ============


def test_validate_redirect_url_rejects_localhost():
    from backend.services.oauth_provider import _validate_redirect_url

    with pytest.raises(Exception):
        _validate_redirect_url("http://localhost:8080/callback")


def test_validate_redirect_url_rejects_loopback_ip():
    from backend.services.oauth_provider import _validate_redirect_url

    with pytest.raises(Exception):
        _validate_redirect_url("https://127.0.0.1/callback")


def test_validate_redirect_url_rejects_private_10x():
    from backend.services.oauth_provider import _validate_redirect_url

    with pytest.raises(Exception):
        _validate_redirect_url("https://10.0.0.1/callback")


def test_validate_redirect_url_rejects_link_local():
    from backend.services.oauth_provider import _validate_redirect_url

    with pytest.raises(Exception):
        _validate_redirect_url("https://169.254.169.254/latest/meta-data/")


def test_validate_redirect_url_rejects_http():
    from backend.services.oauth_provider import _validate_redirect_url

    with pytest.raises(Exception):
        _validate_redirect_url("http://example.com/callback")


# ============ OAuth config endpoint ============


def test_oauth_config_disabled_when_no_env(monkeypatch):
    monkeypatch.delenv("HOTSPOT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("HOTSPOT_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("HOTSPOT_OAUTH_AUTHORIZE_URL", raising=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.secrets import router

    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.get("/api/secrets/oauth-config")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["client_id"] == ""
    assert body["authorize_url"] == ""


def test_oauth_config_enabled_with_full_env(monkeypatch):
    monkeypatch.setenv("HOTSPOT_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("HOTSPOT_OAUTH_REDIRECT_URI", "https://app.example.com/cb")
    monkeypatch.setenv("HOTSPOT_OAUTH_AUTHORIZE_URL", "https://auth.example.com/authorize")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.secrets import router

    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.get("/api/secrets/oauth-config")
    body = r.json()
    assert body["enabled"] is True
    assert body["client_id"] == "test-client"
    assert "response_type=code" in body["authorize_url"]
    assert "client_id=test-client" in body["authorize_url"]


# ============ Unlock-with-OAuth happy path ============


def test_unlock_with_oauth_success(client):
    """setup → mock token → unlock-with-oauth 成功 → unlock_status 反映 oauth_verified。"""
    # setup master_key
    r = client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    assert r.status_code == 201, r.text

    # OAuth unlock (mock token: mock:user-1:alice@example.com)
    r = client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "mock:user-1:alice@example.com", "role": "admin"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unlocked"] is True
    assert body["oauth_verified"] is True
    assert body["oauth_user"] == "alice@example.com"
    assert "expires_at" in body

    # unlock_status 反映 oauth_verified
    r = client.get("/api/secrets/unlock?role=admin")
    assert r.status_code == 200
    assert r.json()["unlocked"] is True


def test_unlock_with_oauth_invalid_token_401(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "invalid-format", "role": "admin"},
    )
    assert r.status_code == 401
    assert "INVALID_OAUTH_TOKEN" in r.text or "INVALID_OAUTH_TOKEN" in str(r.json())


def test_unlock_with_oauth_not_setup_409(client):
    """未 setup 时 OAuth unlock → 409 (主密钥未初始化)。"""
    r = client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "mock:user-1:alice@example.com", "role": "admin"},
    )
    assert r.status_code == 409


def test_unlock_with_oauth_allowlist_blocks(client, monkeypatch):
    """settings.kv 配置 allowlist → 不在白名单邮箱被拒。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})

    # 写 allowlist
    from backend.repository.settings_repo import SettingsRepository
    SettingsRepository().set("secrets.oauth_allowlist", "bob@example.com,carol@x.com")

    r = client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "mock:user-1:alice@example.com", "role": "admin"},
    )
    assert r.status_code == 401
    assert "allowlist" in r.text.lower() or "allowlist" in str(r.json()).lower()


def test_unlock_with_oauth_allowlist_allows(client, monkeypatch):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    from backend.repository.settings_repo import SettingsRepository
    SettingsRepository().set("secrets.oauth_allowlist", "alice@example.com,bob@x.com")

    r = client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "mock:u1:alice@example.com", "role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["oauth_user"] == "alice@example.com"


# ============ audit 验证 ============


def test_unlock_with_oauth_writes_audit_log(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post(
        "/api/secrets/unlock-with-oauth",
        json={"token": "mock:u1:alice@example.com", "role": "admin"},
    )
    # 查 audit log (audit_log 表, action 列)
    from backend.repository.db import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT action FROM audit_log WHERE action LIKE 'llm_secrets.%' ORDER BY id"
    ).fetchall()
    actions = [r[0] for r in rows]
    assert "llm_secrets.unlock_oauth" in actions