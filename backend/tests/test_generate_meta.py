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

    # v0.7.0 (795189ca) 起 v0.6_workstation_plan.md 归档至 docs/archived/，
    # 顶层 docs/*.md 活跃 draft 由 3 个收敛为 2 个。
    def test_two_known_drafts_are_registered_in_real_arch(self, gm):
        """2 个活跃 draft 规划必须都已登记（防回归）。"""
        arch_text = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        registry = gm.parse_architecture_registry(arch_text)
        for rel in (
            "docs/HOTSPOT_SECNEWS_INTEGRATION.md",
            "docs/SECNEWS_INTEGRATION_TASKS.md",
        ):
            assert rel in registry, (
                f"{rel} 应在 ARCHITECTURE.md §9.1 表格登记;实际找到的 docs 引用: {sorted(registry)}"
            )

    def test_two_known_drafts_have_frontmatter(self, gm):
        """v085 整理批后: 原 2 个 draft 已归档 — 归档件必须保留 draft frontmatter
        (出处可追溯), 且 docs/ 顶层不再有副本。"""
        docs_dir = REPO_ROOT / "docs"
        sweep = docs_dir / "archived" / "2026-09-09-sweep"
        for fname in (
            "HOTSPOT_SECNEWS_INTEGRATION.md",
            "SECNEWS_INTEGRATION_TASKS.md",
        ):
            assert not (docs_dir / fname).exists(), f"{fname} 应已归档, docs/ 顶层不应再有副本"
            archived = sweep / fname
            assert archived.exists(), f"{fname} 归档件缺失"
            assert gm.is_draft_planning_doc(archived), f"归档件 {fname} 丢失 'status: draft' frontmatter"

    def test_archived_plan_not_counted_as_draft(self, gm):
        """归档到 docs/archived/ 的规划不再被顶层扫描计入 draft。"""
        drafts = gm.collect_planning_drafts(REPO_ROOT / "docs")
        rels = {d["relpath"] for d in drafts}
        assert "docs/v0.6_workstation_plan.md" not in rels

    def test_drafts_only_outputs_two_known_drafts(self, gm, capsys):
        """v085 整理批后 docs/ 顶层 0 个活跃 draft → --drafts-only 应返回空表。

        本测试同时是绊线: 若未来有人在 docs/ 顶层新增规划 draft, 此处会失败,
        提醒同步登记 (原 2 个 draft 已随 2026-09-09 整理批归档)。"""
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
        assert rels == [], f"docs/ 顶层出现未登记的 draft: {rels}"


# ============================================================================
# 6. --fix 数字写回 (DEV-0242: 文档声称"自动维护"但实现缺失的漂移根治)
# ============================================================================

ACTUAL = {"jobs": 58, "collectors": 14, "routers": 90, "services": 153}

ARCH_SAMPLE = (
    "# 架构\n"
    "> jobs 57 头部散文 (非槽位, 不动)\n"
    "│ scheduler/ 57 jobs │\n"
    "13 个 BaseCollector\n"
    "api/ 89 router\n"
    "services/ 152 \n"
)


class TestFixDocNumbers:
    def test_rewrites_stale_slots_keeps_prose(self, gm, tmp_path: Path, monkeypatch):
        """漂移槽位写回反推值; 非槽位散文 (header `jobs 57`) 不被误改。"""
        arch = tmp_path / "ARCHITECTURE.md"
        arch.write_text(ARCH_SAMPLE, encoding="utf-8")
        monkeypatch.setattr(gm, "ARCHITECTURE", arch)
        changes = gm.fix_doc_numbers(ACTUAL)
        text = arch.read_text(encoding="utf-8")
        assert "scheduler/ 58 jobs" in text
        assert "14 个 BaseCollector" in text
        assert "api/ 90 router" in text
        assert "services/ 153" in text
        # 非槽位散文保持原样
        assert "> jobs 57 头部散文" in text
        assert any("jobs" in c for c in changes) and any("routers" in c for c in changes)
        assert any("collectors" in c for c in changes) and any("services" in c for c in changes)

    def test_idempotent_second_run_reports_nothing(self, gm, tmp_path: Path, monkeypatch):
        """幂等: 第二次 fix 无变更 — subn 匹配数不得虚报为变更数。"""
        arch = tmp_path / "ARCHITECTURE.md"
        arch.write_text(ARCH_SAMPLE, encoding="utf-8")
        monkeypatch.setattr(gm, "ARCHITECTURE", arch)
        gm.fix_doc_numbers(ACTUAL)
        assert gm.fix_doc_numbers(ACTUAL) == []

    def test_missing_file_returns_error_no_crash(self, gm, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(gm, "ARCHITECTURE", tmp_path / "nope.md")
        changes = gm.fix_doc_numbers(ACTUAL)
        assert len(changes) == 1 and changes[0].startswith("ERROR")

    def test_parse_and_fix_share_patterns(self, gm, tmp_path: Path, monkeypatch):
        """check 与 fix 必须认同一组槽位: fix 后 parse 读到的就是反推值。"""
        arch = tmp_path / "ARCHITECTURE.md"
        arch.write_text(ARCH_SAMPLE, encoding="utf-8")
        monkeypatch.setattr(gm, "ARCHITECTURE", arch)
        gm.fix_doc_numbers(ACTUAL)
        assert gm.parse_doc_numbers(arch.read_text(encoding="utf-8")) == ACTUAL


class TestFixAgentsNumbers:
    def test_rewrites_stale_kind_declarations(self, gm, tmp_path: Path, monkeypatch):
        doc = tmp_path / "AGENTS.md"
        doc.write_text(
            "架构数字由 AST 反推维护 (57 jobs / 14 collectors / 90 routers / 153 services)。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(gm, "AGENTS_DOC_SOURCES", (doc,))
        monkeypatch.setattr(gm, "ROOT", tmp_path)
        changes = gm.fix_agents_numbers(ACTUAL)
        assert changes == ["AGENTS.md: N <kind> 声明 → 反推值"]
        assert "58 jobs" in doc.read_text(encoding="utf-8")

    def test_idempotent_and_correct_values_untouched(self, gm, tmp_path: Path, monkeypatch):
        doc = tmp_path / "AGENTS.md"
        doc.write_text("58 jobs / 14 collectors\n", encoding="utf-8")
        monkeypatch.setattr(gm, "AGENTS_DOC_SOURCES", (doc,))
        monkeypatch.setattr(gm, "ROOT", tmp_path)
        assert gm.fix_agents_numbers(ACTUAL) == []
        assert doc.read_text(encoding="utf-8") == "58 jobs / 14 collectors\n"

    def test_claude_md_in_managed_sources(self, gm):
        """CLAUDE.md 必须在受管集合内 — 镜像文档数字漂移曾绕过 check (DEV-0242)。"""
        names = {p.name for p in gm.AGENTS_DOC_SOURCES}
        assert "CLAUDE.md" in names
