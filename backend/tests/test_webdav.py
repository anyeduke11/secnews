"""Phase 42 WebDAV client 测试 (mock httpx)。

覆盖:
- _join URL 拼接 + 路径编码
- test_connection: 200/207/401/403/404/timeout/connect error
- exists: HEAD 200/404
- mkdir: MKCOL 201/405/401
- upload: PUT 200/201/401/error
- download: GET 200/404 (返回 None)/error
- URL path 编码 (含中文)
"""
from __future__ import annotations

import asyncio
from typing import Iterator
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from backend.services.webdav_client import (
    WebDAVAuthError,
    WebDAVClient,
    WebDAVError,
)


def _run(coro):
    """同步跑 async coroutine — 用独立 event loop 避免 pytest MainThread 冲突。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_url_join_basic():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    assert c._join("/hotspot/config.json") == "https://dav.jianguoyun.com/dav/hotspot/config.json"
    # 去掉末尾 /
    c2 = WebDAVClient("https://dav.jianguoyun.com/dav/", "u", "p")
    assert c2._join("/x.json") == "https://dav.jianguoyun.com/dav/x.json"
    # 自动补 /
    c3 = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    assert c3._join("x.json") == "https://dav.jianguoyun.com/dav/x.json"


def test_url_join_unicode():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    # 中文路径应被 percent-encode
    out = c._join("/中文/配置.json")
    assert "%E4%B8%AD%E6%96%87" in out
    assert "%E9%85%8D%E7%BD%AE" in out


def test_constructor_validates():
    with pytest.raises(WebDAVError):
        WebDAVClient("", "u", "p")
    with pytest.raises(WebDAVError):
        WebDAVClient("https://x", "", "p")
    with pytest.raises(WebDAVError):
        WebDAVClient("https://x", "u", None)


def _make_response(status_code: int, content: bytes = b"") -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.reason_phrase = "OK" if status_code < 400 else "Error"
    r.content = content
    # text 应与 content 解码一致, 供 _body_hint 使用
    try:
        r.text = content.decode("utf-8")
    except UnicodeDecodeError:
        r.text = content.decode("utf-8", errors="replace")
    return r


def test_test_connection_success():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch("httpx.AsyncClient") as MockClient:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=None)
        ctx.request = AsyncMock(return_value=_make_response(207))
        MockClient.return_value = ctx
        ok, msg = _run(c.test_connection())
        assert ok is True
        assert "成功" in msg


def test_test_connection_auth_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch("httpx.AsyncClient") as MockClient:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=None)
        ctx.request = AsyncMock(return_value=_make_response(401))
        MockClient.return_value = ctx
        ok, msg = _run(c.test_connection())
        assert ok is False
        assert "认证失败" in msg


def test_test_connection_connect_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch("httpx.AsyncClient") as MockClient:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=None)
        ctx.request = AsyncMock(side_effect=httpx.ConnectError("nope"))
        MockClient.return_value = ctx
        ok, msg = _run(c.test_connection())
        assert ok is False
        assert "无法连接" in msg


def test_exists_true():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(200))):
        assert _run(c.exists("/x.json")) is True


def test_exists_false():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(404))):
        assert _run(c.exists("/x.json")) is False


def test_exists_auth_error_raises():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(401))):
        with pytest.raises(WebDAVAuthError):
            _run(c.exists("/x.json"))


def test_mkcol_201():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(201))):
        assert _run(c.mkdir("/hotspot")) is True


def test_mkcol_405_already_exists_ok():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(405))):
        assert _run(c.mkdir("/hotspot")) is True


def test_mkcol_409_jianguoyun_quirk_treated_as_exists():
    """坚果云对已存在目录 MKCOL 返回 409, 应视为成功, 不可抛错。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(409))):
        assert _run(c.mkdir("/hotspot")) is True


def test_ensure_parent_dirs_chain():
    """/a/b/c.json 应触发 MKCOL /a, /a/b (跳过自身)。

    新版 ensure_parent_dirs 先 HEAD 探一次, 不存在才 MKCOL; MKCOL 后再
    HEAD 验证。测试用 exists 序列: 每层父目录 = [False, True] (前 False
    触发 MKCOL, MKCOL 后 True 验证成功), 共两层父目录。
    """
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    calls: list[str] = []
    sequence = [False, True, False, True]
    async def fake_exists(p):
        return sequence.pop(0)
    async def fake_mkdir(path):
        calls.append(path)
    with patch.object(c, "exists", AsyncMock(side_effect=fake_exists)), \
         patch.object(c, "mkdir", AsyncMock(side_effect=fake_mkdir)):
        _run(c.ensure_parent_dirs("/a/b/c.json"))
    assert calls == ["/a", "/a/b"]


