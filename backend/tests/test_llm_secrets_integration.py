"""AIService llm_secrets 接入测试 (Batch ⑥ C2 + C3 共用)。

覆盖 ``AIService._resolve_api_key`` / ``_key_source`` 四级链:
- env > secrets(provider=...) > "" (fail-soft)
- key_source 三态 (env / secrets / none)
- ``llm_usage_log.key_source`` 落库正确
- LLMService gateway 同步走 AIService 单点

测试隔离: temp_db (conftest) + autouse mock ``_check_keyring`` 返 False
(CI runner 无 D-Bus, fail-soft 路径必走)。
"""
from __future__ import annotations

import time

import pytest

MASTER_KEY = "test-master-key-strong-1234"


@pytest.fixture(autouse=True)
def _disable_keyring(monkeypatch):
    """CI runner 无 D-Bus, 强制 _check_keyring 返 False。
    走 secrets_service._persist_master_key → settings 表加密存储 路径,
    不依赖 OS keyring, 与生产 macOS 行为等价 (master_key 持久化到 settings)。
    """
    from backend.services import secrets_service
    monkeypatch.setattr(secrets_service, "_check_keyring", lambda: False)


def _setup_master_and_unlock() -> int:
    """建立 master_key + unlock + 返 encryption_key_id。"""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.services import secrets_service
    row = EncryptionKeyRepository().setup_default(master_key=MASTER_KEY)
    secrets_service._unlock_state[row.id] = {
        "fernet_key": secrets_service.derive_fernet_key(
            MASTER_KEY, row.salt, row.iterations,
        ),
        "expires_at": time.time() + 600,
    }
    return int(row.id)


def _make_secret(provider: str, *, name: str = "test", api_key: str = "sk-from-db"):
    """录入一条 secret 并返 id。"""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository
    kid = _setup_master_and_unlock()
    row = EncryptionKeyRepository().get_by_id(kid)
    from backend.crypto import derive_fernet_key
    fk = derive_fernet_key(MASTER_KEY, row.salt, row.iterations)
    item = SecretRepository().create(
        name=name, model="m", base_url="https://x.com",
        api_key=api_key, fernet_key=fk, encryption_key_id=kid,
        provider=provider,
    )
    return int(item.id), kid


