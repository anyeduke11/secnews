"""POST /api/settings/llm-provider 端点测试 (v0.7 Batch 2)。

覆盖:
- 合法 provider 切换 → 200 + settings.kv 写入 + audit_log 一行
- 非法 provider → 400 InvalidParamException, 无 settings 写入, 无 audit
- audit_log 写入失败 (mock get_connection 抛) → 仍 200, settings.kv 已落 (审计容错)
- actor=web / system / agent:test 三种格式均落 audit_log
- 旧值记录正确 (from=None → 替换为新值)
- 校验 yaml registry 路径在 config 缺失时退化到 sensenova/ollama 兜底
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.settings import router as settings_router
from backend.exceptions import register_exception_handlers
from backend.repository.db import get_connection
from backend.repository.settings_repo import SettingsRepository
from backend.version import APP_VERSION


@pytest.fixture
def client(temp_db):
    """最小 FastAPI app + settings router (不挂 lifespan / scheduler)。

    conftest 的 temp_db 已隔离 SQLite 文件 + 重置 connection 缓存, 这里只
    需要构造一个能路由 /api/settings/* 的 app。
    """
    app = FastAPI(title="test", version=APP_VERSION)
    register_exception_handlers(app)
    app.include_router(settings_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _audit_count() -> int:
    return get_connection().execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action='llm_config.update'"
    ).fetchone()["n"]


def test_valid_provider_switch_writes_settings_and_audit(client):
    """合法 provider 切换 → 200, settings.kv 写入, audit_log 一行。"""
    SettingsRepository().delete("llm.default_provider")
    assert _audit_count() == 0

    resp = client.post(
        "/api/settings/llm-provider",
        json={"provider": "ollama", "actor": "web"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["new_provider"] == "ollama"
    assert body["old_provider"] is None
    assert "ollama" in body["valid_providers"]

    # settings.kv 写入
    assert SettingsRepository().get("llm.default_provider") == "ollama"
    # audit_log 一行
    assert _audit_count() == 1
    row = get_connection().execute(
        "SELECT actor, target, detail FROM audit_log ORDER BY occurred_at DESC LIMIT 1"
    ).fetchone()
    assert row["actor"] == "web"
    assert row["target"] == "default_provider"
    import json
    detail = json.loads(row["detail"])
    assert detail["from"] is None and detail["to"] == "ollama"
    assert detail["source"] == "user_switch"

    SettingsRepository().delete("llm.default_provider")


def test_invalid_provider_returns_400_no_settings_no_audit(client):
    """非法 provider → 400, 无 settings 写入, 无 audit。"""
    SettingsRepository().delete("llm.default_provider")
    assert _audit_count() == 0

    resp = client.post(
        "/api/settings/llm-provider",
        json={"provider": "typo_provider"},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    # InvalidParamException envelope: {code, message, trace_id, version}
    assert body["code"] == "INVALID_PARAM"
    assert "typo_provider" in body["message"]
    assert "not in llm.yaml registry" in body["message"]

    # 没有 settings.kv 写入
    assert SettingsRepository().get("llm.default_provider") is None
    # 没有 audit
    assert _audit_count() == 0


def test_audit_failure_does_not_break_response(client):
    """audit_log 写入失败 (mock get_connection 抛) → 仍 200, settings.kv 已落。

    PRD §10 红线 ②: 观测失败不允许阻塞业务流。record_audit 内部全异常
    吞, 此处验证即使 mock 让 get_connection 抛, 端点仍正常返回。
    """
    SettingsRepository().delete("llm.default_provider")

    # patch observability_records.get_connection 让它抛 OperationalError
    with patch(
        "backend.observability_records.get_connection",
        side_effect=sqlite3.OperationalError("audit table missing"),
    ):
        resp = client.post(
            "/api/settings/llm-provider",
            json={"provider": "openai", "actor": "system"},
        )

    # 端点仍返 200 — settings.kv 已落 (先写后审计), 审计失败吞掉
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_provider"] == "openai"
    assert SettingsRepository().get("llm.default_provider") == "openai"

    SettingsRepository().delete("llm.default_provider")


def test_actor_formats_persist_to_audit(client):
    """actor=web / system / agent:test 三种格式均落 audit_log。"""
    for actor in ("web", "system", "agent:test"):
        SettingsRepository().delete("llm.default_provider")
        before = _audit_count()

        resp = client.post(
            "/api/settings/llm-provider",
            json={"provider": "qwen", "actor": actor},
        )
        assert resp.status_code == 200, resp.text

        assert _audit_count() == before + 1
        row = get_connection().execute(
            "SELECT actor FROM audit_log WHERE action='llm_config.update' "
            "ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()
        assert row["actor"] == actor

        SettingsRepository().delete("llm.default_provider")


def test_old_value_recorded_correctly(client):
    """旧值记录正确 (from=None 首次切换, from='sensenova' 二次切换)。"""
    SettingsRepository().delete("llm.default_provider")

    # 第一次切换
    resp1 = client.post(
        "/api/settings/llm-provider",
        json={"provider": "sensenova", "actor": "web"},
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["old_provider"] is None
    assert body1["new_provider"] == "sensenova"

    # 第二次切换
    resp2 = client.post(
        "/api/settings/llm-provider",
        json={"provider": "anthropic", "actor": "web"},
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["old_provider"] == "sensenova"
    assert body2["new_provider"] == "anthropic"

    # audit_log 详情应记录 from/to 序列
    rows = get_connection().execute(
        "SELECT detail FROM audit_log WHERE action='llm_config.update' "
        "ORDER BY occurred_at ASC"
    ).fetchall()
    assert len(rows) == 2
    import json
    details = [json.loads(r["detail"]) for r in rows]
    assert details[0] == {"from": None, "to": "sensenova", "source": "user_switch"}
    assert details[1] == {"from": "sensenova", "to": "anthropic", "source": "user_switch"}

    SettingsRepository().delete("llm.default_provider")


def test_yaml_registry_fallback_when_config_missing(client, monkeypatch):
    """config 缺失时, 合法 provider 校验退化到 ['sensenova', 'ollama']。

    llm_service.config 是 property, 不能直接 setattr; 用 monkeypatch 把
    ``_list_valid_providers`` 内部依赖的 provider 列表 mock 成空 (模拟
    config 加载失败), 验证 endpoint 不挂、且限定到兜底列表。
    """
    SettingsRepository().delete("llm.default_provider")

    # 让 _list_valid_providers 走到兜底分支 (llm_service.config.providers 为空)
    with patch(
        "backend.services.ai_hub.gateway.llm_service"
    ) as mock_llm:
        mock_cfg = type("Cfg", (), {})()
        mock_cfg.providers = {}  # 空 dict → 退兜底
        mock_llm.config = mock_cfg

        # 兜底列表内的 provider 应通过
        resp_ok = client.post(
            "/api/settings/llm-provider",
            json={"provider": "ollama", "actor": "web"},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json()["valid_providers"] == ["sensenova", "ollama"]

        # 兜底列表外的 provider 应被拒
        resp_no = client.post(
            "/api/settings/llm-provider",
            json={"provider": "openai", "actor": "web"},
        )
        assert resp_no.status_code == 400

    SettingsRepository().delete("llm.default_provider")
