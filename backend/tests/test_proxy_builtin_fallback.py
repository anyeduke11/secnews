"""cadence 修正批 T5 — 代理内置可选项 (默认开启) + 失效自动切回直连.

覆盖:
- proxy_config: 默认 builtin / 优先级 env > json > 默认 / 文件缺失·损坏回退 builtin /
  no_proxy 五种匹配语义 / 熔断状态机 (阈值→熔断→窗口→半开→闭合) / mtime 缓存与原子保存
- ProxySession: 代理链路失败 → 摘 proxy 直连重试一次 + 回写熔断器; 熔断期第一跳直连;
  显式 proxy= 参数; 代理成功回写 success
- BackendSession: 代理失败 → 同轮直连重试 (不再同一代理打到死)
- /api/proxy: GET 带 health/builtin; PUT 合并语义 + 非法 mode; /health/reset; /test 汇总 status
- /api/health 代理片段附加字段
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import proxy_config as pc


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    """把配置文件指到临时路径, 清掉 env 覆盖 (conftest 默认 off), 每测试干净。"""
    p = tmp_path / "proxy_config.json"
    monkeypatch.setattr(pc, "PROXY_CONFIG_FILE", str(p))
    monkeypatch.delenv("HOTSPOT_PROXY_MODE", raising=False)
    for k in ("HOTSPOT_HTTP_PROXY", "HOTSPOT_HTTPS_PROXY", "HOTSPOT_SOCKS_PROXY", "HOTSPOT_NO_PROXY"):
        monkeypatch.delenv(k, raising=False)
    pc.invalidate_settings_cache()
    pc.reset_proxy_health()
    yield p
    pc.invalidate_settings_cache()
    pc.reset_proxy_health()


# ---------------------------------------------------------------------------
# 配置: 默认 / 优先级 / 回退
# ---------------------------------------------------------------------------
class TestDefaultsAndPriority:
    def test_builtin_is_default_and_bypasses_domestic(self, cfg_file):
        s = pc.ProxySettings()
        assert s.mode == "builtin"
        assert "*.cn" in s.no_proxy and "36kr.com" in s.no_proxy

    def test_missing_file_falls_back_to_builtin_not_off(self, cfg_file):
        assert not cfg_file.exists()
        assert pc.load_proxy_settings().mode == "builtin"
        assert pc.get_proxy_url("https://github.com/trending") == pc.BUILTIN_PROXY_URL

    def test_corrupt_file_falls_back_to_builtin(self, cfg_file):
        cfg_file.write_text("{not json", encoding="utf-8")
        assert pc.load_proxy_settings().mode == "builtin"

    def test_unknown_mode_in_file_normalized_to_builtin(self, cfg_file):
        cfg_file.write_text(json.dumps({"mode": "weird"}), encoding="utf-8")
        assert pc.load_proxy_settings().mode == "builtin"

    def test_file_off_is_honored(self, cfg_file):
        cfg_file.write_text(json.dumps({"mode": "off"}), encoding="utf-8")
        assert pc.load_proxy_settings().mode == "off"
        assert pc.get_proxy_url("https://github.com/") is None
        assert pc.should_use_proxy("https://github.com/") is False

    def test_env_overrides_file(self, cfg_file, monkeypatch):
        cfg_file.write_text(json.dumps({"mode": "off"}), encoding="utf-8")
        monkeypatch.setenv("HOTSPOT_PROXY_MODE", "manual")
        monkeypatch.setenv("HOTSPOT_HTTP_PROXY", "http://127.0.0.1:7890")
        pc.invalidate_settings_cache()
        s = pc.load_proxy_settings()
        assert (s.mode, s.http_proxy) == ("manual", "http://127.0.0.1:7890")
        assert pc.get_proxy_url("http://example.com/") == "http://127.0.0.1:7890"

    def test_manual_https_only_still_serves_http_targets(self, cfg_file):
        s = pc.ProxySettings(mode="manual", https_proxy="http://p:1")
        assert pc.configured_proxy_url("http://example.com/", s) == "http://p:1"
        s2 = pc.ProxySettings(mode="manual", socks_proxy="socks5://s:1", http_proxy="http://p:1")
        assert pc.configured_proxy_url("https://example.com/", s2) == "socks5://s:1"

    def test_save_is_atomic_and_invalidates_cache(self, cfg_file):
        pc.save_proxy_settings(pc.ProxySettings(mode="manual", http_proxy="http://p:1"))
        assert pc.load_proxy_settings().http_proxy == "http://p:1"
        assert not list(cfg_file.parent.glob(".proxy_config.*.tmp")), "临时文件必须被 replace 掉"
        # 外部改文件 → mtime 变 → 重读
        cfg_file.write_text(json.dumps({"mode": "off"}), encoding="utf-8")
        import os
        os.utime(cfg_file, (cfg_file.stat().st_atime, cfg_file.stat().st_mtime + 5))
        assert pc.load_proxy_settings().mode == "off"


class TestNoProxyMatching:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.ccgp.gov.cn/cggg/", False),      # *.cn
        ("https://36kr.com/feed", False),              # 精确
        ("https://news.36kr.com/x", False),            # 子串
        ("http://printer.local/", False),              # 前导点后缀
        ("http://127.0.0.1:8000/api", False),          # loopback
        ("https://github.com/trending", True),
        ("https://thehackernews.com/feeds/posts/default", True),
        ("https://www.schneier.com/", True),
    ])
    def test_builtin_list(self, cfg_file, url, expected):
        assert pc.should_use_proxy(url) is expected

    def test_fnmatch_wildcard(self, cfg_file):
        pc.save_proxy_settings(pc.ProxySettings(mode="builtin", no_proxy="*.example.*,api-*.foo.com"))
        assert pc.should_use_proxy("https://a.example.org/") is False
        assert pc.should_use_proxy("https://api-1.foo.com/") is False
        assert pc.should_use_proxy("https://web.foo.com/") is True


# ---------------------------------------------------------------------------
# 熔断器
# ---------------------------------------------------------------------------
class TestCircuitBreaker:
    def test_threshold_open_halfopen_close(self, cfg_file, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(pc, "_now", lambda: clock["t"])
        monkeypatch.setattr(pc, "PROXY_FAIL_THRESHOLD", 3)
        monkeypatch.setattr(pc, "PROXY_OPEN_SECONDS", 60.0)

        assert pc.mark_proxy_failure("e1") is False
        assert pc.mark_proxy_failure("e2") is False
        assert pc.proxy_circuit_open() is False
        assert pc.should_use_proxy("https://github.com/") is True
        assert pc.mark_proxy_failure(RuntimeError("proxy refused")) is True
        # 熔断中: 全部直连
        assert pc.proxy_circuit_open() is True
        assert pc.get_proxy_url("https://github.com/") is None
        assert pc.should_use_proxy("https://github.com/") is False
        snap = pc.proxy_health_snapshot()
        assert snap["circuit_open"] and snap["opened_count"] == 1
        assert snap["last_error"].startswith("RuntimeError")
        assert 0 < snap["open_remaining_seconds"] <= 60
        # 窗口过后半开: 允许再试代理
        clock["t"] += 61
        assert pc.proxy_circuit_open() is False
        assert pc.should_use_proxy("https://github.com/") is True
        # 半开探测成功 → 闭合归零
        pc.mark_proxy_success()
        assert pc.proxy_health_snapshot()["consecutive_failures"] == 0
        # 半开探测再失败 → 立即再熔断 (阈值已满)
        pc.mark_proxy_failure("e")
        pc.mark_proxy_failure("e")
        assert pc.mark_proxy_failure("e") is True
        assert pc.proxy_health_snapshot()["opened_count"] == 2

    def test_success_resets_consecutive(self, cfg_file, monkeypatch):
        monkeypatch.setattr(pc, "PROXY_FAIL_THRESHOLD", 3)
        pc.mark_proxy_failure("a")
        pc.mark_proxy_failure("b")
        pc.mark_proxy_success()
        assert pc.mark_proxy_failure("c") is False, "success 归零后单次失败不应熔断"

    def test_reset(self, cfg_file, monkeypatch):
        monkeypatch.setattr(pc, "PROXY_FAIL_THRESHOLD", 1)
        assert pc.mark_proxy_failure("x") is True
        pc.reset_proxy_health()
        assert pc.proxy_circuit_open() is False
        assert pc.proxy_health_snapshot()["total_failures"] == 0


# ---------------------------------------------------------------------------
# ProxySession 请求级回退
# ---------------------------------------------------------------------------
class _FakeCM:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc
        self.exited = False

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self._resp

    async def __aexit__(self, *exc):
        self.exited = True
        return False


class _FakeAioSession:
    def __init__(self, plan):
        self.plan = list(plan)   # 依次返回的 _FakeCM
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.plan.pop(0)

    async def close(self):
        pass


async def _ps_with(fake: _FakeAioSession):
    """ProxySession 实例, 把内部 aiohttp session 换成 fake (先关掉真 session 防泄漏)。"""
    from backend.proxy_session import ProxySession

    ps = ProxySession()
    await ps._session.close()
    ps._session = fake
    return ps


@pytest.fixture
def builtin_env(cfg_file, monkeypatch):
    monkeypatch.setenv("HOTSPOT_PROXY_MODE", "builtin")
    pc.invalidate_settings_cache()
    yield


@pytest.mark.asyncio
async def test_proxy_session_falls_back_to_direct_and_marks_failure(builtin_env):
    from backend.proxy_session import ProxySession

    ok = MagicMock(status=200)
    fake = _FakeAioSession([_FakeCM(exc=aiohttp.ServerDisconnectedError()), _FakeCM(resp=ok)])
    ps = ProxySession()
    await ps._session.close()
    ps._session = fake
    req = ps.get("https://github.com/trending", ssl=False)
    async with req as resp:
        assert resp is ok
    assert len(fake.calls) == 2
    assert fake.calls[0]["proxy"] == pc.BUILTIN_PROXY_URL and fake.calls[0]["ssl"] is False
    assert "proxy" not in fake.calls[1], "回退请求必须摘掉 proxy 直连"
    assert req.fell_back is True and req.via_proxy is False
    assert pc.proxy_health_snapshot()["consecutive_failures"] == 1
    assert fake.plan == [] and fake.calls[1]["url"] == "https://github.com/trending"


@pytest.mark.asyncio
async def test_proxy_session_timeout_via_proxy_also_falls_back(builtin_env):

    ok = MagicMock(status=200)
    fake = _FakeAioSession([_FakeCM(exc=asyncio.TimeoutError()), _FakeCM(resp=ok)])
    ps = await _ps_with(fake)
    async with ps.get("https://github.com/trending") as resp:
        assert resp is ok
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_proxy_session_success_marks_success_and_exits_cm(builtin_env):

    ok = MagicMock(status=200)
    cm = _FakeCM(resp=ok)
    fake = _FakeAioSession([cm])
    ps = await _ps_with(fake)
    pc.mark_proxy_failure("earlier")
    req = ps.get("https://github.com/trending")
    async with req as resp:
        assert resp is ok
    assert req.via_proxy is True and cm.exited is True
    assert pc.proxy_health_snapshot()["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_proxy_session_circuit_open_goes_direct_first(builtin_env, monkeypatch):

    monkeypatch.setattr(pc, "PROXY_FAIL_THRESHOLD", 1)
    pc.mark_proxy_failure("dead")
    assert pc.proxy_circuit_open()
    ok = MagicMock(status=200)
    fake = _FakeAioSession([_FakeCM(resp=ok)])
    ps = await _ps_with(fake)
    async with ps.get("https://github.com/trending") as resp:
        assert resp is ok
    assert len(fake.calls) == 1 and "proxy" not in fake.calls[0]


@pytest.mark.asyncio
async def test_proxy_session_domestic_host_never_proxied(builtin_env):

    ok = MagicMock(status=200)
    fake = _FakeAioSession([_FakeCM(resp=ok)])
    ps = await _ps_with(fake)
    async with ps.get("https://36kr.com/feed") as resp:
        assert resp is ok
    assert "proxy" not in fake.calls[0]


@pytest.mark.asyncio
async def test_proxy_session_explicit_proxy_kwarg_respected(cfg_file):

    ok = MagicMock(status=200)
    fake = _FakeAioSession([_FakeCM(resp=ok)])
    ps = await _ps_with(fake)
    async with ps.get("https://36kr.com/", proxy="http://127.0.0.1:1") as resp:
        assert resp is ok
    assert fake.calls[0]["proxy"] == "http://127.0.0.1:1"


@pytest.mark.asyncio
async def test_proxy_session_ssrf_gate(cfg_file):
    from backend.proxy_session import ProxySession
    from backend.utils.url_safety import UrlSafetyError

    ps = ProxySession()
    try:
        with pytest.raises(UrlSafetyError):
            ps.get("http://127.0.0.1:8000/api/health")
    finally:
        await ps.close()


# ---------------------------------------------------------------------------
# BackendSession (httpx) 回退
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backend_session_retries_direct_after_proxy_failure(builtin_env):
    import httpx

    from backend.collectors.session import BackendSession

    resp = MagicMock(status_code=200, text="direct-ok")
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(side_effect=[httpx.ConnectError("proxy refused"), resp])
    client.aclose = AsyncMock()
    with patch("backend.collectors.session.httpx.AsyncClient", return_value=client):
        async with BackendSession() as s:
            text = await s.get("https://github.com/trending")
    assert text == "direct-ok"
    assert client.get.await_count == 2
    first, second = client.get.await_args_list
    assert first.kwargs["proxies"] == {"all://": pc.BUILTIN_PROXY_URL}
    assert second.kwargs["proxies"] is None
    assert pc.proxy_health_snapshot()["consecutive_failures"] == 1


@pytest.mark.asyncio
async def test_backend_session_proxy_success_marks_success(builtin_env):
    from backend.collectors.session import BackendSession

    resp = MagicMock(status_code=200, text="via-proxy")
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.aclose = AsyncMock()
    pc.mark_proxy_failure("earlier")
    with patch("backend.collectors.session.httpx.AsyncClient", return_value=client):
        async with BackendSession() as s:
            assert await s.get("https://github.com/trending") == "via-proxy"
    assert pc.proxy_health_snapshot()["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture
def api(cfg_file):
    from backend.api.proxy import router
    from backend.exceptions import register_exception_handlers

    app = FastAPI(title="test")
    register_exception_handlers(app)
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_get_settings_exposes_builtin_health_modes(api):
    d = api.get("/api/proxy/settings").json()
    assert d["settings"]["mode"] == "builtin"
    assert d["effective_proxy"] == pc.BUILTIN_PROXY_URL
    assert d["builtin"]["proxy_url"] == pc.BUILTIN_PROXY_URL
    assert set(d["valid_modes"]) == set(pc.VALID_MODES)
    assert d["health"]["circuit_open"] is False


def test_put_merges_and_validates(api):
    r = api.put("/api/proxy/settings", json={"mode": "manual", "http_proxy": "http://u:pw@p:1"})
    assert r.json()["status"] == "ok"
    assert r.json()["settings"]["http_proxy"] == "http://u:***@p:1"
    # 只改 mode, 不带 http_proxy → 现值保留 (旧实现会清空)
    r2 = api.put("/api/proxy/settings", json={"mode": "builtin"})
    assert r2.json()["status"] == "ok"
    assert pc.load_proxy_settings().http_proxy == "http://u:pw@p:1"
    assert pc.load_proxy_settings().mode == "builtin"
    # 非法 mode
    assert api.put("/api/proxy/settings", json={"mode": "nope"}).json()["status"] == "error"
    # 保存会重置熔断器
    pc.mark_proxy_failure("x")
    api.put("/api/proxy/settings", json={"mode": "builtin"})
    assert pc.proxy_health_snapshot()["total_failures"] == 0


def test_health_reset_closes_circuit(api, monkeypatch):
    monkeypatch.setattr(pc, "PROXY_FAIL_THRESHOLD", 1)
    pc.mark_proxy_failure("dead")
    assert pc.proxy_circuit_open()
    d = api.post("/api/proxy/health/reset").json()
    assert d["status"] == "ok" and d["health"]["circuit_open"] is False


def _fake_probe(direct_ok: bool, proxy_ok: bool):
    async def _p(url, proxy):
        ok = proxy_ok if proxy else direct_ok
        return {"ok": ok, "status": 200 if ok else None, "error": None if ok else "timeout", "ms": 5}
    return _p


def test_connectivity_test_status_ok(api):
    with patch("backend.utils.proxy_probe.probe_url", side_effect=_fake_probe(True, True)):
        d = api.get("/api/proxy/test").json()
    assert d["status"] == "ok" and d["mode"] == "builtin"
    assert len(d["results"]) == 5
    foreign = [r for r in d["results"] if r["policy"] == "proxy"]
    domestic = [r for r in d["results"] if r["policy"] == "direct"]
    assert len(foreign) == 3 and len(domestic) == 2
    assert all(r["proxy"] is not None and r["direct"] is not None for r in d["results"])


def test_connectivity_test_status_down_when_proxy_dead(api):
    with patch("backend.utils.proxy_probe.probe_url", side_effect=_fake_probe(True, False)):
        d = api.get("/api/proxy/test").json()
    assert d["status"] == "down"
    assert all(r["ok"] is False for r in d["results"] if r["policy"] == "proxy")
    assert all(r["ok"] is True for r in d["results"] if r["policy"] == "direct")


def test_connectivity_test_skipped_when_off(api):
    pc.save_proxy_settings(pc.ProxySettings(mode="off"))
    with patch("backend.utils.proxy_probe.probe_url", side_effect=_fake_probe(True, True)):
        d = api.get("/api/proxy/test").json()
    assert d["status"] == "skipped"
    assert all(r["proxy"] is None for r in d["results"])


def test_health_component_has_circuit_fields(cfg_file):
    from backend.api.health import _proxy_health

    h = _proxy_health()
    assert h["ok"] and h["mode"] == "builtin" and h["enabled"] is True
    assert h["effective_proxy"] == pc.BUILTIN_PROXY_URL and h["circuit_open"] is False
