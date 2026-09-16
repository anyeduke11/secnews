"""C2 (DEV-0195): cubox CLI 导出导入 + 本地目录导入测试。

覆盖:
- _cubox_env: PATH 注入 ~/.local/bin (同步异常根因修复)
- _check_cubox_cli: 增强 PATH 探测 / 无 cli 时 False
- import_cubox_cards: 新建/合并/无 url 跳过
- import_cubox_dir: 数组与 {cards} 两种形状 / 非 json 忽略 / 相对路径与不存在目录 ValueError
- API: POST /api/knowledge/cubox/import-cards 与 /cubox/import-dir
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.knowledge_ops import router as knowledge_ops_router
from backend.services.cubox_sync import (
    _check_cubox_cli,
    _cubox_env,
    import_cubox_cards,
    import_cubox_dir,
)


@pytest.fixture
def client(temp_db) -> TestClient:
    from backend.api.cubox_import_api import router as cubox_import_router
    from backend.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(knowledge_ops_router)
    app.include_router(cubox_import_router)
    return TestClient(app)


def _card(cid: str, url: str | None = None) -> dict:
    if url is None:
        url = f"https://example.com/{cid}"
    return {
        "title": f"卡片 {cid}",
        "url": url,
        "description": f"{cid} 的正文内容",
        "tags": ["test"],
        "create_time": "2026-09-16T00:00:00+00:00",
    }


class TestCliPathResolution:
    def test_env_augments_path_with_home_local(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake_local_bin = tmp_path / ".local" / "bin"
        fake_local_bin.mkdir(parents=True)
        (fake_local_bin / "cubox-cli").write_text("#!/bin/sh\n")
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        env = _cubox_env()
        assert str(fake_local_bin) in env["PATH"].split(":")

    def test_check_cli_false_when_absent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        assert _check_cubox_cli() is False


class TestImportCards:
    def test_new_merge_and_skip(self, temp_db) -> None:
        # 预置一条已存在 md 的卡片 (合并路径)
        first = import_cubox_cards([_card("a")])
        assert first["new"] == 1 and first["merged"] == 0

        second = import_cubox_cards([_card("a"), _card("b"), _card("no-url", url="")])
        assert second["merged"] == 1  # a 已存在 → merge
        assert second["new"] == 1     # b 新建
        assert second["skipped"] == 1  # 无 url → skip

    def test_empty_cards(self, temp_db) -> None:
        assert import_cubox_cards([])["total"] == 0


class TestImportDir:
    def test_dir_import_two_shapes(self, temp_db, tmp_path: Path) -> None:
        (tmp_path / "batch1.json").write_text(
            json.dumps([_card("d1"), _card("d2")]), encoding="utf-8"
        )
        (tmp_path / "batch2.json").write_text(
            json.dumps({"cards": [_card("d3")]}), encoding="utf-8"
        )
        (tmp_path / "notes.txt").write_text("not json", encoding="utf-8")
        (tmp_path / "broken.json").write_text("{oops", encoding="utf-8")

        result = import_cubox_dir(str(tmp_path))
        assert result["files"] == 2          # batch1 + batch2; broken 记 error
        assert result["files_total"] == 3    # 2 json + broken.json; txt 忽略
        assert result["cards"] == 3
        assert result["new"] == 3
        assert len(result["errors"]) == 1 and "broken.json" in result["errors"][0]

    def test_relative_path_rejected(self, temp_db) -> None:
        with pytest.raises(ValueError, match="绝对路径"):
            import_cubox_dir("relative/dir")

    def test_missing_dir_rejected(self, temp_db, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="目录不存在"):
            import_cubox_dir(str(tmp_path / "nope"))


class TestImportAPI:
    def test_import_cards_endpoint(self, client) -> None:
        r = client.post("/api/knowledge/cubox/import-cards", json={"cards": [_card("api1")]})
        assert r.status_code == 200
        assert r.json()["imported"] == 1

    def test_import_cards_bad_body(self, client) -> None:
        r = client.post("/api/knowledge/cubox/import-cards", json={"cards": "not-a-list"})
        assert r.status_code in (400, 422)

    def test_import_dir_endpoint_bad_path(self, client) -> None:
        r = client.post("/api/knowledge/cubox/import-dir", json={"path": "relative/dir"})
        assert r.status_code == 400