def _clear_env(monkeypatch):
    for k in ("SENSENOVA_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY",
              "ANTHROPIC_API_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


# ----------------------------------------------------------------------------
# _resolve_api_key 四级链
# ----------------------------------------------------------------------------

def test_env_beats_secrets(monkeypatch, temp_db):
    """1. env 命中 → 返 env, 不读 secrets。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    monkeypatch.setenv("SENSENOVA_API_KEY", "env-wins")
    _make_secret("sensenova", api_key="db-loses")
    assert AIService()._resolve_api_key() == "env-wins"


def test_env_unset_secrets_unlocked(monkeypatch, temp_db):
    """2. env 未设 + secrets 配 + unlock → 返 secrets 明文。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    _make_secret("sensenova", api_key="from-db-key")
    assert AIService()._resolve_api_key() == "from-db-key"


def test_env_unset_secrets_locked(monkeypatch, temp_db):
    """3. env 未设 + secrets 配 + 未 unlock → "" (fail-soft)。"""
    from backend.crypto import derive_fernet_key
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository
    from backend.services import secrets_service
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    row = EncryptionKeyRepository().setup_default(master_key=MASTER_KEY)
    secrets_service._unlock_state.clear()  # 不 unlock
    fk = derive_fernet_key(MASTER_KEY, row.salt, row.iterations)
    SecretRepository().create(
        name="locked", model="m", base_url="https://x.com",
        api_key="db-key", fernet_key=fk, encryption_key_id=int(row.id),
        provider="sensenova",
    )
    assert AIService()._resolve_api_key() == ""


def test_env_unset_secrets_table_empty(monkeypatch, temp_db):
    """4. env 未设 + secrets 表空 → ""。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    assert AIService()._resolve_api_key() == ""


# ----------------------------------------------------------------------------
# _key_source 三态
# ----------------------------------------------------------------------------

def test_key_source_env(monkeypatch, temp_db):
    """5. env 命中 → "env"。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    monkeypatch.setenv("SENSENOVA_API_KEY", "anything")
    _make_secret("sensenova")  # 即使有 secrets, env 胜出
    assert AIService()._key_source() == "env"


def test_key_source_secrets(monkeypatch, temp_db):
    """6. env 未设 + secrets + unlock → "secrets"。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    _make_secret("sensenova")
    assert AIService()._key_source() == "secrets"


def test_key_source_none(monkeypatch, temp_db):
    """7. env 未设 + 无 secrets → "none"。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    assert AIService()._key_source() == "none"


# ----------------------------------------------------------------------------
# 多条同 provider 取 updated_at 最新
# ----------------------------------------------------------------------------

def test_multi_provider_takes_latest_updated(monkeypatch, temp_db):
    """8. 同 provider 录入两次, _resolve_api_key 拿明文 = 最新条。"""
    from backend.crypto import derive_fernet_key
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository
    from backend.services import secrets_service
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    # 强制 _resolve_provider 返 ollama, 让 _resolve_api_key 查 ollama 槽
    monkeypatch.setattr(AIService, "_resolve_provider", staticmethod(lambda: "ollama"))
    repo = EncryptionKeyRepository()
    if repo.is_setup():
        row = repo.get_default()
    else:
        row = repo.setup_default(master_key=MASTER_KEY)
    fk = derive_fernet_key(MASTER_KEY, row.salt, row.iterations)
    secrets_service._unlock_state.clear()
    secrets_service._unlock_state[row.id] = {
        "fernet_key": fk,
        "expires_at": time.time() + 600,
    }
    SecretRepository().create(
        name="first", model="m", base_url="https://x.com",
        api_key="sk-old-key-1234", fernet_key=fk, encryption_key_id=int(row.id),
        provider="ollama",
    )
    time.sleep(0.01)
    SecretRepository().create(
        name="second", model="m", base_url="https://y.com",
        api_key="sk-new-key-5678", fernet_key=fk, encryption_key_id=int(row.id),
        provider="ollama",
    )
    assert AIService()._resolve_api_key() == "sk-new-key-5678"


# ----------------------------------------------------------------------------
# 端到端: evaluate() 落 llm_usage_log.key_source
# ----------------------------------------------------------------------------

def test_evaluate_writes_key_source_secrets(monkeypatch, temp_db):
    """9. evaluate 走 secrets → llm_usage_log.key_source = "secrets"。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    _make_secret("sensenova")
    monkeypatch.setattr(
        "backend.services.ai_hub.service.AIService._call_sensenova_eval",
        lambda self, title, content, key, timeout: {
            "quality_score": 8, "verdict": "ok",
            "key_points": ["k1"], "summary": "s", "provider": "sensenova",
        },
    )
    AIService().evaluate("body", title="t")
    # 查 llm_usage_log 最近一条
    from backend.repository.db import get_connection
    row = get_connection().execute(
        "SELECT key_source FROM llm_usage_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["key_source"] == "secrets"


def test_evaluate_no_key_key_source_none(monkeypatch, temp_db):
    """10. 无 key + evaluate 失败 → key_source="none" (fail-soft)。"""
    from backend.services.ai_hub.service import AIService
    _clear_env(monkeypatch)
    # secrets 表空, env 空 → key="" → sensenova HTTP 调用失败 → 走 except 分支
    monkeypatch.setattr(
        "backend.services.ai_hub.service.AIService._call_sensenova_eval",
        lambda self, title, content, key, timeout: (_ for _ in ()).throw(
            RuntimeError("no key")
        ),
    )
    res = AIService().evaluate("body", title="t")
    assert res["ok"] is False
    from backend.repository.db import get_connection
    row = get_connection().execute(
        "SELECT key_source FROM llm_usage_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["key_source"] == "none"