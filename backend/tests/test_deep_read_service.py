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


def _stub_knowledge():
    """KnowledgeRepo().get_item 返回值 stub (P4-1 knowledge 分支)。"""
    from types import SimpleNamespace
    return SimpleNamespace(
        id="ki-001",
        title="Sample knowledge",
        topic="Sample knowledge topic text.",
        domain="security",
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


# ── 2b. knowledge 分支 (DEV-0298: P4-1 检索锚点桥接) ─────────


def test_run_knowledge_entity_type_supported(temp_db):
    """entity_type=knowledge (knowledge_items.id) → 正常拉原文 + LLM 生成。

    旧版仅支持 hotspot/wiki — P4-1 统一检索给 knowledge 结果生成
    /deep/knowledge/:id 锚点后, 此分支缺失导致 'unsupported entity_type'。
    """
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import DeepReadService

    defs = deep_read_sections("security")
    new_json = json.dumps(
        {d["key"]: f"知识解读-{d['title']}" for d in defs}, ensure_ascii=False,
    )

    with patch(
        "backend.services.deep_read_service._ai_hub_mod.llm_service"
    ) as mock_llm:
        mock_llm.generate = AsyncMock(return_value=new_json)
        mock_llm.resolve_provider_for_task.return_value = ("openai", "gpt-4o-mini")
        mock_llm._est_tokens = lambda x: 42

        with patch(
            "backend.repository.knowledge_repo.KnowledgeRepo.get_item",
            return_value=_stub_knowledge(),
        ):
            svc = DeepReadService()
            import asyncio
            item = asyncio.run(svc.run("knowledge", "ki-001", force=True))

    assert item.sections[defs[0]["key"]] == f"知识解读-{defs[0]['title']}"
    assert item.entity_type == "knowledge"
    mock_llm.generate.assert_called_once()


def test_fetch_source_knowledge_not_found_raises():
    """knowledge id 不存在 → DeepReadError (非 unsupported)。"""
    import pytest as _pytest

    from backend.repository.knowledge_repo import KnowledgeRepo
    from backend.services.deep_read_service import DeepReadError, _fetch_source

    with patch.object(KnowledgeRepo, "get_item", return_value=None):
        with _pytest.raises(DeepReadError, match="knowledge item not found"):
            _fetch_source("knowledge", "missing-id")


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
    """合法 JSON 直接解析, 按传入的分类节集合逐键落地 (v3 走 _parse_sections_v3)。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections_v3

    defs = deep_read_sections("security")
    raw = json.dumps(
        {d["key"]: f"内容-{d['key']}" for d in defs}, ensure_ascii=False,
    )
    out, _fw, _hl = _parse_sections_v3(raw, "security")
    assert set(out) == {d["key"] for d in defs}
    assert out[defs[0]["key"]] == f"内容-{defs[0]['key']}"


def test_parse_sections_extra_keys_are_dropped():
    """LLM 多吐的键被丢弃, 缺的键补空 —— 不能让脏键流到前端渲染。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections_v3

    defs = deep_read_sections("finance")  # DEV-0183: bid profile 已随标讯下线移除
    raw = json.dumps(
        {**{d["key"]: "x" for d in defs[:-1]}, "bonus_hallucinated": "y"},
        ensure_ascii=False,
    )
    out, _fw, _hl = _parse_sections_v3(raw, "finance")
    assert set(out) == {d["key"] for d in defs}
    assert "bonus_hallucinated" not in out
    assert out[defs[-1]["key"]] == ""


# ── 5. JSON 解析失败 → fallback 到整段落首节 ────────────────


def test_parse_sections_fallback_to_whole_text():
    """非 JSON 输入 → 原文落进首节, 其余空 (不抛错)。"""
    from backend.services.ai_hub.prompts import deep_read_sections
    from backend.services.deep_read_service import _parse_sections_v3

    defs = deep_read_sections("security")
    first = defs[0]["key"]
    raw = "我只是一段分析文字, 不是 JSON, 应该被 fallback。"
    out, _fw, _hl = _parse_sections_v3(raw, "security")
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
    fin_keys = [s["key"] for s in deep_read_sections("finance")]
    assert sec_keys != fin_keys
    assert "impact_ioc" in sec_keys and "penalty" in fin_keys
    # 跨类别可比的固定骨架
    assert sec_keys[0] == fin_keys[0] == "key_takeaways"
    assert sec_keys[-2:] == fin_keys[-2:] == ["next_actions", "evidence_gaps"]

    p_sec = _build_deep_read_prompt("security", {"title": "T"}, "正文")
    p_fin = _build_deep_read_prompt("finance", {"title": "T"}, "正文")
    assert "应急响应工程师" in p_sec
    assert '"impact_ioc"' in p_sec and '"penalty"' in p_fin


def test_unknown_category_falls_back_to_general():
    """未识别分类回落通用视角而不是抛错, 保证深度阅读总能出结果。"""
    from backend.services.ai_hub.prompts import (
        _build_deep_read_prompt,
        deep_read_sections,
    )

    unknown = [s["key"] for s in deep_read_sections("not-a-real-category")]
    general = [s["key"] for s in deep_read_sections(None)]
    assert unknown == general
    assert "what" in unknown
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
    for cat in ("finance", "startup", "github", "tech", "ai"):
        assert all(
            s["tone"] != "red" for s in deep_read_sections(cat)
        ), f"{cat} 视角不该占用 red (red 专属漏洞告警)"


def test_framework_auto_selected_by_category():
    """v2 框架机制: 解读框架必须随文章类型自动适配 —
    情报研判类走 What/Why/How, 选型/商业类走轻量 SWOT, 监管类走 5W;
    lens 提示语注入 prompt, 引导模型按框架组织各节而非散写。"""
    from backend.services.ai_hub.prompts import (
        _build_deep_read_prompt,
        deep_read_framework_lens,
        deep_read_sections,
    )

    def keys(cat: str) -> list[str]:
        return [s["key"] for s in deep_read_sections(cat)]

    # what/why/how 框架: 资讯研判类 (security/tech/ai/ai_security/通用兜底)
    for cat in ("security", "tech", "ai", "ai_security", None):
        ks = keys(cat or "not-a-real-category")
        assert {"what", "why_matters", "how_react"} <= set(ks), f"{cat} 应含 what_why_how 框架节"

    # swot 框架: 选型与商业判断类
    for cat in ("github", "startup"):
        assert {"strengths_opp", "weak_threat"} <= set(keys(cat)), f"{cat} 应含 swot_lite 框架节"

    # 5W 框架: 监管合规类
    assert {"who_when", "scope_bound"} <= set(keys("finance"))

    # lens 注入: prompt 必须携带框架组织指令
    assert "What/Why/How" in _build_deep_read_prompt("security", {"title": "T"}, "正文")
    assert "SWOT" in _build_deep_read_prompt("github", {"title": "T"}, "正文")
    assert "5W" in _build_deep_read_prompt("finance", {"title": "T"}, "正文")
    assert deep_read_framework_lens("security"), "lens 不得为空"


def test_framework_config_integrity():
    """配置完整性防呆: 所有 profile 声明的框架必须存在于框架库;
    组合后的分节键不得重复 (框架节与领域节撞键会让 JSON schema 静默丢节);
    单分类分节数 ≤9 防止 prompt 膨胀稀释每节质量。"""
    from backend.services.ai_hub.prompts import (
        _FRAMEWORKS,
        _GENERAL_PROFILE,
        DEEP_READ_PROFILES,
        deep_read_sections,
    )

    all_profiles: dict[str, dict] = {**DEEP_READ_PROFILES, "general": _GENERAL_PROFILE}
    for cat, profile in all_profiles.items():
        for f in profile.get("frameworks", ()):
            assert f in _FRAMEWORKS, f"{cat} 声明了未知框架 {f}"
        ks = [s["key"] for s in deep_read_sections(cat)]
        assert len(ks) == len(set(ks)), f"{cat} 分节键重复: {ks}"
        assert len(ks) <= 9, f"{cat} 分节数 {len(ks)} 超预算 (≤9)"


def test_framework_sections_never_red_and_skeleton_invariant():
    """框架节不占用 red (red 专属漏洞语境的三色锁对 v2 新节同样生效);
    全部分类固定骨架不变: 首节要点速读, 尾两节我的动作+存疑与未证实 —
    前端折叠顺序与跨类对比都依赖该不变式。"""
    from backend.services.ai_hub.prompts import DEEP_READ_PROFILES, deep_read_sections

    fw_keys = {"what", "why_matters", "how_react", "strengths_opp", "weak_threat", "who_when", "scope_bound"}
    for cat in (*DEEP_READ_PROFILES, None):
        secs = deep_read_sections(cat or "not-a-real-category")
        for s in secs:
            if s["key"] in fw_keys:
                assert s["tone"] != "red", f"{cat}/{s['key']} 框架节不得染红"
        assert secs[0]["key"] == "key_takeaways", f"{cat} 首节漂移"
        assert [s["key"] for s in secs[-2:]] == ["next_actions", "evidence_gaps"], f"{cat} 尾节漂移"


def test_prompt_schema_matches_sections_exactly():
    """prompt 内嵌默认分节示例的键必须与 deep_read_sections 逐键一致 —
    service 用同一函数解析, 示例与分节定义漂移 = 分节键错乱/丢节。
    同时验证 v3 的「框架菜单」段与 framework/headline 契约键在每个分类的
    prompt 中都存在。"""
    import json as _json

    from backend.services.ai_hub.prompts import (
        _build_deep_read_prompt,
        deep_read_sections,
    )

    for cat in ("security", "github", "finance", None):
        prompt = _build_deep_read_prompt(cat, {"title": "T"}, "正文")
        schema_block = prompt.split("默认分节示例 (所选框架不同时节键相应替换):\n", 1)[1].split("\n\n来源元信息")[0]
        assert set(_json.loads(schema_block)) == {s["key"] for s in deep_read_sections(cat)}, f"{cat} schema 漂移"
        assert "框架菜单" in prompt, f"{cat} prompt 缺框架菜单段"
        assert '"framework"' in prompt and '"headline"' in prompt, f"{cat} prompt 缺 v3 契约键"
        assert "安全从业者视角" in prompt, f"{cat} prompt 缺 next_actions 视角约束"


def test_profile_version_bumped_to_v3():
    """模板结构变更加 profile_version 锚点: 落库记录据此识别模板代际,
    旧 v1/v2 报告渲染不回归, 新报告可审计。"""
    from backend.services.ai_hub.prompts import DEEP_READ_PROFILE_VERSION

    assert DEEP_READ_PROFILE_VERSION == "v3"


def test_build_prompt_pinned_framework():
    """v3.1 用户显式指定框架: prompt 菜单收敛到该框架并强制选用;
    非法框架值回落自动模式 (菜单全开) 而非报错。"""
    from backend.services.ai_hub.prompts import _build_deep_read_prompt

    p = _build_deep_read_prompt("security", {"title": "T"}, "正文", framework="swot_lite")
    assert '已由用户指定为 "swot_lite"' in p, "pinned 模式必须声明用户指定"
    assert "框架菜单" not in p, "pinned 模式不再开放全菜单"
    assert "SWOT" in p

    p_auto = _build_deep_read_prompt("security", {"title": "T"}, "正文")
    assert "框架菜单" in p_auto, "自动模式保留全菜单"
    p_ghost = _build_deep_read_prompt("security", {"title": "T"}, "正文", framework="ghost_fw")
    assert "框架菜单" in p_ghost, "非法框架回落自动模式"


def test_parse_sections_v3_framework_self_select():
    """v3 框架自选解析: LLM 返回 framework 键 → 节集合按所选框架组装;
    headline 透传; 非法 framework 回落 profile 默认 (v2 行为)。"""
    from backend.services.deep_read_service import _parse_sections_v3

    # security 默认 what_why_how; LLM 改选 swot_lite → 节键应含 strengths_opp
    raw = '{"framework": "swot_lite", "headline": "测试标题", "key_takeaways": "K", "strengths_opp": "S", "weak_threat": "W", "impact_ioc": "I", "next_actions": "N", "evidence_gaps": "E"}'
    sections, fw, headline = _parse_sections_v3(raw, "security")
    assert fw == "swot_lite"
    assert headline == "测试标题"
    assert sections["strengths_opp"] == "S" and sections["weak_threat"] == "W"
    assert "impact_ioc" in sections, "security 领域专属节须保留"
    assert "what" not in sections, "未选框架的节不得出现"

    # 非法 framework → 回落默认 (security = what_why_how)
    raw2 = '{"framework": "ghost", "key_takeaways": "K", "what": "A", "why_matters": "B", "how_react": "C", "impact_ioc": "I", "next_actions": "N", "evidence_gaps": "E"}'
    sections2, fw2, hl2 = _parse_sections_v3(raw2, "security")
    assert fw2 == "ghost"  # 原样透传 (envelope 如实记录 LLM 声明)
    assert "what" in sections2, "非法框架回落默认框架节集合"
    assert hl2 == ""

    # 非 JSON → 整段塞首节 fallback, framework/headline 空
    sections3, fw3, hl3 = _parse_sections_v3("纯文本垃圾输出", "security")
    assert fw3 == "" and hl3 == ""
    assert sections3["key_takeaways"].startswith("纯文本")


def test_framework_lens_tolerates_unknown_framework(monkeypatch):
    """防御性: profile 引用不存在的框架键时 lens 跳过该框架返回空串,
    不抛错阻断深读 (与未知分类回落通用视角同一韧性原则)。"""
    from backend.services.ai_hub import prompts

    monkeypatch.setitem(
        prompts.DEEP_READ_PROFILES,
        "tech",
        {**prompts.DEEP_READ_PROFILES["tech"], "frameworks": ("ghost_framework",)},
    )
    assert prompts.deep_read_framework_lens("tech") == ""
    # 分节装配同样跳过: 只剩头尾与领域节, 不炸
    ks = [s["key"] for s in prompts.deep_read_sections("tech")]
    assert ks[0] == "key_takeaways" and ks[-2:] == ["next_actions", "evidence_gaps"]