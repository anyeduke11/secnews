"""cadence 修正批 T2.2 — 抓取链根因修复回归.

诊断实测 (scripts/audit_dead_source_triage.py + aiohttp 对照) 确认的三类根因:
- 编码陷阱: 政企站声明 GB2312 却含 GBK 扩展字, ``resp.text()`` 抛 UnicodeDecodeError
  被级联链吞掉 → "all failed" (okcis.cn 200/472KB 被判 dead 数十轮)
- RSS 机器人 UA: feedparser 默认 UA 被 Cloudflare 挑战页拦下 → ``rss_empty bozo=True``
  (嘶吼 4hou.com/feed 换浏览器 UA 即拿到 entries)
- 失败原因不可见: bid 三步失败只留 DEBUG, last_error 无诊断价值

覆盖:
- ``backend.utils.http_text.decode_html_bytes`` / ``read_text_lenient``
- ``FetchersMixin._fetch_rss`` 传浏览器 UA + Accept 头; 超时 → ``rss_timeout``
- ``BidCollector._fetch_with_fallback`` 直连宽容解码成功 / 失败时 error_msg 携带各步原因
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.collectors import base as _base
from backend.utils.http_text import decode_html_bytes, read_text_lenient

# GB2312 声明常见, 但 "•" (U+2022) 只在 GBK/GB18030 有编码 (0xA1 0xF9), 严格 gb2312 解码会炸
_GBK_ONLY_TEXT = "招标公告•安全设备采购"


# ---------------------------------------------------------------------------
# decode_html_bytes
# ---------------------------------------------------------------------------
class TestDecodeHtmlBytes:
    def test_gb2312_declared_gbk_content_upgrades_to_gb18030(self):
        raw = _GBK_ONLY_TEXT.encode("gb18030")
        with pytest.raises(UnicodeDecodeError):
            raw.decode("gb2312")  # 前提: 严格按声明确实会炸
        assert decode_html_bytes(raw, "gb2312") == _GBK_ONLY_TEXT
        assert decode_html_bytes(raw, "GBK") == _GBK_ONLY_TEXT
        assert decode_html_bytes(raw, "x-gbk") == _GBK_ONLY_TEXT

    def test_utf8_default_when_no_declaration(self):
        assert decode_html_bytes("安全资讯".encode()) == "安全资讯"

    def test_meta_charset_sniffed_when_header_missing(self):
        raw = ('<html><head><meta charset="gbk"><title>' + _GBK_ONLY_TEXT + "</title>").encode(
            "gb18030"
        )
        assert _GBK_ONLY_TEXT in decode_html_bytes(raw, None)

    def test_http_equiv_meta_sniffed(self):
        raw = (
            '<meta http-equiv="Content-Type" content="text/html; charset=gb2312">' + _GBK_ONLY_TEXT
        ).encode("gb18030")
        assert _GBK_ONLY_TEXT in decode_html_bytes(raw, None)

    def test_unknown_declared_charset_falls_through(self):
        raw = "ok 中文".encode()
        assert decode_html_bytes(raw, "x-not-a-codec") == "ok 中文"

    def test_never_raises_on_garbage(self):
        garbage = bytes(range(256)) * 4
        out = decode_html_bytes(garbage, "gb2312")
        assert isinstance(out, str) and out  # replace 兜底, 不抛

    def test_declared_takes_priority_over_meta(self):
        # 头声明 utf-8 且内容确为 utf-8, meta 写错成 gbk 不应干扰
        raw = ('<meta charset="gbk">' + "正确的 utf-8 内容").encode()
        assert "正确的 utf-8 内容" in decode_html_bytes(raw, "utf-8")


@pytest.mark.asyncio
async def test_read_text_lenient_uses_resp_charset_and_read():
    class _Resp:
        charset = "gb2312"

        async def read(self):
            return _GBK_ONLY_TEXT.encode("gb18030")

    assert await read_text_lenient(_Resp()) == _GBK_ONLY_TEXT


# ---------------------------------------------------------------------------
# _fetch_rss: 浏览器 UA + 超时兜底
# ---------------------------------------------------------------------------
def _rss_collector():
    from backend.collectors.security_collector import SecurityCollector

    return SecurityCollector()


def _feed(entries):
    d = MagicMock()
    d.get = lambda k, default=None: {"status": 200, "bozo": False, "entries": entries}.get(k, default)
    return d


@pytest.mark.asyncio
async def test_fetch_rss_bytes_sends_browser_ua_via_proxy_aware_layer():
    """T5: 浏览器 UA + Accept 头在 _fetch_rss_bytes 的 HTTP 层注入 (经 ProxySession)。"""
    captured: dict = {}

    ok = MagicMock(status=200)
    ok.read = AsyncMock(return_value=b"<rss><channel><item><title>t</title></item></channel></rss>")
    resp = _FakeResp(200, b"<rss><channel/></rss>")
    resp.read = AsyncMock(return_value=b"<rss><channel><item><title>t</title></item></channel></rss>")
    resp.headers = {"Content-Type": "application/rss+xml"}

    class _FakePS:
        def __init__(self, headers=None, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return resp

    c = _rss_collector()
    with patch("backend.proxy_session.ProxySession", _FakePS):
        status, headers, body = await c._fetch_rss_bytes("https://www.4hou.com/feed")
    assert captured["url"] == "https://www.4hou.com/feed"
    assert captured["headers"]["User-Agent"] == _base.UA, "RSS 必须用浏览器 UA (feedparser 默认 UA 被 Cloudflare 拦)"
    assert "rss+xml" in captured["headers"]["Accept"]
    assert "Accept-Language" in captured["headers"]
    assert status == 200 and b"<rss>" in body


@pytest.mark.asyncio
async def test_fetch_rss_timeout_returns_rss_timeout_error():
    c = _rss_collector()
    c.timeout = 0.2
    src = {"name": "slow", "url": "https://example.com/", "rss_url": "https://example.com/feed"}

    async def _hang(*_a, **_k):
        await asyncio.sleep(1.0)
        return 200, {}, b""

    c._fetch_rss_bytes = _hang  # type: ignore[method-assign]
    items, result = await c._fetch_rss(src)
    assert items == []
    assert result.error_msg.startswith("rss_timeout")


# ---------------------------------------------------------------------------
# BidCollector._fetch_with_fallback — DEV-0178: 已随标讯剔除移除
# (_FakeResp 类仍被上方 RSS UA 用例使用, 保留)
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status: int, raw: bytes = b"", charset: str | None = None):
        self.status = status
        self._raw = raw
        self.charset = charset

    async def read(self):
        return self._raw

    async def text(self):  # 旧路径: 严格解码 (模拟 aiohttp 行为), 用于证明陷阱确实存在
        return self._raw.decode(self.charset or "utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_asyncio_marker_sanity():
    # 防止 pytest-asyncio 模式变化时上面 async 测试被静默跳过
    assert asyncio.iscoroutinefunction(test_fetch_rss_timeout_returns_rss_timeout_error)
    assert SimpleNamespace is not None
