"""settings_service — settings KV 服务出口契约测试 (P2 Task 12, 设计稿 §4.4)。

验收:
- 转发 SettingsRepository: get miss 默认值 / set-get 回读 / delete / list_all
- set 成功写 audit_log (默认 action=settings.set; 可定制 actor/action/detail)
- R3: backend/api/settings.py 不再 import settings_repo (api 层禁直连 repository)
- P3 namespace 契约 (设计稿 §5): 未注册前缀写入 fail-loud; state.* 例外清单
  与精确键 (secrets.oauth_allowlist) 放行; webhook.secret 已迁 vault 后经
  _DISALLOWED_EXACT 禁止明文回写 (Task 15)。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db
from backend.services.settings_service import SettingsService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_settings_service.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _audit_rows(action: str) -> list[dict]:
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT actor, action, target, detail FROM audit_log WHERE action = ?",
        (action,),
    ).fetchall()
    return [dict(r) for r in rows]


class TestSettingsServiceForwarding:
    """service 转发 repo — 契约与 SettingsRepository 语义一致。"""

    def test_get_miss_returns_default(self, temp_db):
        svc = SettingsService()
        assert svc.get("nope.key") is None
        assert svc.get("nope.key", []) == []

    def test_set_then_get_roundtrip(self, temp_db):
        svc = SettingsService()
        svc.set("collection.refresh_interval_seconds", 300)
        assert svc.get("collection.refresh_interval_seconds") == 300

    def test_delete_returns_true_then_false(self, temp_db):
        svc = SettingsService()
        svc.set("llm.default_provider", "deepseek")
        assert svc.delete("llm.default_provider") is True
        assert svc.delete("llm.default_provider") is False
        assert svc.get("llm.default_provider") is None

    def test_list_all_roundtrip(self, temp_db):
        svc = SettingsService()
        svc.set("interest.practice_domains", ["sec"])
        assert svc.list_all()["interest.practice_domains"] == ["sec"]


class TestSettingsServiceAudit:
    """写入即审计 — 默认 action=settings.set, 调用方可定制语义。"""

    def test_set_writes_default_audit(self, temp_db):
        SettingsService().set("quality.threshold", 0.8)
        rows = _audit_rows("settings.set")
        assert len(rows) == 1
        assert rows[0]["actor"] == "web"
        assert rows[0]["target"] == "quality.threshold"
        detail = json.loads(rows[0]["detail"])
        assert detail == {"from": None, "to": 0.8}

    def test_set_custom_actor_action_detail(self, temp_db):
        svc = SettingsService()
        old = svc.get("llm.default_provider")
        svc.set(
            "llm.default_provider",
            "deepseek",
            actor="web",
            action="llm_config.update",
            detail={"from": old, "to": "deepseek", "source": "user_switch"},
        )
        rows = _audit_rows("llm_config.update")
        assert len(rows) == 1
        assert rows[0]["actor"] == "web"
        assert rows[0]["target"] == "llm.default_provider"
        detail = json.loads(rows[0]["detail"])
        assert detail == {"from": None, "to": "deepseek", "source": "user_switch"}

    def test_failed_set_writes_no_audit(self, temp_db, monkeypatch):
        """repo.set 失败 (异常传播) 时不应留下审计行。"""
        from backend.repository import settings_repo

        def boom(self, key, value):
            raise RuntimeError("db down")

        monkeypatch.setattr(settings_repo.SettingsRepository, "set", boom)
        with pytest.raises(RuntimeError):
            SettingsService().set("quality.threshold", 0.9)
        assert _audit_rows("settings.set") == []


class TestR3NoDirectRepoInApi:
    """设计稿 §4.4: api/settings.py 必须经 settings_service, 不直连 repo。"""

    def test_api_settings_does_not_import_repo(self):
        import backend.api.settings as settings_mod

        source = Path(settings_mod.__file__).read_text(encoding="utf-8")
        assert "settings_repo" not in source
        assert "SettingsRepository" not in source
        assert "settings_service" in source


class TestNamespacePrefixContract:
    """P3 Task 14 (设计稿 §5): 写入必须落在注册前缀内, 未注册 fail-loud。

    - 未注册前缀 (webhook.subject) → InvalidParamException (Task 12 放行锚点已翻转)
    - state.* 例外清单 (mitre 位点/dsh 模式等既有运行状态 key) → 放行
    - 精确键 secrets.oauth_allowlist → 放行 (OAuth 白名单既有存储位)
    - webhook.secret → 已迁 vault (Task 15), 经 _DISALLOWED_EXACT 禁止明文回写
    """

    def test_unregistered_prefix_raises(self, temp_db):
        from backend.exceptions import InvalidParamException

        svc = SettingsService()
        with pytest.raises(InvalidParamException, match=r"webhook\.subject"):
            svc.set("webhook.subject", "build")
        assert svc.get("webhook.subject") is None

    def test_unregistered_prefix_writes_no_audit(self, temp_db):
        """契约拒绝发生在 repo.set 之前 — 不应留下任何审计行。"""
        from backend.exceptions import InvalidParamException

        with pytest.raises(InvalidParamException):
            SettingsService().set("random.unknown_key", 1)
        assert _audit_rows("settings.set") == []

    def test_state_exception_prefix_allowed(self, temp_db):
        svc = SettingsService()
        svc.set("state.mitre.synced_at", "2026-09-23T00:00:00Z")
        assert svc.get("state.mitre.synced_at") == "2026-09-23T00:00:00Z"

    def test_oauth_allowlist_exact_key_allowed(self, temp_db):
        svc = SettingsService()
        svc.set("secrets.oauth_allowlist", "a@x.com,b@x.com")
        assert svc.get("secrets.oauth_allowlist") == "a@x.com,b@x.com"

    def test_registered_config_prefixes_allowed(self, temp_db):
        """4 个用户偏好/配置 namespace (Task 16 sync 白名单同源) 正常写入。"""
        svc = SettingsService()
        svc.set("collection.refresh_interval_seconds", 300)
        svc.set("llm.default_provider", "deepseek")
        svc.set("interest.practice_domains", ["sec"])
        svc.set("quality.threshold", 0.8)

    def test_webhook_secret_exact_key_disallowed(self, temp_db):
        """P3 两步走收口: webhook.secret 已迁 llm_secrets 加密存储 (Task 15),
        settings 明文回写通道永久关闭。

        webhook. 前缀本就未注册 (会被 startswith 检查拒绝), _DISALLOWED_EXACT
        为防御性双保险 — 防未来有人把 webhook. 登记进前缀后明文键复活。
        """
        from backend.exceptions import InvalidParamException

        svc = SettingsService()
        with pytest.raises(InvalidParamException, match=r"webhook\.secret"):
            svc.set("webhook.secret", "should-not-persist")
        assert svc.get("webhook.secret") is None
