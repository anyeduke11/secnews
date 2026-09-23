"""settings_service — settings KV 服务出口契约测试 (P2 Task 12, 设计稿 §4.4)。

验收:
- 转发 SettingsRepository: get miss 默认值 / set-get 回读 / delete / list_all
- set 成功写 audit_log (默认 action=settings.set; 可定制 actor/action/detail)
- R3: backend/api/settings.py 不再 import settings_repo (api 层禁直连 repository)
- P3 前行为锚点: 未注册前缀 (webhook.subject) 当前放行 —
  Task 14 prefix 契约 (_ALLOWED_PREFIXES) 落地后本用例应翻转为 raises。
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


class TestPreP3PrefixAnchor:
    """P3 前放行锚点 — Task 14 加 _ALLOWED_PREFIXES 后翻转为 pytest.raises。"""

    def test_unregistered_prefix_allowed_before_p3(self, temp_db):
        svc = SettingsService()
        svc.set("webhook.subject", "build")
        assert svc.get("webhook.subject") == "build"
