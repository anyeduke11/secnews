"""lifecycle 值域收敛测试 (KL 管线治理 T2)。

覆盖 scripts/fix_lifecycle_values.py 的核心契约:
  - dry-run 默认: 不传 --apply 绝不写盘
  - --apply 落盘: 只改 lifecycle 行, 其余 frontmatter 与正文字节不动
  - 幂等: 二次 apply 零改写
  - 大小写 / 引号变体均命中; 合法值 (kl:publish / kl:deduped) 不动
以及 backend/wiki_fs/contract.get_lifecycle 的读路径兜底 (generate/signal
→ kl:publish), 防外部工具再写旧值。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")  # repo root (scripts 为 namespace package, 先例 test_c01)

flv = importlib.import_module("scripts.fix_lifecycle_values")

from backend.wiki_fs.contract import get_lifecycle


def _make_md(path: Path, lifecycle_value: str, body: str = "正文 body\n") -> None:
    path.write_text(
        f"---\nid: x\ntitle: T\nlifecycle: {lifecycle_value}\ntags:\n"
        f"  - a\n---\n\n# Title\n{body}",
        encoding="utf-8",
    )


@pytest.fixture
def wiki_root(tmp_path, monkeypatch):
    """临时 items 目录 + 把脚本 REPO_ROOT 指到 tmp_path (隔离备份目录)。"""
    root = tmp_path / "items"
    root.mkdir()
    monkeypatch.setattr(flv, "REPO_ROOT", tmp_path)
    return root


class TestRewriteFrontmatter:
    def test_legacy_values_rewritten_with_mainstream_quoting(self):
        """generate / signal (含引号与大小写变体) → "kl:publish" (主流带双引号)。"""
        for old in ('generate', '"generate"', "'generate'", 'GENERATE',
                    'signal', '"signal"', 'Signal'):
            data = f"---\nlifecycle: {old}\n---\n\nbody".encode()
            new, n = flv.rewrite_frontmatter(data)
            assert n == 1, old
            assert b'lifecycle: "kl:publish"' in new

    def test_non_legacy_values_untouched(self):
        """kl:* 与 kl:deduped 是合法值域, 不得被改写。"""
        for ok in ('"kl:publish"', '"kl:deduped"', "kl:raw", "kl:refine"):
            data = f"---\nlifecycle: {ok}\n---\n\nbody".encode()
            assert flv.rewrite_frontmatter(data) == (data, 0), ok

    def test_body_and_other_fm_bytes_untouched(self):
        """字节级外科式改写: 其余 frontmatter 与正文一字节不动。"""
        body = "正文 with 中文 + emoji 🛡\nsecond line\n".encode()
        data = (b'---\nid: x\ntitle: "\xe6\xb5\x8b\xe8\xaf\x95"\n'
                b"lifecycle: generate\ntags:\n  - a\n---\n\n" + body)
        new, n = flv.rewrite_frontmatter(data)
        assert n == 1
        assert b"lifecycle: generate" not in new
        assert body in new
        assert b'title: "\xe6\xb5\x8b\xe8\xaf\x95"' in new

    def test_survives_undecodable_body(self):
        """utf-8 解码失败的文件 (坏字节在正文) 也能字节级迁移 frontmatter。"""
        data = (b"---\nlifecycle: signal\n---\n\nbroken \x91 body")
        new, n = flv.rewrite_frontmatter(data)
        assert n == 1
        assert b'lifecycle: "kl:publish"' in new
        assert b"\x91" in new  # 正文坏字节原样保留 (编码修复是另一件事)

    def test_no_frontmatter_noop(self):
        assert flv.rewrite_frontmatter(b"no fm here") == (b"no fm here", 0)


class TestCli:
    def test_dry_run_default_writes_nothing(self, wiki_root):
        _make_md(wiki_root / "a.md", "generate")
        before = (wiki_root / "a.md").read_bytes()

        assert flv.main(["--root", str(wiki_root)]) == 0  # 缺省即 dry-run

        assert (wiki_root / "a.md").read_bytes() == before

    def test_apply_rewrites_and_is_idempotent(self, wiki_root):
        _make_md(wiki_root / "a.md", '"generate"')
        _make_md(wiki_root / "b.md", "signal")
        _make_md(wiki_root / "ok.md", '"kl:publish"')

        assert flv.main(["--root", str(wiki_root), "--apply"]) == 0
        assert (wiki_root / "a.md").read_text(encoding="utf-8").splitlines()[3] \
            == 'lifecycle: "kl:publish"'
        assert (wiki_root / "b.md").read_text(encoding="utf-8").splitlines()[3] \
            == 'lifecycle: "kl:publish"'
        # 其余字段/正文不动
        assert "正文 body" in (wiki_root / "a.md").read_text(encoding="utf-8")

        # 幂等: 二次 apply 零改写
        assert flv.main(["--root", str(wiki_root), "--apply"]) == 0
        assert (wiki_root / "a.md").read_text(encoding="utf-8").splitlines()[3] \
            == 'lifecycle: "kl:publish"'


class TestGetLifecycleAlias:
    def test_legacy_values_read_as_publish(self):
        """读路径兜底: 外部工具再写 generate/signal 也读作 kl:publish。"""
        assert get_lifecycle({"lifecycle": "generate"}) == "kl:publish"
        assert get_lifecycle({"lifecycle": "signal"}) == "kl:publish"
        assert get_lifecycle({"lifecycle": '"kl:publish"'}) == '"kl:publish"'  # 不越权

    def test_existing_contract_unchanged(self):
        assert get_lifecycle({"lifecycle": "kl:link"}) == "kl:link"
        assert get_lifecycle({}) == "kl:raw"
        assert get_lifecycle({"kl_stage": "kl:refine"}) == "kl:refine"
