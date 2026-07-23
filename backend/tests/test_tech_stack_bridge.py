"""v1.7 Phase 2 — TechStack 桥接测试 (验收 4: FastAPI 文章 → 使用 FastAPI 的项目).

核心验收: FastAPI 漏洞文章能匹配到 tech_stack 包含 "fastapi" 的 cg_project.
"""
from __future__ import annotations

import pytest

from backend.repository.codegarden_repo import CodegardenProjectRepository
from backend.repository.db import close_db, init_db
from backend.repository.hotspot_repo import HotspotRepository
from backend.services.tech_stack_service import analyze_impact
from backend.config import config


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_tech_stack_bridge.db"
    monkeypatch.setattr(config, "db_path", test_db)
    close_db()
    init_db()
    yield test_db
    close_db()


def _make_project(name: str, tech_stack: list[str]) -> dict:
    """创建一个 cg_project (用最小必填字段, lifecycle_stage=development 未归档)."""
    repo = CodegardenProjectRepository()
    return repo.create(
        name=name,
        type="library",
        source_type="imported",
        lifecycle_stage="development",
        tech_stack=tech_stack,
    )


def _upsert_hotspot_direct(hotspot_id: str, title: str, summary: str, category: str) -> None:
    """直接 SQL 插入热点 (绕过 HotspotItem 必填字段, 仅写桥接所需列)."""
    from datetime import datetime, timezone
    from backend.repository.db import get_connection
    now = datetime.now(timezone.utc).isoformat()
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hotspot_id, title, summary, "test-source", f"https://example.com/{hotspot_id}",
            category, now, 50.0, now, 0, 80, "[]", "pending", now,
        ),
    )


# ---------------------------------------------------------------------------
# 验收 4: FastAPI 漏洞文章 → 匹配使用 FastAPI 的项目
# ---------------------------------------------------------------------------
class TestAnalyzeImpact:
    def test_fastapi_article_matches_fastapi_project(self, temp_db):
        """验收 4: FastAPI 漏洞文章匹配到使用 FastAPI 的项目."""
        # 1. 创建一篇 FastAPI 漏洞文章
        _upsert_hotspot_direct(
            "h-fastapi-vuln",
            "FastAPI 远程代码执行漏洞 CVE-2024-1234",
            "FastAPI 框架被发现存在远程代码执行漏洞, 影响所有 FastAPI 0.100 以下版本.",
            category="security",
        )
        # 2. 创建使用 FastAPI 的项目
        proj_match = _make_project("my-fastapi-app", ["fastapi", "react"])
        # 3. 创建不使用 FastAPI 的项目 (不应匹配)
        _make_project("flask-app", ["flask", "sqlalchemy"])

        # 4. 影响分析
        result = analyze_impact("h-fastapi-vuln")

        # 5. 断言: 匹配到使用 FastAPI 的项目, 且只有它
        assert result["article_id"] == "h-fastapi-vuln"
        # 提取到的标签应包含 fastapi (来自 tag_rules.json)
        tag_ids = {t["tag_id"] for t in result["tags"]}
        assert "fastapi" in tag_ids, f"expected fastapi in extracted tags, got {tag_ids}"
        assert "fastapi" in result["matched_tech"]

        project_ids = {p["id"] for p in result["projects"]}
        assert proj_match["id"] in project_ids, "FastAPI 项目应被匹配"
        assert len(result["projects"]) == 1, f"应只匹配 1 个项目, got {len(result['projects'])}"

    def test_no_matching_project_returns_empty(self, temp_db):
        """文章标签无对应项目时返回空列表."""
        _upsert_hotspot_direct(
            "h-langchain",
            "LangChain 提示注入攻击",
            "LangChain 框架的 prompt injection 风险分析.",
            category="security",
        )
        # 只有 FastAPI 项目, 不应匹配 LangChain 文章
        _make_project("api-server", ["fastapi"])

        result = analyze_impact("h-langchain")
        assert result["article_id"] == "h-langchain"
        # tags 应包含 langchain, 但没有项目使用 langchain
        tag_ids = {t["tag_id"] for t in result["tags"]}
        assert "langchain" in tag_ids
        assert result["projects"] == []

    def test_missing_article_returns_empty(self, temp_db):
        """不存在的 article_id 返回空结果 (不报错)."""
        result = analyze_impact("no-such-article")
        assert result["article_id"] == "no-such-article"
        assert result["tags"] == []
        assert result["projects"] == []
        assert result["matched_tech"] == []

    def test_archived_project_excluded(self, temp_db):
        """已归档项目不参与匹配."""
        _upsert_hotspot_direct(
            "h-fa",
            "FastAPI 安全更新",
            "FastAPI 修复了多个安全问题.",
            category="security",
        )
        # 创建后归档
        proj = _make_project("archived-fa", ["fastapi"])
        repo = CodegardenProjectRepository()
        repo.set_lifecycle(proj["id"], "archived")

        result = analyze_impact("h-fa")
        project_ids = {p["id"] for p in result["projects"]}
        assert proj["id"] not in project_ids, "已归档项目不应匹配"

    def test_multiple_tech_match_dedup(self, temp_db):
        """一篇文章提取多个标签, 项目匹配多个标签时去重."""
        _upsert_hotspot_direct(
            "h-multi",
            "FastAPI + LangChain 集成漏洞",
            "FastAPI 与 LangChain 集成时存在 prompt injection 风险, 涉及 CVE-2024-5678.",
            category="security",
        )
        # 一个项目同时使用 fastapi 和 langchain → 只匹配一次
        proj_both = _make_project("ai-backend", ["fastapi", "langchain"])
        _make_project("fa-only", ["fastapi"])

        result = analyze_impact("h-multi")
        project_ids = [p["id"] for p in result["projects"]]
        # proj_both 只出现一次
        assert project_ids.count(proj_both["id"]) == 1
        assert len(result["projects"]) == 2


