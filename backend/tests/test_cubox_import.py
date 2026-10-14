"""C2 (DEV-0195): cubox CLI 导出导入 + 本地目录导入测试。

覆盖:
- _cubox_env: PATH 注入 ~/.local/bin (同步异常根因修复)
- _check_cubox_cli: 增强 PATH 探测 / 无 cli 时 False
- import_cubox_cards: 新建/合并/无 url 跳过
- import_cubox_dir: 数组与 {cards} 两种形状 / 非 json 忽略 / 相对路径与不存在目录 ValueError
- import_cubox_dir (DEV-0327): 递归 *.md / 无 frontmatter 跳过 / 无来源 url 跳过 / 内联 tags 拆分 / json+md 混放
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
    _md_to_card,
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


def _md(
    path: Path,
    *,
    title: str,
    url: str | None = None,
    tags: str | None = None,
    body: str = "",
) -> None:
    """写一个 cubox 本地化卡片 md (frontmatter 形状仿 ``#书籍/Cubox`` 导出)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f'title: "{title}"']
    if url:
        lines.append(f'source_url: "{url}"')
    if tags is not None:
        lines.append(f"tags: {tags}")
    lines.append('created: "2026-05-09T21:54:03.474+0800"')
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")


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


class TestMdCard:
    """DEV-0327: cubox 本地化 md → 卡片反解 (无 DB 依赖)。"""

    def test_inline_tags_split_and_body(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        _md(f, title="X 文", url="https://example.com/x", tags="[RAG, 应用]", body="正文内容")
        card = _md_to_card(f)
        assert card is not None
        assert card["title"] == "X 文"
        assert card["url"] == "https://example.com/x"
        assert card["tags"] == ["RAG", "应用"]  # 内联非 JSON 数组需拆回 list
        assert card["description"] == "正文内容"
        assert card["create_time"] == "2026-05-09T21:54:03.474+0800"

    def test_cli_export_shape_uses_url(self, tmp_path: Path) -> None:
        """cubox-cli 导出形状: 用 ``url`` (非 ``source_url``) 也要识别。"""
        f = tmp_path / "cli.md"
        f.write_text(
            '---\ntitle: "CLI 文"\nurl: "https://example.com/cli"\n'
            'tags: []\ncreated: "2026-06-01T00:00:00+0800"\n---\n\n正文\n',
            encoding="utf-8",
        )
        card = _md_to_card(f)
        assert card is not None
        assert card["url"] == "https://example.com/cli"
        assert card["tags"] == []

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.md"
        f.write_text("# 标题\n正文", encoding="utf-8")
        assert _md_to_card(f) is None

    def test_no_url_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "no-url.md"
        _md(f, title="无来源")
        assert _md_to_card(f) is None


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

    def test_dir_import_md_recursive_and_skip(self, temp_db, tmp_path: Path) -> None:
        """md 递归子目录扫描; 无 frontmatter / 无来源 url 静默跳过。"""
        sub = tmp_path / "AI" / "LLM Wiki"
        _md(sub / "a.md", title="A 文", url="https://example.com/md-a",
            tags="[RAG, 应用, 知识管理]", body="正文 A")
        _md(sub / "no-url.md", title="无来源")
        (tmp_path / "index.md").write_text("# 索引\n无 frontmatter", encoding="utf-8")

        result = import_cubox_dir(str(tmp_path))
        assert result["md_files"] == 3   # 递归命中子目录
        assert result["md_cards"] == 1   # 仅 a.md 是卡片
        assert result["cards"] == 1
        assert result["new"] == 1
        assert result["imported"] == 1

    def test_dir_import_json_and_md_mixed(self, temp_db, tmp_path: Path) -> None:
        (tmp_path / "batch.json").write_text(json.dumps([_card("m1")]), encoding="utf-8")
        _md(tmp_path / "sub" / "c.md", title="C 文", url="https://example.com/md-c")

        result = import_cubox_dir(str(tmp_path))
        assert result["files"] == 1     # 顶层 json 文件数
        assert result["md_cards"] == 1
        assert result["cards"] == 2
        assert result["new"] == 2

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

    def test_import_dir_endpoint_returns_imported(self, client, tmp_path: Path) -> None:
        """DEV-0327: 响应含 imported 键 (前端 toast 依赖, 修「入库 0 条」误报)。"""
        _md(tmp_path / "sub" / "a.md", title="A", url="https://example.com/api-md")
        r = client.post("/api/knowledge/cubox/import-dir", json={"path": str(tmp_path)})
        assert r.status_code == 200
        body = r.json()
        assert body["imported"] == 1
        assert body["md_cards"] == 1