def test_ensure_parent_dirs_no_parent():
    """/config.json 顶层文件无需 MKCOL (parts 长度为 1)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    calls: list[str] = []
    async def fake_mkdir(path):
        calls.append(path)
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "mkdir", AsyncMock(side_effect=fake_mkdir)):
        _run(c.ensure_parent_dirs("/config.json"))
    assert calls == []


def test_upload_auto_ensures_parents():
    """upload 默认 ensure_parents=True, 应先 MKCOL 父目录再 PUT。

    mkdir 内部走 ``_log_path`` (在 mock 看到带 /dav 的 path);
    upload 调 ``_request`` 时传入原始 path (mock 直接看到, 未经 _log_path)。
    所以 MKCOL mock path 带 /dav 前缀, PUT mock path 是原始路径。
    """
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    calls: list[tuple[str, str]] = []
    sequence = [False, True, False, True]
    async def fake_exists(p):
        return sequence.pop(0)
    async def fake_request(method, path, **kw):
        calls.append((method, path))
        if method == "MKCOL":
            return _make_response(201)
        return _make_response(201)
    with patch.object(c, "_request", AsyncMock(side_effect=fake_request)), \
         patch.object(c, "exists", AsyncMock(side_effect=fake_exists)):
        status = _run(c.upload("/hotspot/sub/config.json", b"x"))
    assert status == 201
    methods = [m for m, _ in calls]
    assert methods == ["MKCOL", "MKCOL", "PUT"]
    # 父目录顺序: /dav/hotspot, /dav/hotspot/sub (MKCOL 内部 _log_path 加前缀)
    assert calls[0][1] == "/dav/hotspot"
    assert calls[1][1] == "/dav/hotspot/sub"
    # PUT 传入原始 path, _request mock 看到的 path 不带 /dav 前缀
    assert calls[2][1] == "/hotspot/sub/config.json"


def test_upload_ensure_parents_false_skips_mkcol():
    """ensure_parents=False 时不调 MKCOL (兼容旧用法)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    calls: list[tuple[str, str]] = []
    async def fake_request(method, path, **kw):
        calls.append((method, path))
        return _make_response(201)
    with patch.object(c, "_request", AsyncMock(side_effect=fake_request)):
        status = _run(c.upload("/a/b.json", b"x", ensure_parents=False))
    assert status == 201
    assert [m for m, _ in calls] == ["PUT"]


def test_upload_409_error_includes_body():
    """PUT 409 错误信息应含 body 摘要, 便于诊断父目录冲突。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 409
    resp.reason_phrase = "Conflict"
    resp.text = "<D:error>父目录不存在</D:error>"
    with patch.object(c, "_request", AsyncMock(return_value=resp)):
        with pytest.raises(WebDAVError) as ei:
            _run(c.upload("/hotspot/x.json", b"x", ensure_parents=False))
    msg = str(ei.value)
    assert "409" in msg
    assert "父目录不存在" in msg


def test_download_500_error_includes_body():
    """download 5xx 错误信息含 body 摘要。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 500
    resp.reason_phrase = "Server Error"
    resp.text = "internal error"
    with patch.object(c, "_request", AsyncMock(return_value=resp)):
        with pytest.raises(WebDAVError) as ei:
            _run(c.download("/x.json"))
    msg = str(ei.value)
    assert "500" in msg
    assert "internal error" in msg


# ---------------------------------------------------------------------------
# 坚果云 quirk: AncestorsNotFound + MKCOL 异步落库
# ---------------------------------------------------------------------------
def test_ensure_one_dir_already_exists_skips_mkcol():
    """HEAD 200 表示父目录已存在, 不应再 MKCOL。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "mkdir", AsyncMock()) as mk:
        _run(c._ensure_one_dir("/hotspot"))
    mk.assert_not_called()


def test_ensure_one_dir_mkcol_then_head_ok():
    """MKCOL 后 HEAD 200 → 不重试。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    # exists: 第一次 False, 第二次 True
    exists_results = [False, True]
    async def fake_exists(p):
        return exists_results.pop(0)
    mkdir_mock = AsyncMock()
    with patch.object(c, "exists", AsyncMock(side_effect=fake_exists)), \
         patch.object(c, "mkdir", mkdir_mock), \
         patch("asyncio.sleep", AsyncMock()) as sleep_mock:
        _run(c._ensure_one_dir("/hotspot"))
    mkdir_mock.assert_called_once_with("/hotspot")
    sleep_mock.assert_not_called()