# ---------------------------------------------------------------------------
# TechStackRepository CRUD (基础单元测试)
# ---------------------------------------------------------------------------
class TestTechStackRepository:
    def test_add_and_get(self, temp_db):
        from backend.repository.tech_stack_repo import TechStackRepository
        repo = TechStackRepository()
        repo.add("ts-fastapi", "FastAPI", "framework", 3, "web framework")
        got = repo.get("ts-fastapi")
        assert got is not None
        assert got["name"] == "FastAPI"
        assert got["category"] == "framework"
        assert got["proficiency"] == 3
        assert got["notes"] == "web framework"

    def test_list_by_category(self, temp_db):
        from backend.repository.tech_stack_repo import TechStackRepository
        repo = TechStackRepository()
        repo.add("ts-fastapi", "FastAPI", "framework")
        repo.add("ts-react", "React", "framework")
        repo.add("ts-python", "Python", "language")

        frameworks = repo.list(category="framework")
        assert len(frameworks) == 2
        languages = repo.list(category="language")
        assert len(languages) == 1

    def test_update(self, temp_db):
        from backend.repository.tech_stack_repo import TechStackRepository
        repo = TechStackRepository()
        repo.add("ts-1", "Original", "cat", 1)
        updated = repo.update("ts-1", name="Renamed", proficiency=4)
        assert updated["name"] == "Renamed"
        assert updated["proficiency"] == 4
        assert updated["category"] == "cat"  # 未传则保留

    def test_delete(self, temp_db):
        from backend.repository.tech_stack_repo import TechStackRepository
        repo = TechStackRepository()
        repo.add("ts-del", "ToDelete", "cat")
        assert repo.delete("ts-del") == 1
        assert repo.get("ts-del") is None
        assert repo.delete("ts-del") == 0  # 再删返回 0

    def test_find_by_name_case_insensitive(self, temp_db):
        from backend.repository.tech_stack_repo import TechStackRepository
        repo = TechStackRepository()
        repo.add("ts-fa", "FastAPI", "framework")
        assert repo.find_by_name("fastapi") is not None
        assert repo.find_by_name("FASTAPI") is not None
        assert repo.find_by_name("nonexistent") is None
