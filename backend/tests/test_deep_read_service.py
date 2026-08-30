"""DeepRead 深度分析面板测试 (分类型动态分节)。

覆盖:
1. 表里有 + force=false → 不调 LLM, 直接返回 (cache 命中)
2. force=true → 调 LLM, 覆盖旧记录; 且必须显式声明 task="deep_read"
3. LLM 返回空 → 抛 DeepReadError, 不写表
4. 分节 JSON 正常解析 → 按该分类的节集合落地
5. JSON 解析失败 → fallback 到整段落首节
6. 不同 category → 不同分节集合与不同 persona (本次需求的核心)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


def _stub_hotspot(category: str | None = None):
    """HotspotRepository().get_by_id 返回值 stub。

    ``category=None`` → 服务回落通用视角, 保持历史用例语义不变。
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        id="h-001",
        title="Sample hotspot title",
        summary="This is a sample hotspot summary for deep read testing.",
        content="",
        category=category,
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
    """force=True → 拉原文 + 显式按 deep_read 任务调 LLM, 旧记录被覆盖。"""
    from backend.repository.deepread_repo import DeepReadRepository
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import DeepReadService

    repo = DeepReadRepository()
    _seed_one_item(repo, "hotspot", "h-force")

    # category=None → 通用视角的分节键
    defs = deep_read_sections(None)
    new_json = json.dumps(
        {d["key"]: f"新生成-{d['title']}" for d in defs}, ensure_ascii=False,
    )

    with patch(
        "backend.services.deep_read_service._ai_hub_mod.llm_service"
    ) as mock_llm:
        mock_llm.generate = AsyncMock(return_value=new_json)
        # router 推荐 → 强制返回 ("openai", "gpt-4o-mini")
        mock_llm.resolve_provider_for_task.return_value = ("openai", "gpt-4o-mini")
        # _est_tokens 也要 stub (从 ai_hub 导入)
        mock_llm._est_tokens = lambda x: 42

        with patch(
            "backend.repository.hotspot_repo.HotspotRepository.get_by_id",
            return_value=_stub_hotspot(),
        ):
            svc = DeepReadService()
            import asyncio
            item = asyncio.run(svc.run("hotspot", "h-force", force=True))

    # 修复核心: 必须显式声明 deep_read 任务, 否则被写死成 "summary" → FLASH 档
    # → t3_chunk_summary → 未运行的 ollama, 深度阅读因此从未成功过一次。
    kwargs = mock_llm.generate.call_args.kwargs
    assert kwargs.get("task") == "deep_read", "未声明 task → 会被路由到未运行的 provider"
    assert kwargs.get("max_tokens"), "深度阅读必须显式给输出上限 (TaskOverride 不下发)"

    # 旧 sections 被新内容覆盖
    for d in defs:
        assert item.sections[d["key"]] == f"新生成-{d['title']}"
    # 落库形状可被前端动态渲染: 有序 + 带标题与色调
    assert [s["key"] for s in item.section_defs] == [d["key"] for d in defs]
    assert item.section_defs[0]["title"] == defs[0]["title"]
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


# ── 4. 分节 JSON 正常解析 → 该分类的节集合落地 ──────────────


def test_parse_sections_normal_json():
    """合法 JSON 直接解析, 按传入的分类节集合逐键落地。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections

    defs = deep_read_sections("security")
    raw = json.dumps(
        {d["key"]: f"内容-{d['key']}" for d in defs}, ensure_ascii=False,
    )
    out = _parse_sections(raw, defs)
    assert set(out) == {d["key"] for d in defs}
    assert out[defs[0]["key"]] == f"内容-{defs[0]['key']}"


def test_parse_sections_extra_keys_are_dropped():
    """LLM 多吐的键被丢弃, 缺的键补空 —— 不能让脏键流到前端渲染。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections

    defs = deep_read_sections("bid")
    raw = json.dumps(
        {**{d["key"]: "x" for d in defs[:-1]}, "bonus_hallucinated": "y"},
        ensure_ascii=False,
    )
    out = _parse_sections(raw, defs)
    assert set(out) == {d["key"] for d in defs}
    assert "bonus_hallucinated" not in out
    assert out[defs[-1]["key"]] == ""


# ── 5. JSON 解析失败 → fallback 到整段落首节 ────────────────


def test_parse_sections_fallback_to_whole_text():
    """非 JSON 输入 → 原文落进首节, 其余空 (不抛错)。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections

    defs = deep_read_sections("security")
    first = defs[0]["key"]
    raw = "我只是一段分析文字, 不是 JSON, 应该被 fallback。"
    out = _parse_sections(raw, defs)
    assert "我只是一段分析文字" in out[first]
    assert all(out[d["key"]] == "" for d in defs[1:])


# ── 6. 分类型视角 (本次需求核心) ────────────────────────────


def test_different_category_different_sections():
    """不同文章分类必须给出不同分节集合与不同 persona。"""
    from backend.services.ai_hub.prompts import (
        _build_deep_read_prompt,
        deep_read_sections,
    )

    sec_keys = [s["key"] for s in deep_read_sections("security")]
    bid_keys = [s["key"] for s in deep_read_sections("bid")]
    assert sec_keys != bid_keys
    assert "impact_ioc" in sec_keys and "qualification" in bid_keys
    # 跨类别可比的固定骨架
    assert sec_keys[0] == bid_keys[0] == "key_takeaways"
    assert sec_keys[-2:] == bid_keys[-2:] == ["next_actions", "evidence_gaps"]

    p_sec = _build_deep_read_prompt("security", {"title": "T"}, "正文")
    p_bid = _build_deep_read_prompt("bid", {"title": "T"}, "正文")
    assert "应急响应工程师" in p_sec
    assert "投标负责人" in p_bid
    assert '"impact_ioc"' in p_sec and '"qualification"' in p_bid


def test_unknown_category_falls_back_to_general():
    """未识别分类回落通用视角而不是抛错, 保证深度阅读总能出结果。"""
    from backend.services.ai_hub.prompts import (
        _build_deep_read_prompt,
        deep_read_sections,
    )

    unknown = [s["key"] for s in deep_read_sections("not-a-real-category")]
    general = [s["key"] for s in deep_read_sections(None)]
    assert unknown == general
    assert "context" in unknown
    prompt = _build_deep_read_prompt("not-a-real-category", {}, "正文")
    assert "研判员" in prompt


def test_security_profile_marks_vuln_section_red_only():
    """语义三色锁: red 只用于漏洞/攻击面语境, 其余节不得染红。"""
    from backend.services.ai_hub.prompts import deep_read_sections

    tones = {s["key"]: s["tone"] for s in deep_read_sections("security")}
    assert tones["impact_ioc"] == "red"
    assert tones["next_actions"] == "mint"
    assert tones["evidence_gaps"] == "amber"
    # 非漏洞类不应出现 red
    for cat in ("bid", "finance", "startup", "github", "tech", "ai"):
        assert all(
            s["tone"] != "red" for s in deep_read_sections(cat)
        ), f"{cat} 视角不该占用 red (red 专属漏洞告警)"