"""S1-3 书签存活三态检测测试 — check_url 单测 (safe_urlopen 边界打桩) + sweep 集成。

三态契约 (docs/HOTSPOT_SECNEWS_INTEGRATION.md §7.1):
  alive   = HTTP < 400
  dead    = HTTP >= 400 / DNS 不存在 / 连接拒绝 / SSRF 拒收 (私网·环回)
  unknown = 超时等瞬态; check_url 永不抛异常。

Mimosa triage T1: 出站探测统一走 url_safety.safe_urlopen (环回/私网拒收)。
单测在 safe_urlopen 边界打桩驱动三态分类逻辑; 拦截语义另有专测
(test_blocked_private_ip_is_dead)。
"""
from __future__ import annotations

import urllib.error

import pytest

from backend.wiki_fs.liveness import (
    ALIVE_STATES,
    check_url,
    liveness_counts,
    sweep_liveness,
)

_BOOKMARK_HTML = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="http://example.test/ok">Alive Link</A>
<DT><A HREF="http://example.test/missing">Dead Link</A>
<DT><A HREF="https://nonexistent.invalid.example">Dns Dead</A>
</DL><p>"""


class _FakeResp:
    """最小 response: _probe 只读 status (getattr 兜底 getcode)。"""

    def __init__(self, status: int):
        self.status = status

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install_fake_urlopen(monkeypatch, *, status=200, http_error=None):
    """打桩 backend.utils.url_safety.safe_urlopen (_probe 函数级导入, 调用时解析)。"""
    calls: list[tuple[str, str]] = []

    def fake(url, *, method="GET", timeout=10.0, headers=None):
        calls.append((url, method))
        if http_error is not None and method == "HEAD":
            raise http_error(url, method)
        return _FakeResp(status)

    import backend.utils.url_safety as us

    monkeypatch.setattr(us, "safe_urlopen", fake)
    return calls


class TestCheckUrl:
    def test_alive_states_constant(self):
        assert ALIVE_STATES == ("alive", "dead", "unknown")

    def test_alive_200(self, monkeypatch):
        _install_fake_urlopen(monkeypatch, status=200)
        assert check_url("http://example.test/ok") == "alive"

    def test_head_405_falls_back_to_get(self, monkeypatch):
        """HEAD 被拒 (405/501) 时降级 GET 重试 → alive。"""
        calls = _install_fake_urlopen(
            monkeypatch,
            status=200,
            http_error=lambda url, method: urllib.error.HTTPError(
                url, 405, "Method Not Allowed", {}, None
            ),
        )
        assert check_url("http://example.test/ok") == "alive"
        assert [m for _, m in calls] == ["HEAD", "GET"]

    def test_dead_404(self, monkeypatch):
        _install_fake_urlopen(monkeypatch, status=404)
        assert check_url("http://example.test/missing") == "dead"

    def test_dead_dns_failure(self):
        assert check_url("https://nonexistent.invalid.example", timeout=3.0) == "dead"

    def test_blocked_private_ip_is_dead(self):
        """Mimosa triage T1 新语义: 环回/私网目标被 SSRF 防护拒收 → dead。"""
        assert check_url("http://127.0.0.1:9/ok") == "dead"

    def test_unknown_timeout_never_raises(self):
        """不可路由地址 → 连接挂起/拒绝; 无论哪种结果都必须收敛为合法三态且不抛。"""
        state = check_url("https://10.255.255.2/nope", timeout=1.0)
        assert state in ALIVE_STATES

    def test_empty_url_is_unknown(self):
        assert check_url("") == "unknown"


class TestSweepLiveness:
    @pytest.fixture
    def tmp_wiki(self, tmp_path):
        import os

        from backend.wiki_fs import WikiFs

        root = str(tmp_path / "wiki")
        os.makedirs(root, exist_ok=True)
        return WikiFs(root)

    @pytest.fixture
    def patched_sweep(self, monkeypatch):
        """按 URL 路由三态: /ok→200, /missing→404, invalid TLD→URL_ERROR。"""
        import backend.utils.url_safety as us

        def fake(url, *, method="GET", timeout=10.0, headers=None):
            if url.endswith("/ok"):
                return _FakeResp(200)
            if url.endswith("/missing"):
                return _FakeResp(404)
            raise us.UrlSafetyError("dns resolution failed")

        monkeypatch.setattr(us, "safe_urlopen", fake)

    def test_import_bookmarks_default_unknown(self, tmp_wiki):
        result = tmp_wiki.import_bookmarks(_BOOKMARK_HTML)
        assert result["added"] == 3
        for item_id in tmp_wiki.list_ids():
            fm = tmp_wiki.read_item(item_id)["fm"]
            assert fm["source"] == "bookmark-import"
            assert fm["alive"] == "unknown"
            assert "alive_checked_at" not in fm

    def test_sweep_writes_back_three_states(self, tmp_wiki, patched_sweep):
        tmp_wiki.import_bookmarks(_BOOKMARK_HTML)
        stats = sweep_liveness(tmp_wiki, workers=4, timeout=3.0)
        assert set(stats) == {"total", *ALIVE_STATES}
        assert stats["total"] == 3
        assert stats["alive"] == 1                    # /ok → 200
        assert stats["dead"] + stats["unknown"] == 2  # 404 + DNS 拒收分支

        states = {}
        for item_id in tmp_wiki.list_ids():
            fm = tmp_wiki.read_item(item_id)["fm"]
            states[fm["url"]] = fm["alive"]
            assert "alive_checked_at" in fm
        assert states["http://example.test/ok"] == "alive"
        assert states["http://example.test/missing"] == "dead"
        assert states["https://nonexistent.invalid.example"] in ("dead", "unknown")

    def test_liveness_counts_read_only(self, tmp_wiki):
        """liveness_counts 只读 frontmatter, 不发网络请求。"""
        tmp_wiki.import_bookmarks(_BOOKMARK_HTML)
        counts = liveness_counts(tmp_wiki)
        assert counts == {"total": 3, "alive": 0, "dead": 0, "unknown": 3}
