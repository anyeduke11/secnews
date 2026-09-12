"""P0-F 路径穿越回归测试 — KL items API + WikiFs 路径拼装白名单。

背景 (docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md P0-F):
  GET/PUT /api/kl/items/{item_id} 直传 wiki_fs.read_item/write_item,
  ``self._items_dir / f"{item_id}.md"`` 无过滤, URL 编码 ``%2e%2e%2f``
  可任意读/覆写 .md。修复: store.py `_safe_md_path` 白名单 + resolve
  前缀双校验, API 层 ValueError → 400。

注: TestClient 会在路由前把 %2f 解码成 ``/`` 并归一化点段, 因此含段分隔符
的穿越 id 经 HTTP 层会 404 (路由不匹配); 能到达 handler 的单段穿越 id
(``..`` 等) 必须得 400。含 ``/`` 的 id 直接以函数调用断言 (确定性覆盖)。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.kl_pipeline_api import (
    UpdateItemRequest,
    get_item,
    update_item,
)
from backend.api.kl_pipeline_api import (
    router as kl_router,
)
from backend.wiki_fs.store import WikiFs, _safe_md_path


# ---------------------------------------------------------------------------
# 单元层: _safe_md_path / WikiFs 直调
# ---------------------------------------------------------------------------
class TestSafeMdPath:
    def test_rejects_traversal_segments(self, tmp_path):
        for bad in ("../evil", "a/../b", "..", ".", "a/b", "a\\b", "", "a\x00b", "%2e%2e"):
            with pytest.raises(ValueError):
                _safe_md_path(tmp_path, bad)

    def test_accepts_normal_ids(self, tmp_path):
        for good in ("abc", "item-1234", "A.b_c-d9", "0start"):
            p = _safe_md_path(tmp_path, good)
            assert p.parent == tmp_path.resolve()
            assert p.name == f"{good}.md"


class TestWikiFsItemGuards:
    def test_read_item_rejects_traversal(self, tmp_path):
        fs = WikiFs(str(tmp_path))
        with pytest.raises(ValueError):
            fs.read_item("../../etc/passwd")

    def test_write_item_rejects_traversal(self, tmp_path):
        fs = WikiFs(str(tmp_path))
        with pytest.raises(ValueError):
            fs.write_item("../escape", {"fm": {}, "body": "x"})
        # 确认没有把文件写到 items/ 之外
        assert not (tmp_path / "escape.md").exists()

    def test_normal_roundtrip_unaffected(self, tmp_path):
        fs = WikiFs(str(tmp_path))
        fs.write_item("hello-1", {"fm": {"title": "T"}, "body": "b"})
        doc = fs.read_item("hello-1")
        assert doc is not None
        assert doc["fm"]["title"] == "T"
        assert doc["body"] == "b"


# ---------------------------------------------------------------------------
# API 层: GET/PUT /api/kl/items/{item_id}
# ---------------------------------------------------------------------------
@pytest.fixture()
def kl_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """最小 app: 仅挂 kl router, wiki_fs 指向 tmp_path (隔离生产 knowledge/)。"""
    fs = WikiFs(str(tmp_path))
    fs.write_item("normal-item", {"fm": {"title": "OK"}, "body": "fine"})

    import backend.kl_pipeline.runtime as runtime

    monkeypatch.setattr(runtime, "get_production_wiki_fs", lambda: fs)

    app = FastAPI()
    app.include_router(kl_router)
    return TestClient(app, raise_server_exceptions=False)


class TestKlItemsApiTraversal:
    def test_get_encoded_dot_segment_400(self, kl_client):
        """单段穿越 id (``..``, URL 编码保持单段) → handler 转 400。"""
        r = kl_client.get("/api/kl/items/%2e%2e")
        assert r.status_code == 400

    def test_get_dotfile_id_400(self, kl_client):
        r = kl_client.get("/api/kl/items/.hidden")
        assert r.status_code == 400

    def test_put_encoded_dot_segment_400(self, kl_client):
        r = kl_client.put("/api/kl/items/%2e%2e", json={"body": "pwned"})
        assert r.status_code == 400

    def test_get_slash_traversal_400_direct_call(self, kl_client):
        """含段分隔符的穿越 id: 直接调 endpoint 函数断言 400 转换。"""
        with pytest.raises(HTTPException) as ei:
            asyncio.run(get_item("../../etc/passwd"))
        assert ei.value.status_code == 400

    def test_put_slash_traversal_400_direct_call(self, kl_client):
        with pytest.raises(HTTPException) as ei:
            asyncio.run(update_item("a/../../etc/passwd", UpdateItemRequest(body="x")))
        assert ei.value.status_code == 400

    def test_normal_id_read_write_unaffected(self, kl_client):
        r = kl_client.get("/api/kl/items/normal-item")
        assert r.status_code == 200
        assert r.json()["fm"]["title"] == "OK"

        r = kl_client.put(
            "/api/kl/items/normal-item", json={"body": "updated"}
        )
        assert r.status_code == 200
        assert kl_client.get("/api/kl/items/normal-item").json()["body"] == "updated"

    def test_missing_item_still_404(self, kl_client):
        r = kl_client.get("/api/kl/items/no-such-item")
        assert r.status_code == 404
