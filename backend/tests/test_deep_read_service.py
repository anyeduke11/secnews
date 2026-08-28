"""S4-2 DeepRead 4 节深度分析面板测试。

覆盖:
1. 表里有 + force=false → 不调 LLM, 直接返回 (cache 命中)
2. force=true → 调 LLM, 覆盖旧记录
3. LLM 返回空 → 抛 DeepReadError, 不写表
4. 4 节 JSON 正常解析 → sections 各 key 落地
5. JSON 解析失败 → fallback 到整段 summary
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


def _stub_hotspot():
    """HotspotRepository().get_by_id 返回值 stub。"""
    from types import SimpleNamespace
    return SimpleNamespace(
        id="h-001",
        title="Sample hotspot title",
        summary="This is a sample hotspot summary for deep read testing.",
        content="",
    )


def _stub_wiki():
    from types import SimpleNamespace
    return SimpleNamespace(
        item_id="sample.md",
        title="Sample wiki",
        content="Sample wiki content for testing.",
    )


def _seed_one_item(repo, entity_type: str, entity_id: str) -> None:
    """直接 upsert 一条 deep_reads 记录 (不调 LLM)。"""
    sections = {
        "summary": "预设摘要",
        "impact": "预设影响",
        "relations": "预设关联",
        "risks": "预设风险",
    }
    repo.upsert(
        entity_type=entity_type,
        entity_id=entity_id,
        content_md="## 摘要\n\n预设摘要\n\n## 影响\n\n预设影响\n",
        sections_json=json.dumps(sections, ensure_ascii=False),
        provider="preset",
        model="preset-model",
        tokens_in=10,
        tokens_out=20,
        cost_usd=0.0,
        latency_ms=1,
    )


# ── 1. 表里有 + force=false → 不调 LLM ───────────────────────


def test_run_cache_hit_does_not_call_llm(temp_db):
    """表里有且 force=False → 直接返回, generate() 不被调用。"""
    from backend.repository.deepread_repo import DeepReadRepository
    from backend.services.deep_read_service import DeepReadService

    repo = DeepReadRepository()
    _seed_one_item(repo, "hotspot", "h-cache-hit")

    with patch(
        "backend.services.deep_read_service._ai_hub_mod.llm_service"
    ) as mock_llm:
        mock_llm.generate = AsyncMock(return_value="")
        svc = DeepReadService()

        import asyncio
        item = asyncio.run(svc.run("hotspot", "h-cache-hit", force=False))

    assert item.entity_type == "hotspot"
    assert item.entity_id == "h-cache-hit"
    assert item.provider == "preset"
    assert item.sections["summary"] == "预设摘要"
    # generate 绝不被调用
    mock_llm.generate.assert_not_called()


# ── 2. force=true → 调 LLM + 覆盖 ────────────────────────────


def test_run_force_overrides_existing(temp_db):
    """force=True → 拉原文 + 调 LLM, 旧 sections 被新生成覆盖。"""
    from backend.repository.deepread_repo import DeepReadRepository
    from backend.services.deep_read_service import DeepReadService

    repo = DeepReadRepository()
    _seed_one_item(repo, "hotspot", "h-force")

    new_json = json.dumps({
        "summary": "新生成的摘要",
        "impact": "新生成的影响",
        "relations": "新生成的关联",
        "risks": "新生成的风险",
    }, ensure_ascii=False)

    with patch(
        "backend.services.deep_read_service._ai_hub_mod.llm_service"
    ) as mock_llm:
        mock_llm.generate = AsyncMock(return_value=new_json)
        # router 推荐 → 强制返回 ("openai", "gpt-4o-mini")
        mock_llm.resolve_provider_for_task.return_value = ("openai", "gpt-4o-mini")
        # _est_tokens 也要 stub (从 ai_hub 导入)
        mock_llm._est_tokens = lambda x: 42

        # 拉原文 stub — HotspotRepository.get_by_id 返回值
        with patch(
            "backend.repository.hotspot_repo.HotspotRepository.get_by_id",
            return_value=_stub_hotspot(),
        ):
            svc = DeepReadService()
            import asyncio
            item = asyncio.run(svc.run("hotspot", "h-force", force=True))

    assert item.sections["summary"] == "新生成的摘要"
    assert item.provider == "openai"
    assert item.model == "gpt-4o-mini"
    mock_llm.generate.assert_called_once()


# ── 3. LLM 返回空 → 抛 DeepReadError + 不写表 ────────────────


def test_run_llm_empty_raises_and_no_write(temp_db):
    """LLM 返回空串 → DeepReadError, deep_reads 表保持空。"""
    from backend.repository.deepread_repo import DeepReadRepository
    from backend.services.deep_read_service import DeepReadError, DeepReadService

    with patch(
        "backend.services.deep_read_service._ai_hub_mod.llm_service"
    ) as mock_llm:
        mock_llm.generate = AsyncMock(return_value="")
        mock_llm.resolve_provider_for_task.return_value = ("ollama", "qwen2.5:7b")

        with patch(
            "backend.repository.hotspot_repo.HotspotRepository.get_by_id",
            return_value=_stub_hotspot(),
        ):
            svc = DeepReadService()
            import asyncio
            with pytest.raises(DeepReadError):
                asyncio.run(svc.run("hotspot", "h-empty"))

    # 表里仍是空
    repo = DeepReadRepository()
    assert repo.get("hotspot", "h-empty") is None


# ── 4. 4 节 JSON 正常解析 → sections 各 key 落地 ──────────────


def test_parse_sections_normal_json():
    """合法 JSON 直接解析, 4 节都落地。"""
    from backend.services.deep_read_service import _parse_sections

    raw = json.dumps({
        "summary": "A",
        "impact": "B",
        "relations": "C",
        "risks": "D",
    }, ensure_ascii=False)
    out = _parse_sections(raw)
    assert out == {"summary": "A", "impact": "B", "relations": "C", "risks": "D"}


# ── 5. JSON 解析失败 → fallback 到整段 summary ────────────────


def test_parse_sections_fallback_to_whole_text():
    """非 JSON 输入 → summary=原文, 其余空 (不抛错)。"""
    from backend.services.deep_read_service import _parse_sections

    raw = "我只是一段分析文字, 不是 JSON, 应该被 fallback。"
    out = _parse_sections(raw)
    assert "我只是一段分析文字" in out["summary"]
    assert out["impact"] == ""
    assert out["relations"] == ""
    assert out["risks"] == ""