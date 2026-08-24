"""S1-3 书签存活三态检测测试 — check_url 单测 (本地 http.server) + sweep 集成。

三态契约 (docs/HOTSPOT_SECNEWS_INTEGRATION.md §7.1):
  alive   = HTTP < 400
  dead    = HTTP >= 400 / DNS 不存在 / 连接拒绝
  unknown = 超时等瞬态; check_url 永不抛异常。
"""
from __future__ import annotations

import http.server
import threading

import pytest

from backend.wiki_fs.liveness import (
    ALIVE_STATES,
    check_url,
    liveness_counts,
    sweep_liveness,
)

_BOOKMARK_HTML = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="http://127.0.0.1:{port}/ok">Alive Link</A>
<DT><A HREF="http://127.0.0.1:{port}/missing">Dead Link</A>
<DT><A HREF="https://nonexistent.invalid.example">Dns Dead</A>
</DL><p>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    """HEAD/GET 双支持: /ok → 200, 其余 → 404。"""

    def _respond(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(b"ok")

    def do_HEAD(self):  # noqa: N802
        self._respond(200 if self.path == "/ok" else 404)

    def do_GET(self):  # noqa: N802
        self._respond(200 if self.path in ("/ok", "/head-only") else 404)

    def log_message(self, *args):  # 静默测试日志
        pass


@pytest.fixture(scope="module")
def http_port():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def tmp_wiki(tmp_path):
    import os

    from backend.wiki_fs import WikiFs

    root = str(tmp_path / "wiki")
    os.makedirs(root, exist_ok=True)
    return WikiFs(root)


class TestCheckUrl:
    def test_alive_states_constant(self):
        assert ALIVE_STATES == ("alive", "dead", "unknown")

    def test_alive_200(self, http_port):
        assert check_url(f"http://127.0.0.1:{http_port}/ok") == "alive"

    def test_head_405_falls_back_to_get(self, http_port):
        """HEAD 被拒 (405/501) 时降级 GET 重试 → alive。"""
        import urllib.error
        from unittest.mock import patch

        from backend.wiki_fs import liveness as lv

        real_urlopen = lv.urllib.request.urlopen

        def fake_urlopen(req, timeout=10.0):
            if getattr(req, "method", "GET") == "HEAD":
                raise urllib.error.HTTPError(
                    req.full_url, 405, "Method Not Allowed", {}, None
                )
            return real_urlopen(req, timeout=timeout)

        with patch.object(lv.urllib.request, "urlopen", side_effect=fake_urlopen):
            assert check_url(f"http://127.0.0.1:{http_port}/ok") == "alive"

    def test_dead_404(self, http_port):
        assert check_url(f"http://127.0.0.1:{http_port}/missing") == "dead"

    def test_dead_dns_failure(self):
        assert check_url("https://nonexistent.invalid.example", timeout=3.0) == "dead"

    def test_unknown_timeout_never_raises(self):
        """不可路由地址 → 连接挂起/拒绝; 无论哪种结果都必须收敛为合法三态且不抛。"""
        state = check_url("http://10.255.255.1/nope", timeout=1.0)
        assert state in ALIVE_STATES

    def test_empty_url_is_unknown(self):
        assert check_url("") == "unknown"


class TestSweepLiveness:
    def test_import_bookmarks_default_unknown(self, tmp_wiki):
        result = tmp_wiki.import_bookmarks(_BOOKMARK_HTML.format(port=9))
        assert result["added"] == 3
        for item_id in tmp_wiki.list_ids():
            fm = tmp_wiki.read_item(item_id)["fm"]
            assert fm["source"] == "bookmark-import"
            assert fm["alive"] == "unknown"
            assert "alive_checked_at" not in fm

    def test_sweep_writes_back_three_states(self, tmp_wiki, http_port):
        tmp_wiki.import_bookmarks(_BOOKMARK_HTML.format(port=http_port))
        stats = sweep_liveness(tmp_wiki, workers=4, timeout=3.0)
        assert set(stats) == {"total", *ALIVE_STATES}
        assert stats["total"] == 3
        assert stats["alive"] == 1                    # /ok → 200
        assert stats["dead"] + stats["unknown"] == 2  # 404 + DNS 分支

        states = {}
        for item_id in tmp_wiki.list_ids():
            fm = tmp_wiki.read_item(item_id)["fm"]
            states[fm["url"]] = fm["alive"]
            assert "alive_checked_at" in fm
        assert states[f"http://127.0.0.1:{http_port}/ok"] == "alive"
        assert states[f"http://127.0.0.1:{http_port}/missing"] == "dead"
        # .invalid TLD 保证 NXDOMAIN → dead; 沙箱网络策略下允许降级 unknown
        assert states["https://nonexistent.invalid.example"] in ("dead", "unknown")

    def test_liveness_counts_read_only(self, tmp_wiki):
        """liveness_counts 只读 frontmatter, 不发网络请求。"""
        tmp_wiki.import_bookmarks(_BOOKMARK_HTML.format(port=9))
        counts = liveness_counts(tmp_wiki)
        assert counts == {"total": 3, "alive": 0, "dead": 0, "unknown": 3}