def test_ensure_one_dir_mkcol_quirk_retry():
    """坚果云 quirk: MKCOL 返 201 但 HEAD 仍 404 → sleep + 再 MKCOL。

    序列: [False, False, False, True]
    - attempt=1: exists=False → mkcol → exists=False → sleep
    - attempt=2: exists=False → mkcol → exists=True → return
    → 2 次 mkcol + 1 次 sleep
    """
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    sequence = [False, False, False, True]
    async def fake_exists(p):
        return sequence.pop(0)
    mkdir_mock = AsyncMock()
    sleeps: list[float] = []
    async def fake_sleep(s):
        sleeps.append(s)
    with patch.object(c, "exists", AsyncMock(side_effect=fake_exists)), \
         patch.object(c, "mkdir", mkdir_mock), \
         patch("backend.services.webdav_client.asyncio.sleep", fake_sleep):
        _run(c._ensure_one_dir("/hotspot"))
    assert mkdir_mock.call_count == 2
    assert sleeps == [0.3]


def test_ensure_one_dir_give_up_raises():
    """两次 MKCOL + HEAD 都失败 → 抛错。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=False)), \
         patch.object(c, "mkdir", AsyncMock()):
        with pytest.raises(WebDAVError) as ei:
            _run(c._ensure_one_dir("/hotspot"))
        assert "MKCOL + HEAD 验证失败" in str(ei.value)


def test_upload_retry_on_ancestors_not_found():
    """PUT 第一次 409 AncestorsNotFound, 自动 sleep + 再 PUT 成功。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    # 第一次 PUT: 409 AncestorsNotFound; 第二次: 201
    put_responses = [
        _make_response(409, b"<D:error>AncestorsNotFound</D:error>"),
        _make_response(201, b""),
    ]
    put_calls: list[str] = []
    async def fake_request(method, path, **kw):
        if method == "PUT":
            put_calls.append(path)
            return put_responses.pop(0)
        # HEAD / MKCOL 不需要
        return _make_response(200 if method == "HEAD" else 201)
    sleeps: list[float] = []
    async def fake_sleep(s):
        sleeps.append(s)
    with patch.object(c, "_request", AsyncMock(side_effect=fake_request)), \
         patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch("backend.services.webdav_client.asyncio.sleep", fake_sleep):
        status = _run(c.upload("/hotspot/config.json", b"x"))
    assert status == 201
    assert len(put_calls) == 2
    assert sleeps == [0.5]


def test_upload_no_retry_on_other_409():
    """非 AncestorsNotFound 的 409 不重试, 直接抛。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "_request", AsyncMock(return_value=_make_response(409, b"<D:error>other</D:error>"))):
        with pytest.raises(WebDAVError) as ei:
            _run(c.upload("/x.json", b"x"))
        msg = str(ei.value)
        assert "409" in msg
        assert "other" in msg


def test_upload_retry_disabled_does_not_retry():
    """retry_on_ancestors_not_found=False 时不重试, 直接抛错。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "_request", AsyncMock(return_value=_make_response(409, b"<D:error>AncestorsNotFound</D:error>"))):
        with pytest.raises(WebDAVError) as ei:
            _run(c.upload("/x.json", b"x", retry_on_ancestors_not_found=False))
        assert "AncestorsNotFound" in str(ei.value)


def test_upload_give_up_after_retry():
    """重试后仍 409 AncestorsNotFound → 抛错 (信息含 重试后 字样)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    # 两次 PUT 都 409 AncestorsNotFound
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "_request", AsyncMock(return_value=_make_response(409, b"<D:error>AncestorsNotFound</D:error>"))), \
         patch("backend.services.webdav_client.asyncio.sleep", AsyncMock()):
        with pytest.raises(WebDAVError) as ei:
            _run(c.upload("/x.json", b"x"))
        msg = str(ei.value)
        assert "重试后" in msg
        assert "AncestorsNotFound" in msg


# ---------------------------------------------------------------------------
# 坚果云 HEAD quirk: 存在的目录 HEAD 返 409, 应视为已存在
# ---------------------------------------------------------------------------
def test_exists_404_returns_false():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(404))):
        assert _run(c.exists("/missing")) is False


def test_exists_200_returns_true():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(200))):
        assert _run(c.exists("/present")) is True


def test_exists_207_returns_true():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(207))):
        assert _run(c.exists("/present")) is True


def test_exists_409_jianguoyun_quirk_treated_as_true():
    """坚果云对已存在目录 HEAD 返 409 — 视为 True (已存在)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(409))):
        assert _run(c.exists("/hotspot")) is True


def test_exists_405_treated_as_true():
    """HEAD 不允许 (405) — 视为已存在 (资源存在但方法不允许)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(405))):
        assert _run(c.exists("/hotspot")) is True


def test_exists_301_treated_as_true():
    """301 redirect — 视为已存在 (重定向到存在的资源)。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(301))):
        assert _run(c.exists("/hotspot")) is True


