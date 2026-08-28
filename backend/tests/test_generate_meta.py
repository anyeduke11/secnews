"""Regression tests for scripts/generate_meta.py — 架构数字反推 + draft 规划登记校验。

覆盖三种行为：
1. 数字反推（jobs/collectors/routers/services）保持原契约
2. frontmatter 解析（status / target_version / related_code）
3. draft 文档必须被 ARCHITECTURE.md backtick 引用，否则 --check exit 1
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def gm():
    """Import generate_meta as a module; add scripts/ to sys.path once."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module("generate_meta")


# ============================================================================
# 1. frontmatter 解析
# ============================================================================


class TestParseFrontmatter:
    def test_empty_when_no_frontmatter(self, gm, tmp_path: Path):
        f = tmp_path / "plain.md"
        f.write_text("# Title only\n\nbody\n", encoding="utf-8")
        assert gm.parse_frontmatter(f) == {}

    def test_empty_when_frontmatter_unclosed(self, gm, tmp_path: Path):
        f = tmp_path / "broken.md"
        f.write_text("---\nstatus: draft\nno end marker\n", encoding="utf-8")
        assert gm.parse_frontmatter(f) == {}

    def test_single_string_value(self, gm, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text(
            "---\nstatus: draft\ntarget_version: v0.6\n---\n\n# body\n",
            encoding="utf-8",
        )
        fm = gm.parse_frontmatter(f)
        # 一律解析为列表（参见 parse_frontmatter 注释）
        assert fm["status"] == ["draft"]
        assert fm["target_version"] == ["v0.6"]

    def test_semicolon_list_values(self, gm, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text(
            "---\nstatus: draft\n"
            "related_code: backend/kl_pipeline/;backend/services/ai_hub.py\n"
            "depends_on: docs/v0.5_refactor_plan/README.md\n"
            "---\n\n# body\n",
            encoding="utf-8",
        )
        fm = gm.parse_frontmatter(f)
        assert fm["related_code"] == [
            "backend/kl_pipeline/",
            "backend/services/ai_hub.py",
        ]
        assert fm["depends_on"] == ["docs/v0.5_refactor_plan/README.md"]

    def test_missing_file_returns_empty(self, gm, tmp_path: Path):
        f = tmp_path / "does_not_exist.md"
        assert gm.parse_frontmatter(f) == {}


# ============================================================================
# 2. draft 判定
# ============================================================================


class TestIsDraftPlanningDoc:
    def test_draft_returns_true(self, gm, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("---\nstatus: draft\ntarget_version: v0.6\n---\n", encoding="utf-8")
        assert gm.is_draft_planning_doc(f) is True

    def test_active_returns_false(self, gm, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("---\nstatus: active\n---\n", encoding="utf-8")
        assert gm.is_draft_planning_doc(f) is False

    def test_no_frontmatter_returns_false(self, gm, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("# no fm\n", encoding="utf-8")
        assert gm.is_draft_planning_doc(f) is False


# ============================================================================
# 3. ARCHITECTURE.md 引用抽取
# ============================================================================


class TestParseArchitectureRegistry:
    def test_extracts_backticked_docs_refs(self, gm):
        text = (
            "Some intro.\n\n"
            "`docs/v0.5_refactor_plan/README.md` is one ref.\n\n"
            "And `docs/SECNEWS_INTEGRATION_TASKS.md` is another.\n"
        )
        assert gm.parse_architecture_registry(text) == {
            "docs/v0.5_refactor_plan/README.md",
            "docs/SECNEWS_INTEGRATION_TASKS.md",
        }

    def test_extracts_md_link_wrapped_refs(self, gm):
        text = "| [`docs/foo.md`](foo.md) | x |\n| [`docs/bar.md`](bar.md) | y |\n"
        assert gm.parse_architecture_registry(text) == {
            "docs/foo.md",
            "docs/bar.md",
        }

    def test_ignores_non_docs_paths(self, gm):
        text = "`backend/foo.py` and `scripts/x.py` should not match.\n"
        assert gm.parse_architecture_registry(text) == set()


# ============================================================================
# 4. End-to-end: check_drafts_registration
# ============================================================================


class TestCheckDraftsRegistration:
    def test_returns_missing_when_not_registered(self, gm):
        drafts = [
            {"relpath": "docs/NEW_DRAFT.md", "filename": "NEW_DRAFT.md"},
            {"relpath": "docs/OTHER.md", "filename": "OTHER.md"},
        ]
        arch_text = "# intro\n\n`docs/OTHER.md` is registered.\n`docs/EXISTING.md` is also there.\n"
        assert gm.check_drafts_registration(arch_text, drafts) == ["docs/NEW_DRAFT.md"]

    def test_returns_empty_when_all_registered(self, gm):
        drafts = [
            {"relpath": "docs/A.md", "filename": "A.md"},
            {"relpath": "docs/B.md", "filename": "B.md"},
        ]
        arch_text = "| `docs/A.md` | draft |\n| `docs/B.md` | draft |\n"
        assert gm.check_drafts_registration(arch_text, drafts) == []

    def test_returns_empty_when_no_drafts(self, gm):
        assert gm.check_drafts_registration("# no drafts here", []) == []


# ============================================================================
# 5. 真实仓库 self-check (sanity)：与代码 AST 数字及自身 frontmatter 同步
# ============================================================================


class TestRepoSelfCheck:
    """端到端：在真实仓库运行 --check，确认当前 ARCHITECTURE.md 与代码 + drafts 一致。

    这是 sanity test，不替代单元测试；若失败说明有人改了 ARCHITECTURE.md
    数字或忘了登记 draft。
    """

    def test_three_known_drafts_are_registered_in_real_arch(self, gm):
        """3 个 draft 规划必须都已登记（防回归）。"""
        arch_text = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        registry = gm.parse_architecture_registry(arch_text)
        for rel in (
            "docs/HOTSPOT_SECNEWS_INTEGRATION.md",
            "docs/SECNEWS_INTEGRATION_TASKS.md",
            "docs/v0.6_workstation_plan.md",
        ):
            assert rel in registry, (
                f"{rel} 应在 ARCHITECTURE.md §9.1 表格登记;实际找到的 docs 引用: {sorted(registry)}"
            )

    def test_three_known_drafts_have_frontmatter(self, gm):
        """3 个规划文档必须都含 status: draft frontmatter。"""
        docs_dir = REPO_ROOT / "docs"
        for fname in (
            "HOTSPOT_SECNEWS_INTEGRATION.md",
            "SECNEWS_INTEGRATION_TASKS.md",
            "v0.6_workstation_plan.md",
        ):
            path = docs_dir / fname
            assert gm.is_draft_planning_doc(path), f"{fname} 缺少 'status: draft' frontmatter"

    def test_drafts_only_outputs_three_known_drafts(self, gm, capsys):
        """--drafts-only 应正好列出 3 个已知 draft 文档（以 relpath 校验）。"""
        from generate_meta import main as gm_main

        old_argv = sys.argv
        try:
            sys.argv = ["generate_meta.py", "--drafts-only"]
            rc = gm_main()
        finally:
            sys.argv = old_argv
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        rels = sorted(d["relpath"] for d in data)
        assert rels == [
            "docs/HOTSPOT_SECNEWS_INTEGRATION.md",
            "docs/SECNEWS_INTEGRATION_TASKS.md",
            "docs/v0.6_workstation_plan.md",
        ]
