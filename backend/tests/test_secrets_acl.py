"""v0.7 Batch ⑨ B9-3: per-secret owner_role ACL tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def _seed_secrets(temp_db):
    """建 encryption_key + 2 个不同 owner_role 的 secret (SQL 直插, 绕过 master_key 解密路径)."""
    from datetime import datetime, timezone

    from backend.repository.db import get_connection
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository

    ek = EncryptionKeyRepository()
    ek.setup_default(master_key="test-master-key-12345678", role="admin")
    key_id = ek.get_default().id

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    for name, owner in [("admin-only", "admin"), ("user-shared", "user")]:
        conn.execute(
            """
            INSERT INTO llm_secrets (
                name, model, base_url, provider, api_key_encrypted,
                encryption_key_id, created_at, updated_at, owner_role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                "gpt-4o" if owner == "admin" else "llama3",
                "https://api.openai.com/v1" if owner == "admin" else "http://localhost:11434",
                "openai" if owner == "admin" else "ollama",
                b"dummy-cipher",
                key_id,
                now,
                now,
                owner,
            ),
        )


def test_list_filters_by_actor_role(temp_db, _seed_secrets):
    """user 角色只能看到 owner_role='user' 的 secret."""
    from backend.repository.secrets_repo import SecretRepository

    sr = SecretRepository()
    # admin 看全部
    items, total = sr.list(actor_role="admin")
    assert total == 2
    assert {it.name for it in items} == {"admin-only", "user-shared"}

    # user 只看 user-owned
    items, total = sr.list(actor_role="user")
    assert total == 1
    assert items[0].name == "user-shared"
    assert items[0].owner_role == "user"


def test_get_cross_role_returns_none(temp_db, _seed_secrets):
    """user 取 admin-owned secret → 返 None (404 语义, 不暴露存在性)."""
    from backend.repository.secrets_repo import SecretRepository

    sr = SecretRepository()
    all_items, _ = sr.list(actor_role="admin")
    admin_secret = next(it for it in all_items if it.name == "admin-only")

    # user 查不到
    assert sr.get(admin_secret.id, actor_role="user") is None
    # admin 查得到
    assert sr.get(admin_secret.id, actor_role="admin") is not None


def test_to_dict_includes_owner_role(temp_db, _seed_secrets):
    from backend.repository.secrets_repo import SecretRepository

    sr = SecretRepository()
    items, _ = sr.list(actor_role="admin")
    d = items[0].to_dict()
    assert "owner_role" in d
    assert d["owner_role"] in ("admin", "user")


def test_unknown_role_cannot_access_anything(temp_db, _seed_secrets):
    """未知 role (e.g. 'guest') → 0 results, 不抛."""
    from backend.repository.secrets_repo import SecretRepository

    sr = SecretRepository()
    items, total = sr.list(actor_role="guest")
    assert total == 0
    assert items == []
