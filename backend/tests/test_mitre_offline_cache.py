"""v0.7 Batch ⑨ B9-4: MITRE ATT&CK 离线包 + 增量同步 tests."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _cache_dir(monkeypatch, tmp_path):
    """临时 cache 目录 + env 注入."""
    d = tmp_path / "mitre_cache"
    d.mkdir()
    monkeypatch.setenv("MITRE_CACHE_DIR", str(d))
    return d


def test_cache_dir_default():
    """未设 env 时走 backend/data/mitre/."""
    # 清 env
    import os

    from backend.security import mitre_attack
    old = os.environ.pop("MITRE_CACHE_DIR", None)
    try:
        d = mitre_attack.cache_dir()
        assert d.name == "mitre"
        assert "data" in str(d)
    finally:
        if old is not None:
            os.environ["MITRE_CACHE_DIR"] = old


def test_cache_dir_env_override(monkeypatch, tmp_path):
    from backend.security import mitre_attack
    monkeypatch.setenv("MITRE_CACHE_DIR", str(tmp_path / "custom"))
    assert mitre_attack.cache_dir() == tmp_path / "custom"


def test_cache_info_empty(_cache_dir):
    """无 cache 时 cache_info 返 bundle_exists=False."""
    from backend.security.mitre_attack import MitreAttackClient
    info = MitreAttackClient().cache_info()
    assert info["bundle_exists"] is False
    assert info["meta"] is None
    assert info["bundle_size_bytes"] == 0


def test_cache_info_after_write(_cache_dir):
    """手动写 cache + meta 后, cache_info 反映状态."""
    from backend.security import mitre_attack
    from backend.security.mitre_attack import MitreAttackClient

    mitre_attack.cache_bundle_path().write_text('{"objects":[]}', encoding="utf-8")
    mitre_attack.cache_meta_path().write_text(
        json.dumps({"last_modified": "Wed, 01 Jan 2026 00:00:00 GMT", "etag": '"abc"', "fetched_at": "2026-01-01T00:00:00Z", "size_bytes": 12}),
        encoding="utf-8",
    )
    info = MitreAttackClient().cache_info()
    assert info["bundle_exists"] is True
    assert info["bundle_size_bytes"] == len('{"objects":[]}')  # 14
    assert info["meta"]["last_modified"] == "Wed, 01 Jan 2026 00:00:00 GMT"
    assert info["meta"]["etag"] == '"abc"'


def test_sync_uses_cache_when_not_modified(_cache_dir):
    """HEAD 返 Last-Modified == cache meta → 跳过下载, 直接读 cache."""
    from backend.security import mitre_attack
    from backend.security.mitre_attack import MitreAttackClient

    # 预填 cache + meta
    cache_content = '{"objects":[]}'  # 空 bundle
    mitre_attack.cache_bundle_path().write_text(cache_content, encoding="utf-8")
    mtime = "Wed, 01 Jan 2026 00:00:00 GMT"
    mitre_attack.cache_meta_path().write_text(
        json.dumps({"last_modified": mtime, "etag": '"abc"', "fetched_at": "2026-01-01T00:00:00Z", "size_bytes": len(cache_content)}),
        encoding="utf-8",
    )

    # mock HEAD + GET: HEAD 返相同 mtime, GET 不应被调
    head_resp = MagicMock()
    head_resp.headers = {"Last-Modified": mtime, "ETag": '"abc"'}
    head_resp.__enter__ = MagicMock(return_value=head_resp)
    head_resp.__exit__ = MagicMock(return_value=False)

    download_called = []

    def fake_urlopen(req, timeout=None):
        method = req.get_method() if hasattr(req, "get_method") else getattr(req, "method", "GET")
        if method == "HEAD":
            return head_resp
        download_called.append(req.full_url)
        raise AssertionError("GET should not be called when cache fresh")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = MitreAttackClient().sync_to_db(clear=False, force=False)

    assert result["from_cache"] is True
    assert result["entities"] == 0
    assert result["edges"] == 0
    assert download_called == []


def test_sync_redownloads_when_modified(_cache_dir):
    """HEAD 返新 mtime → 重新下载 + 写 cache + 返回新数据."""
    from backend.security import mitre_attack
    from backend.security.mitre_attack import MitreAttackClient

    # 预填旧 cache
    old_mtime = "Wed, 01 Jan 2026 00:00:00 GMT"
    mitre_attack.cache_bundle_path().write_text('{"objects":[]}', encoding="utf-8")
    mitre_attack.cache_meta_path().write_text(
        json.dumps({"last_modified": old_mtime, "etag": '"old"', "fetched_at": "2026-01-01T00:00:00Z", "size_bytes": 12}),
        encoding="utf-8",
    )

    new_mtime = "Wed, 08 Jan 2026 00:00:00 GMT"
    new_bundle = json.dumps({"objects": [{"type": "tactic", "id": "x", "name": "test", "external_references": []}]})

    def make_resp(body, headers):
        r = MagicMock()
        r.headers = headers
        r.read = MagicMock(return_value=body.encode("utf-8") if isinstance(body, str) else body)
        r.__enter__ = MagicMock(return_value=r)
        r.__exit__ = MagicMock(return_value=False)
        return r

    # urllib Request.get_method() 返 'HEAD' / 'GET'; 检查 get_method() 而非 .method
    def fake_urlopen(req, timeout=None):
        method = req.get_method() if hasattr(req, "get_method") else getattr(req, "method", "GET")
        if method == "HEAD":
            return make_resp("", {"Last-Modified": new_mtime, "ETag": '"new"'})
        return make_resp(new_bundle, {"Last-Modified": new_mtime, "ETag": '"new"'})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = MitreAttackClient().sync_to_db(clear=False, force=False)

    assert result["from_cache"] is False
    assert result["new_modified"] == new_mtime
    assert json.loads(mitre_attack.cache_bundle_path().read_text(encoding="utf-8")) == json.loads(new_bundle)
    meta = json.loads(mitre_attack.cache_meta_path().read_text(encoding="utf-8"))
    assert meta["last_modified"] == new_mtime
    assert meta["etag"] == '"new"'


def test_sync_force_bypasses_etag(_cache_dir):
    """force=True 即使 cache fresh 也强制下载."""
    from backend.security import mitre_attack
    from backend.security.mitre_attack import MitreAttackClient

    mtime = "Wed, 01 Jan 2026 00:00:00 GMT"
    mitre_attack.cache_bundle_path().write_text('{"objects":[]}', encoding="utf-8")
    mitre_attack.cache_meta_path().write_text(
        json.dumps({"last_modified": mtime, "etag": '"abc"', "fetched_at": "2026-01-01T00:00:00Z", "size_bytes": 12}),
        encoding="utf-8",
    )

    get_called = []

    def make_resp(body, headers):
        r = MagicMock()
        r.headers = headers
        r.read = MagicMock(return_value=body.encode("utf-8") if isinstance(body, str) else body)
        r.__enter__ = MagicMock(return_value=r)
        r.__exit__ = MagicMock(return_value=False)
        return r

    def fake_urlopen(req, timeout=None):
        # urllib Request.method 是 property, 在真实代码中等价于 req.get_method()
        try:
            method = req.get_method()
        except AttributeError:
            method = getattr(req, "method", "GET")
        if method == "HEAD":
            return make_resp("", {"Last-Modified": mtime, "ETag": '"abc"'})
        get_called.append("called")
        return make_resp('{"objects":[]}', {"Last-Modified": mtime, "ETag": '"abc"'})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = MitreAttackClient().sync_to_db(clear=False, force=True)

    assert result["from_cache"] is False
    assert len(get_called) == 1


def test_sync_falls_back_to_stale_cache_on_network_error(_cache_dir):
    """网络失败 + 旧 cache 存在 → 兜底用旧 cache."""
    from backend.security import mitre_attack
    from backend.security.mitre_attack import MitreAttackClient

    mtime = "Wed, 01 Jan 2026 00:00:00 GMT"
    mitre_attack.cache_bundle_path().write_text('{"objects":[]}', encoding="utf-8")
    mitre_attack.cache_meta_path().write_text(
        json.dumps({"last_modified": mtime, "etag": '"abc"', "fetched_at": "2026-01-01T00:00:00Z", "size_bytes": 12}),
        encoding="utf-8",
    )

    def fake_urlopen(req, timeout=None):
        raise ConnectionError("network down")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = MitreAttackClient().sync_to_db(clear=False, force=False)

    # 兜底用旧 cache, 但 from_cache=True 标记这是 fallback
    assert result["from_cache"] is True
    assert result["entities"] == 0
