"""trigger webhook.secret — vault 加密存储读点测试 (P3 Task 15, 设计稿 §5)。

背景: webhook.py 原默认路径 import 不存在的 ``settings_kv`` 模块, 异常被吞 →
签名校验生产默认从未生效。修复 = secret 迁 llm_secrets 加密存储, 经
``SecretsService.find_internal_by_name`` (unlock 窗口语义) 读取。

验收:
- find_internal_by_name: unlock 态取明文 / 未解锁返回 None / 不存在返回 None
- WebhookTrigger._get_secret 默认路径采用 vault 读点; 失败路径 (异常/None)
  落 warning 且返回 None, 不抛异常中断 trigger 执行
- 注入 secret_provider (callable/dict) 路径不回归
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.services.secrets_service import SecretsService

MASTER_KEY = "test-master-key-12345678"
SECRET_NAME = "webhook.secret"
SECRET_VALUE = "whsec-vault-plaintext"


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_trigger_webhook_secret.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def vault_secret(temp_db) -> SecretsService:
    """主密钥已 setup + webhook.secret 已入 vault; teardown 清 unlock 态。"""
    from backend.services import secrets_service

    secrets_service._unlock_state.clear()
    svc = SecretsService()
    svc.setup_master_key(MASTER_KEY)
    svc.create_secret(
        name=SECRET_NAME,
        model="hmac",
        base_url="internal://webhook",  # repo 层要求非空; webhook.secret 无 base_url 语义, 占位标记
        api_key=SECRET_VALUE,
        master_key=MASTER_KEY,
    )
    yield svc
    secrets_service._unlock_state.clear()


class TestFindInternalByName:
    """find_internal_by_name — 按 name 取明文 (unlock 窗口语义)。"""

    def test_unlocked_returns_plaintext(self, vault_secret):
        vault_secret.unlock(MASTER_KEY)
        assert vault_secret.find_internal_by_name(SECRET_NAME) == SECRET_VALUE

    def test_locked_returns_none(self, vault_secret):
        """未解锁返回 None (不抛) — webhook 侧走 fail-open 兜底。"""
        assert vault_secret.find_internal_by_name(SECRET_NAME) is None

    def test_missing_name_returns_none(self, vault_secret):
        vault_secret.unlock(MASTER_KEY)
        assert vault_secret.find_internal_by_name("nope.key") is None


class TestWebhookDefaultPath:
    """WebhookTrigger._get_secret 默认路径 (secret_provider=None) 走 vault。"""

    def test_uses_find_internal_by_name(self, monkeypatch):
        from backend.services.trigger_gate.triggers.webhook import WebhookTrigger

        monkeypatch.setattr(
            SecretsService, "find_internal_by_name", lambda self, name: SECRET_VALUE
        )
        assert WebhookTrigger()._get_secret() == SECRET_VALUE

    def test_secret_missing_returns_none(self, monkeypatch):
        """vault 未配置/未解锁 → None (fail-open), 不得抛。"""
        from backend.services.trigger_gate.triggers.webhook import WebhookTrigger

        monkeypatch.setattr(
            SecretsService, "find_internal_by_name", lambda self, name: None
        )
        assert WebhookTrigger()._get_secret() is None

    def test_lookup_exception_returns_none(self, monkeypatch):
        """vault 读点异常 (DB down 等) → warning + None, 不中断 trigger。"""
        from backend.services.trigger_gate.triggers.webhook import WebhookTrigger

        def boom(self, name):
            raise RuntimeError("db down")

        monkeypatch.setattr(SecretsService, "find_internal_by_name", boom)
        assert WebhookTrigger()._get_secret() is None

    def test_end_to_end_unlocked_vault_signs_request(self, vault_secret):
        """端到端: unlock 后默认 trigger 从 vault 取 secret 并强制签名 (fail-closed)。"""
        from backend.services.trigger_gate.triggers.webhook import (
            SignatureInvalidError,
            WebhookTrigger,
        )

        vault_secret.unlock(MASTER_KEY)
        trigger = WebhookTrigger()
        with pytest.raises(SignatureInvalidError):
            trigger.submit("/api/trigger/webhook/secnews", {"event": "push"})


class TestInjectedProviderUnchanged:
    """注入 secret_provider 路径不回归 (test_trigger_sources.py 已覆盖签名语义)。"""

    def test_callable_provider(self):
        from backend.services.trigger_gate.triggers.webhook import WebhookTrigger

        assert WebhookTrigger(secret_provider=lambda: "s1")._get_secret() == "s1"

    def test_dict_provider(self):
        from backend.services.trigger_gate.triggers.webhook import WebhookTrigger

        assert WebhookTrigger(secret_provider={SECRET_NAME: "s2"})._get_secret() == "s2"
