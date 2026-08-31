"""SecretRepository.get_by_provider helper 测试 (Batch ⑥ C1)。

契约: ``074_v0.6_llm_secrets_provider.sql`` ``idx_llm_secrets_provider``
+ AIService 接入约定 — ai_hub 能按 provider 名查表拿到明文, 该 helper
是契约兑现点。

用例 (5):
1. 匹配 — provider 命中, 返回 secret
2. 空 — provider 不在表里, 返回 None
3. 多条取最新 — 同一 provider 录入两次, updated_at 较新者胜出
4. provider 空串/空格 — 返回 None (调用方责任前置)
5. ORDER BY 验证 — 已删除再重建, id 增但 updated_at 更新, 命中新行
"""
from __future__ import annotations

import time

from backend.crypto import derive_fernet_key
from backend.repository.secrets_repo import SecretRepository

MASTER_KEY = "test-master-key-strong-1234"
SALT = b"\x00" * 16


def _fernet() -> bytes:
    return derive_fernet_key(MASTER_KEY, SALT, iterations=600_000)


def _setup_master(temp_db):
    """播种 encryption_keys 表 + 拿到 key_id。"""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    row = EncryptionKeyRepository().setup_default(master_key=MASTER_KEY)
    return int(row.id)


def test_get_by_provider_match(temp_db):
    """1. 命中: 单条同 provider 录入, get_by_provider 返回之。"""
    kid = _setup_master(temp_db)
    repo = SecretRepository()
    repo.create(
        name="DeepSeek-1",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test-1234",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="sensenova",
    )
    item = repo.get_by_provider("sensenova")
    assert item is not None
    assert item.provider == "sensenova"
    assert item.name == "DeepSeek-1"


def test_get_by_provider_empty(temp_db):
    """2. 未命中: 表空, 返 None。"""
    assert SecretRepository().get_by_provider("anything") is None


def test_get_by_provider_latest_updated(temp_db):
    """3. 多条同 provider, updated_at 最新者胜出。"""
    kid = _setup_master(temp_db)
    repo = SecretRepository()
    repo.create(
        name="old",
        model="m1",
        base_url="https://x.com",
        api_key="sk-old-1234",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="ollama",
    )
    # 强制 updated_at 拉开 (毫秒级 sleep 让 updated_at 不撞车)
    time.sleep(0.01)
    repo.create(
        name="new",
        model="m2",
        base_url="https://y.com",
        api_key="sk-new-5678",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="ollama",
    )
    item = repo.get_by_provider("ollama")
    assert item is not None
    assert item.name == "new"
    assert item.api_key_encrypted != repo.get(item.id - 1).api_key_encrypted


def test_get_by_provider_blank_returns_none(temp_db):
    """4. provider 空串/纯空格 → None (前置责任)。"""
    kid = _setup_master(temp_db)
    repo = SecretRepository()
    repo.create(
        name="x",
        model="m",
        base_url="https://x.com",
        api_key="sk-1234",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="openai",
    )
    assert repo.get_by_provider("") is None
    assert repo.get_by_provider("   ") is None


def test_get_by_provider_order_by_id_after_delete(temp_db):
    """5. ORDER BY updated_at DESC, id DESC — 删除旧条后新建, id 增
    但 updated_at 更新, 命中新行。"""
    kid = _setup_master(temp_db)
    repo = SecretRepository()
    old = repo.create(
        name="first",
        model="m",
        base_url="https://x.com",
        api_key="sk-first-1",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="anthropic",
    )
    time.sleep(0.01)
    # 直接 delete, 再 create 同 provider
    repo.delete(old.id)
    new = repo.create(
        name="second",
        model="m",
        base_url="https://x.com",
        api_key="sk-second-2",
        fernet_key=_fernet(),
        encryption_key_id=kid,
        provider="anthropic",
    )
    assert new.id > old.id
    item = repo.get_by_provider("anthropic")
    assert item is not None
    assert item.id == new.id
    assert item.name == "second"