def test_exists_500_raises_with_body():
    """HEAD 5xx 抛错, 错误信息含 body 摘要。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 503
    resp.reason_phrase = "Service Unavailable"
    resp.text = "server overloaded"
    with patch.object(c, "_request", AsyncMock(return_value=resp)):
        with pytest.raises(WebDAVError) as ei:
            _run(c.exists("/x"))
    msg = str(ei.value)
    assert "503" in msg
    assert "server overloaded" in msg


def test_ensure_one_dir_exists_409_skips_mkcol():
    """exists HEAD 409 (坚果云 quirk) → 直接返回, 不再 MKCOL。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=True)), \
         patch.object(c, "mkdir", AsyncMock()) as mk:
        _run(c._ensure_one_dir("/hotspot"))
    mk.assert_not_called()


def test_ensure_one_dir_force_mkcol_skips_exists():
    """force_mkcol=True 时跳过 exists 检查, 强制 MKCOL。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "exists", AsyncMock(return_value=True)) as exists_mock, \
         patch.object(c, "mkdir", AsyncMock()) as mk:
        _run(c._ensure_one_dir("/hotspot", force_mkcol=True))
    # 至少调一次 MKCOL, 且不应调 exists (跳过检查)
    assert mk.call_count >= 1
    exists_mock.assert_not_called()


def test_ensure_parent_dirs_force_mkcol():
    """/a/b/c.json force_mkcol=True → 每层父目录强制 MKCOL, 不调 exists。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    mkdir_calls: list[str] = []
    async def fake_mkdir(path):
        mkdir_calls.append(path)
    with patch.object(c, "exists", AsyncMock(return_value=True)) as exists_mock, \
         patch.object(c, "mkdir", AsyncMock(side_effect=fake_mkdir)):
        _run(c.ensure_parent_dirs("/a/b/c.json", force_mkcol=True))
    assert mkdir_calls == ["/a", "/a/b"]
    exists_mock.assert_not_called()


def test_upload_retry_uses_force_mkcol_on_attempt_2():
    """PUT 第一次 409 AncestorsNotFound, retry 时 ensure_parents 走 force_mkcol=True。"""
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    put_responses = [
        _make_response(409, b"<D:error>AncestorsNotFound</D:error>"),
        _make_response(201, b""),
    ]
    # 记录 ensure_parents 调用参数
    ensure_calls: list[dict] = []
    async def fake_ensure(path, **kw):
        ensure_calls.append({"path": path, **kw})
        return
    with patch.object(c, "_request", AsyncMock(side_effect=lambda m, p, **kw: (
        put_responses.pop(0) if m == "PUT" else _make_response(200)
    ))), \
         patch.object(c, "ensure_parent_dirs", AsyncMock(side_effect=fake_ensure)), \
         patch("backend.services.webdav_client.asyncio.sleep", AsyncMock()):
        status = _run(c.upload("/hotspot/config.json", b"x"))
    assert status == 201
    # ensure_parents 应调 2 次: attempt=1 force_mkcol=False, attempt=2 force_mkcol=True
    assert len(ensure_calls) == 2
    assert ensure_calls[0]["force_mkcol"] is False
    assert ensure_calls[1]["force_mkcol"] is True


def test_upload_success():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(201))):
        status = _run(c.upload("/x.json", b"hello"))
        assert status == 201


def test_upload_auth_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(401))):
        with pytest.raises(WebDAVAuthError):
            _run(c.upload("/x.json", b"hello"))


def test_upload_server_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(500))):
        with pytest.raises(WebDAVError):
            _run(c.upload("/x.json", b"hello"))


def test_upload_wrong_type():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with pytest.raises(WebDAVError):
        _run(c.upload("/x.json", "not-bytes"))


def test_download_200():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(200, b"data"))):
        out = _run(c.download("/x.json"))
        assert out == b"data"


def test_download_404_returns_none():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(404))):
        out = _run(c.download("/x.json"))
        assert out is None


def test_download_auth_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(403))):
        with pytest.raises(WebDAVAuthError):
            _run(c.download("/x.json"))


def test_download_server_error():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch.object(c, "_request", AsyncMock(return_value=_make_response(500))):
        with pytest.raises(WebDAVError):
            _run(c.download("/x.json"))


def test_request_handles_timeout():
    c = WebDAVClient("https://dav.jianguoyun.com/dav", "u", "p")
    with patch("httpx.AsyncClient") as MockClient:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=None)
        ctx.request = AsyncMock(side_effect=httpx.TimeoutException("slow"))
        MockClient.return_value = ctx
        with pytest.raises(WebDAVError) as ei:
            _run(c._request("GET", "/x"))
        assert "超时" in str(ei.value)
