"""ai_hub/prompts.py — Prompt 构造 + LLM 响应解析 (v0.7+ 拆分自 gateway.py)。

原 ``backend/services/ai_hub/gateway.py`` (406 行) 拆为:
- ``gateway.py``   — ``LLMService`` 类骨架 (构造 / config / provider 解析 / 4 任务循环 / provider 调用)
- ``prompts.py``   (本文件) — 无状态工具 (prompt 构造 + 响应解析 + 缓存 key) + 常量
- ``__init__.py``  — re-export 维持向后兼容

所有函数都是纯函数/无状态, 可独立测试. LLMService 在主路径中通过:
    from .prompts import _build_score_prompt, _parse_score
调用, 内部 cross-import 避免循环.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# v0.8.6 P0-6 (审计 E3): DEFAULT_SCORE(5.0) 假成功删除 — 模型拒绝/超时/
# 响应无数字一律走失败路径 (ScoreParseError / gateway 返回 None), 不缓存
# 不编造分数不记 ok=True。

# 成本估算 (USD per 1M tokens) — 近似值
COST_PER_1M_TOKENS: dict[str, float] = {
    "gpt-4o-mini": 0.15,
    "gpt-4o": 5.0,
    "qwen-turbo": 0.3,
    "qwen-plus": 0.8,
    "claude-3-5-haiku-20241022": 0.8,
    "claude-3-5-sonnet-20241022": 3.0,
    # Ollama 本地模型零成本
}


def _estimate_cost(model: str, tokens: int) -> float:
    """估算一次 LLM 调用的 USD 成本."""
    if tokens <= 0:
        return 0.0
    rate = COST_PER_1M_TOKENS.get(model, 0.5)  # 默认 $0.5/1M
    return (tokens / 1_000_000) * rate


def _make_cache_key(prefix: str, content: str) -> str:
    """生成缓存 key: {prefix}:{sha256(content)[:16]}."""
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


def _build_score_prompt(content: str) -> str:
    """构建评分 prompt."""
    MAX_LEN = 2000
    truncated = content[:MAX_LEN]
    return (
        "Rate the following article on a scale of 0.0 to 10.0 based on its "
        "relevance to AI and cybersecurity. Consider: technical depth, novelty, "
        "practical applicability. Return ONLY a number between 0 and 10.\n\n"
        f"Article:\n{truncated}"
    )


def _build_summary_prompt(text: str) -> str:
    """构建摘要 prompt."""
    MAX_LEN = 4000
    truncated = text[:MAX_LEN]
    return (
        "Summarize the following text in 2-3 sentences. "
        "Focus on key technical points and actionable insights.\n\n"
        f"{truncated}"
    )


class ScoreParseError(ValueError):
    """LLM 响应中解析不出评分 — v0.8.6 P0-6 (审计 E3)。

    模型拒绝回答 / 超时截断 / 返回无数字文本均属此类; 调用方必须把它
    当作**失败**处理 (换 provider 重试或显式 unknown), 不得回落默认分。
    """


def _parse_score(raw: str) -> float:
    """从 LLM 响应中解析评分; 解析失败抛 :class:`ScoreParseError`。"""
    match = re.search(r"(\d+(?:\.\d+)?)", (raw or "").strip())
    if not match:
        raise ScoreParseError(f"no numeric score in response: {raw[:120]!r}")
    val = float(match.group(1))
    return max(0.0, min(10.0, val))


def _parse_entity_list(raw: str) -> list[str]:
    """从 LLM 响应中解析实体列表."""
    # 尝试 JSON 解析
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(e) for e in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    # 尝试行解析
    entities = []
    for line in raw.strip().split("\n"):
        line = line.strip().strip("- ").strip('"').strip("'")
        if line and not line.startswith("{"):
            entities.append(line)
    return entities[:20]  # 最多 20 个实体


# 兼容: 旧 gateway.py 内部 _build_score_prompt 也拼了 extract_entities prompt (行 208-211),
# 此处作为 _build_extract_entities_prompt 单独暴露, 避免每个任务循环里都写 4 行字面量
def _build_extract_entities_prompt(content: str) -> str:
    """构建实体提取 prompt."""
    return (
        "Extract named entities (person/company/technology/product) "
        f"from the following text. Return as a JSON list of strings:\n\n{content}"
    )


# ── DeepRead 分类型视角 (v0.7) ─────────────────────────────────
# 替代历史上写死在 deep_read_service.py 的"资深安全研究员 + 必须列 CVE/actor"
# —— 那套证据要求只对漏洞类成立, 对招标/创投/金融监管类文章会诱导模型编造。
# tone 只允许 mint / amber / red: 哨兵终端语义三色锁, red 专属漏洞告警语境。

DEEP_READ_PROFILE_VERSION = "v3"

_HEAD_SECTION = {"key": "key_takeaways", "title": "要点速读", "tone": "mint"}
_TAIL_SECTIONS = (
    {"key": "next_actions", "title": "我的动作", "tone": "mint"},
    {"key": "evidence_gaps", "title": "存疑与未证实", "tone": "amber"},
)

# 通用证据约束: 每条判断都要能对应原文, 否则进 evidence_gaps 而不是硬编。
_EVIDENCE_RULE = "每条判断须能对应原文片段; 无法对应的写进 evidence_gaps, 不要编造。"

# ── 分析框架库 (v2): 按文章类型自动选用的解读框架 ─────────────
# 框架 = 一组有组织视角的分节 + lens 提示语; profile 声明适用的框架,
# 与领域专属节组合 (语义重叠的通用节被框架节吸收, 领域独特节保留)。
_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "what_why_how": {
        "lens": "What/Why/How 认知框架 — what 只写事实与定义 (是什么), why 只写影响与动因 (为什么现在重要), how 只写行动与应对 (该怎么做)",
        "sections": (
            {"key": "what", "title": "这是什么", "tone": "mint"},
            {"key": "why_matters", "title": "为什么重要", "tone": "amber"},
            {"key": "how_react", "title": "如何应对", "tone": "mint"},
        ),
    },
    "swot_lite": {
        "lens": "轻量 SWOT 框架 — strengths_opp 只写机会与优势面, weak_threat 只写短板与威胁面, 两条都要落到「对我的决策意味着什么」",
        "sections": (
            {"key": "strengths_opp", "title": "机会与优势", "tone": "mint"},
            {"key": "weak_threat", "title": "短板与威胁", "tone": "amber"},
        ),
    },
    "five_w": {
        "lens": "5W 要素框架 — who_when 回答谁发布/何时生效/约束谁, scope_bound 回答适用范围与边界条件, 禁止把范围外主体写进来",
        "sections": (
            {"key": "who_when", "title": "主体与时点", "tone": "mint"},
            {"key": "scope_bound", "title": "范围与约束", "tone": "amber"},
        ),
    },
}

DEEP_READ_PROFILES: dict[str, dict[str, Any]] = {
    # CVE 漏洞条目 (DEV-0300): NVD 回源事实 + 奇安信 TI 漏洞通告同构分节
    "cve": {
        "persona": (
            "你是一名漏洞情报分析师, 按 CERT 风险通告的规范把 NVD 结构化事实"
            "整理成中文漏洞总结 — 只陈述事实里有的内容, 影响版本/CVSS/状态"
            "逐项核对, 不外推事实之外的影响面或时间线"
        ),
        "frameworks": ("what_why_how",),
        "extra_sections": (
            {"key": "cve_info", "title": "漏洞信息", "tone": "amber"},
            {"key": "threat_assessment", "title": "威胁评估", "tone": "red"},
            {"key": "remediation", "title": "处置建议", "tone": "mint"},
        ),
        "budget": 8000,
        "evidence": (
            "CVSS 分数/向量、厂商与受影响产品、公开与更新时间必须与事实原文"
            "逐字一致; 处置建议只写事实中可推导的动作 (升级方向/参考链接),"
            "无补丁信息时明说「NVD 未收录补丁信息」。英文描述须译为中文但"
            "不得增删事实。利用条件写进 why_matters, 缓解动作写进 how_react。"
        ),
    },
    "security": {
        "persona": "你是一名安全应急响应工程师（蓝队值班），需要在几分钟内判断这条情报要不要现在就动手",
        "frameworks": ("what_why_how",),
        "extra_sections": (
            {"key": "impact_ioc", "title": "影响面与指标", "tone": "red"},
        ),
        "budget": 10000,
        "evidence": "尽量给出可核对的编号/受影响版本/组件名与具体缓解动作（补丁版本、配置项、检测规则）。利用条件写进 why_matters, 处置动作写进 how_react。",
    },
    "ai_security": {
        "persona": "你是一名 AI 安全研究员，关注模型与 Agent 系统的攻击面和可落地的加固手段",
        "frameworks": ("what_why_how",),
        "extra_sections": (
            {"key": "attack_surface", "title": "攻击面与绕过", "tone": "red"},
            {"key": "detection", "title": "监测信号", "tone": "amber"},
        ),
        "budget": 10000,
        "evidence": "区分「论文/厂商自述」与「独立复现」；缓解与加固手段写进 how_react, 可监测信号单列。",
    },
    "ai": {
        "persona": "你是一名 AI 平台负责人，判断这项能力对自己的产品是可用、可替代还是无关",
        "frameworks": ("what_why_how",),
        "extra_sections": (
            {"key": "capability_boundary", "title": "能力边界", "tone": "mint"},
        ),
        "budget": 8000,
        "evidence": "基准分数须注明评测方与条件；区分宣传口径与可验证结果。成本与替代方案写进 how_react。",
    },
    "finance": {
        "persona": "你是一名金融机构合规负责人 / CISO，只关心这条监管信息约束了谁、何时生效、违反的后果",
        "frameworks": ("five_w",),
        "extra_sections": (
            {"key": "penalty", "title": "罚则与追责", "tone": "amber"},
        ),
        "budget": 8000,
        "evidence": "禁止推测监管意图；只写原文出现的发文机关、条款、日期与罚则。监管要点并入 who_when, 义务与时限并入 scope_bound。",
    },
    "github": {
        "persona": "你是一名开源选型工程师，判断这个项目能不能进自己的技术栈、替换成本多大",
        "frameworks": ("swot_lite",),
        "extra_sections": (
            {"key": "license_risk", "title": "许可与合规", "tone": "amber"},
        ),
        "budget": 6000,
        "evidence": "区分 README 自述与实际能力；许可证结论须给出具体协议名与条款影响。定位与接入成本分别并入优势/短板两节。",
    },
    "startup": {
        "persona": "你是一名独立开发者 / 一人公司经营者，从别人的融资与失败里找可复制的做法与要避的坑",
        "frameworks": ("swot_lite",),
        "extra_sections": (
            {"key": "biz_signal", "title": "商业信号", "tone": "mint"},
        ),
        "budget": 6000,
        "evidence": "融资金额/轮次/投资方只写原文出现的；不要外推估值与赛道趋势。可复制做法写进 strengths_opp, 踩坑写进 weak_threat。",
    },
    "tech": {
        "persona": "你是一名 IT 架构师，梳理事实并判断这条技术动态对自己既有系统的实际影响",
        "frameworks": ("what_why_how",),
        "extra_sections": (
            {"key": "system_impact", "title": "对既有系统影响", "tone": "amber"},
        ),
        "budget": 6000,
        "evidence": "把「已发布 / 已宣布 / 传闻」分开陈述，不混为既成事实。后续看点写进 how_react。",
    },
}

# 未识别分类的兜底视角（不抛错，保证深度阅读总能出结果）
_GENERAL_PROFILE: dict[str, Any] = {
    "persona": "你是一名安全资讯研判员，为这条内容做结构化摘要与要点提炼",
    "frameworks": ("what_why_how",),
    "extra_sections": (),
    "budget": 8000,
    "evidence": _EVIDENCE_RULE,
}


def deep_read_profile_for(category: str | None) -> dict[str, Any]:
    """按文章分类取视角; 未知分类回落通用视角而不是抛错。"""
    return DEEP_READ_PROFILES.get(str(category or ""), _GENERAL_PROFILE)


def deep_read_framework_lens(category: str | None) -> str:
    """该分类所选框架的 lens 提示语 (多框架以「；」连接), 注入 prompt 约束各节写法。"""
    profile = deep_read_profile_for(category)
    lenses = [_FRAMEWORKS[f]["lens"] for f in profile.get("frameworks", ()) if f in _FRAMEWORKS]
    return "；".join(lenses)


def deep_read_sections(category: str | None, framework: str | None = None) -> list[dict[str, str]]:
    """该分类的有序分节定义: 要点速读 + 框架节 + 领域专属节 + 我的动作 + 存疑与未证实。

    v3: ``framework`` 可显式指定 (LLM 自选框架的返回值); None/非法值回落
    profile 默认声明的框架集合 —— 调用方解析 LLM 响应时先取 framework 键
    再用本函数取节定义, 两处必须同源。
    """
    profile = deep_read_profile_for(category)
    frameworks = profile.get("frameworks", ())
    if framework is not None and framework in _FRAMEWORKS:
        frameworks = (framework,)
    fw_sections: list[dict[str, str]] = []
    for f in frameworks:
        fw = _FRAMEWORKS.get(f)
        if fw:
            fw_sections.extend(fw["sections"])
    return [_HEAD_SECTION, *fw_sections, *profile["extra_sections"], *_TAIL_SECTIONS]


def _framework_menu(default_fw: tuple[str, ...]) -> str:
    """v3 框架菜单: 全部可选框架的键与节定义, 供 LLM 按内容自选。"""
    lines = []
    for name, fw in _FRAMEWORKS.items():
        secs = "、".join(f"{s['key']}({s['title']})" for s in fw["sections"])
        mark = " ← 默认推荐" if name in default_fw else ""
        lines.append(f"- {name}: {secs}{mark} — {fw['lens'].split(' — ')[0]}")
    return "\n".join(lines)


def _build_deep_read_prompt(
    category: str | None,
    entity_meta: dict[str, str],
    content: str,
    framework: str | None = None,
) -> str:
    """构建分类型深度解读 prompt (v3 框架自选 / 用户指定)。

    - ``framework`` 空/None/非法 → LLM 从框架菜单按内容自选 1 个 (默认推荐
      profile 声明的), 首键 ``framework`` 声明所选; 解析端用
      ``deep_read_sections(category, framework)`` 同源取节定义。
    - ``framework`` 合法 → 用户显式指定: prompt 菜单只保留该框架, 强制选用。
    - ``headline``: 一句话解读标题 (≤40 字, 概括这条资讯的核心判断)。
    - 字数按语义: 要点速读 100~250 字完整总结, 其余节 60~150 字按语义需要。
    """
    profile = deep_read_profile_for(category)
    default_fw = tuple(f for f in profile.get("frameworks", ()) if f in _FRAMEWORKS)
    pinned = framework if framework in _FRAMEWORKS else None
    schema = json.dumps(
        {s["key"]: "<本节内容, markdown>" for s in deep_read_sections(category)},
        ensure_ascii=False,
        indent=2,
    )
    budget = int(profile["budget"])
    meta_lines = "".join(
        f"[{k}] {v}\n" for k, v in entity_meta.items() if v and k != "entity_type"
    )
    if pinned:
        fw_rule = (
            f"2. 首键 \"framework\": 已由用户指定为 \"{pinned}\", 原样返回该值。\n"
            f"3. 次键 \"headline\": 一句话解读标题, ≤40 字, 给出核心判断而非复述标题。\n"
            "4. 只返回该框架对应的节键 (加该分类专属节与头尾节), 每节 markdown"
            " (可用列表/粗体), 不得返回其他框架的节键。\n"
        )
        menu = f"用户已指定框架: {pinned} — {_FRAMEWORKS[pinned]['lens'].split(' — ')[0]}"
    else:
        fw_rule = (
            "2. 首键 \"framework\": 从下方框架菜单中选 1 个最契合本文内容的框架键"
            f" (默认推荐: {'、'.join(default_fw) or 'what_why_how'}; 内容明显更适合其他框架时可改选)。\n"
            "3. 次键 \"headline\": 一句话解读标题, ≤40 字, 给出核心判断而非复述标题。\n"
            "4. 然后只返回所选框架对应的节键 (加该分类专属节与头尾节), 每节 markdown"
            " (可用列表/粗体), 不得返回未选框架的节键。\n"
        )
        menu = f"框架菜单:\n{_framework_menu(default_fw)}"
    return (
        f"{profile['persona']}。请分析下面这条资讯, 生成结构化深度解读。\n\n"
        "严格要求:\n"
        "1. 必须返回合法 JSON, 不要套外层 ```json 围栏。\n"
        f"{fw_rule}"
        "5. 字数按语义需要, 禁止注水与复述原文: key_takeaways 100~250 字完整总结;"
        " 其余节 60~150 字, 信息密度优先。\n"
        f"6. 证据约束: {profile['evidence']} {_EVIDENCE_RULE}\n"
        "7. next_actions 必须站在安全从业者视角给可落地动作 (检测/加固/评估/跟踪,"
        " 注明优先级), 不写泛泛的\"持续关注\"。\n\n"
        f"{menu}\n\n"
        f"默认分节示例 (所选框架不同时节键相应替换):\n{schema}\n\n"
        f"来源元信息:\n{meta_lines or '(无)'}\n\n"
        f"待分析内容 (最多 {budget} 字符):\n{content[:budget]}"
    )


# ---------------------------------------------------------------------------
# T11 SK-02 cve-impact-brief 专用 prompt — 有证据的判断 (judgment) 生成
# 区别于 deep_read (面向阅读者): 这里面向"判断 + 依据 + 未知"的
# 结构化输出, 直接喂 judgment_service.create_with_dsh → evidence_refs.
# ---------------------------------------------------------------------------

CVE_IMPACT_BRIEF_SCHEMA_V1 = {
    "claim_type": "finding|assessment|recommendation|warning|hypothesis",
    "claim": "<核心断言, Markdown, ≤ 10KB>",
    "conditions": "<适用条件, Markdown, ≤ 500 字符>",
    "confidence": "low|medium|high|proved",
    "evidence_refs": [
        {
            "material_id": "MAT-XXX",
            "hash": "sha256 与 material.content_hash 一致",
            "quote": "≤ 500 字符原文片段, 直接引自 evidence",
        }
    ],
    "counter_evidence_refs": [],
    "unknowns": [
        "<未知项字符串, baseline §5 硬约束: 缺资产/版本/受影响范围时必填>"
    ],
}


def build_cve_impact_brief_prompt(
    *,
    cve_id: str,
    subject_name: str,
    evidence_materials: list[dict[str, Any]],
) -> str:
    """构造 SK-02 cve-impact-brief 的 dsh prompt.

    Parameters
    ----------
    cve_id:
        例 "CVE-2026-31337" — LLM 围绕此 ID 输出影响判断.
    subject_name:
        例 "某 SSL VPN 网关" — 判断目标.
    evidence_materials:
        已收集的资料列表, 每条 {id, title, content_hash, url?, summary?}.
        LLM 须用 material_id + content_hash 引用, 不可编造.

    Returns
    -------
    完整 prompt 字符串, 喂给 ai_hub.generate_text.

    纪律
    ----
    - 每条 evidence_refs.hash 必须等于 material.content_hash (服务层校验, 错就 422)
    - evidence 不足 → unknowns 必填 (baseline §5 硬约束)
    - claim ≤ 10KB (services 层校验, 超长 422)
    - 不允许"未支持 claim" 走 publish (evidence_refs 至少 1)
    """
    materials_block = "\n\n".join(
        f"### material_id={m.get('id', '?')}\n"
        f"title: {m.get('title', '(no title)')}\n"
        f"content_hash: {m.get('content_hash', '?')}\n"
        f"summary: {m.get('summary', '(none)')[:300]}"
        for m in evidence_materials
    )
    schema_str = json.dumps(CVE_IMPACT_BRIEF_SCHEMA_V1, ensure_ascii=False, indent=2)
    return (
        f"你是一名安全应急响应工程师 (蓝队值班).\n"
        f"判断目标: **{cve_id}** 是否影响 **{subject_name}**.\n\n"
        f"## 已收集证据 (materials)\n\n"
        f"{materials_block or '(无 materials — 这是缺证据场景, 必须在 unknowns 列出未知项)'}\n\n"
        f"## 输出要求 (严格 JSON, 不允许任何 prose 包裹)\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"## 纪律\n"
        f"1. evidence_refs 至少 1 条; 若无可用 materials, 把 evidence_refs 留空数组, unknowns 必填 (≥ 1)\n"
        f"2. 每条 evidence_refs.hash 必须等于 material.content_hash; 找不到原文引用的不要瞎写 quote\n"
        f"3. claim 长度 ≤ 10000 字符; 超长会被服务层 422 拒收\n"
        f"4. confidence: proved 须有可复现实验/PoC; high 有 1 条以上高质量证据; medium 缺 PoC; low 仅经验推测\n"
        f"5. claim_type: finding=可核查事实; assessment=综合判断; recommendation=处置建议; warning=风险提示; hypothesis=待证假设\n"
        f"6. unknowns 缺失时不允许 publish (baseline §5 硬约束)\n"
        f"{_EVIDENCE_RULE}\n"
    )


def parse_cve_impact_brief_response(raw: str) -> dict[str, Any]:
    """解析 dsh 返回的 JSON, 容错包裹 (首尾 ```json ... ``` / 前置 prose / 单引号键).

    Raises
    ------
    ValueError
        解析失败 (缺字段 / 类型错 / JSON 坏).
    """
    if not raw or not raw.strip():
        raise ValueError("empty response from dsh")
    s = raw.strip()
    # 1) 剥 ```json ... ``` 包裹
    if "```" in s:
        for fence in ("```json", "```JSON", "```"):
            idx = s.find(fence)
            if idx >= 0:
                end = s.find("```", idx + len(fence))
                if end > idx:
                    s = s[idx + len(fence):end].strip()
                    break
    # 2) 截首个 { 到末尾
    if "{" in s:
        s = s[s.find("{"):s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"dsh response not valid JSON: {e}; raw[:200]={raw[:200]!r}")
    # 3) 必填字段
    for k in ("claim_type", "claim", "confidence", "evidence_refs", "unknowns"):
        if k not in obj:
            raise ValueError(f"missing required field: {k}")
    if obj["claim_type"] not in ("finding", "assessment", "recommendation", "warning", "hypothesis"):
        raise ValueError(f"invalid claim_type: {obj['claim_type']}")
    if obj["confidence"] not in ("low", "medium", "high", "proved"):
        raise ValueError(f"invalid confidence: {obj['confidence']}")
    obj.setdefault("conditions", "")
    obj.setdefault("counter_evidence_refs", [])
    return obj


# ---------------------------------------------------------------------------
# T12 SK-03 inspection-materials 专用 prompt — 受控行动 + 材料生成
# 区别于 cve_impact_brief (出判断): 这里出"行动计划 + 预期产物 + 验收准则"
# 喂 action_service.create_with_dsh → 落 draft action (plan + plan_hash)
# ---------------------------------------------------------------------------

INSPECTION_MATERIALS_SCHEMA_V1 = {
    "plan": "<行动计划 Markdown, ≤ 50KB>",
    "expected_artifacts": ["<产物名, 如 'checklist' / 'report' / 'data_export'>"],
    "success_criteria": "<完成判据文本, ≤ 500 字符>",
    "tool_versions": {"<tool_name>": "<version>"},
    "unknowns": ["<未知项 / 缺资源 / 缺文档; 必须显式呈现>"],
}


def build_inspection_materials_prompt(
    *,
    case_id: str,
    judgment_id: str,
    subject_name: str,
    cve_id: str,
    scope: str,
    evidence_materials: list[dict[str, Any]],
) -> str:
    """构造 SK-03 inspection-materials 的 dsh prompt (action plan 生成).

    Parameters
    ----------
    case_id:
        例 "ABCDEFGHIJKLMNOPQRSTUVWXY".
    judgment_id:
        已发布的判断 (contracts §10.1: action.judgment_id 必引 published judgment).
    subject_name / cve_id / scope:
        行动目标上下文.
    evidence_materials:
        [{id, title, content_hash, summary?}, ...] — 喂 LLM 出计划参考.

    Returns
    -------
    完整 prompt 字符串.

    纪律
    ----
    - plan ≤ 50KB (服务层校验, 超长 422)
    - expected_artifacts 是 list[str], 至少 1 (否则 "材料" 不成立)
    - success_criteria ≤ 500 字符
    - unknowns 缺失时 plan 标 incomplete, 服务层 enforce (对齐 T11 baseline §5)
    - plan_hash = sha256(plan) — contracts §6.4 plan 改 = hash 改 = 重建
    """
    materials_block = "\n\n".join(
        f"### material_id={m.get('id', '?')}\n"
        f"title: {m.get('title', '(no title)')}\n"
        f"content_hash: {m.get('content_hash', '?')}\n"
        f"summary: {m.get('summary', '(none)')[:300]}"
        for m in evidence_materials
    )
    schema_str = json.dumps(INSPECTION_MATERIALS_SCHEMA_V1, ensure_ascii=False, indent=2)
    return (
        f"你是一名安全应急工程师 (蓝队值守), 针对一个已发布的判断 (judgment_id={judgment_id}) "
        f"输出受控行动的执行计划.\n\n"
        f"## 上下文\n\n"
        f"- case_id: {case_id}\n"
        f"- subject: {subject_name}\n"
        f"- cve_id: {cve_id}\n"
        f"- scope: {scope}\n\n"
        f"## 已有材料 (materials)\n\n"
        f"{materials_block or '(无 materials — 这是缺材料场景, unknowns 必须显式列出)'}\n\n"
        f"## 输出要求 (严格 JSON, 不允许 prose 包裹)\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"## 纪律\n"
        f"1. plan 长度 ≤ 50000 字符; 服务层超长 422 拒收\n"
        f"2. expected_artifacts 至少 1 条; '材料已生成' ≠ '排查已完成' (baseline §5)\n"
        f"3. success_criteria 必须可验证 (数值 / 步骤 / 状态变化)\n"
        f"4. unknowns 缺失时 plan 标 incomplete (baseline §5 硬约束)\n"
        f"5. tool_versions 是 dict, 列出计划用的工具/版本 (空 dict 也允许)\n"
        f"6. 不允许 '生成清单即完成排查' 的偷换; 验收由业务侧触发, 你只生成计划\n"
        f"{_EVIDENCE_RULE}\n"
    )


def parse_inspection_materials_response(raw: str) -> dict[str, Any]:
    """解析 dsh 返回的 inspection-materials JSON; 容错 + 必填字段校验."""
    if not raw or not raw.strip():
        raise ValueError("empty response from dsh")
    s = raw.strip()
    if "```" in s:
        for fence in ("```json", "```JSON", "```"):
            idx = s.find(fence)
            if idx >= 0:
                end = s.find("```", idx + len(fence))
                if end > idx:
                    s = s[idx + len(fence):end].strip()
                    break
    if "{" in s:
        s = s[s.find("{"):s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"dsh response not valid JSON: {e}; raw[:200]={raw[:200]!r}")
    for k in ("plan", "expected_artifacts", "success_criteria", "tool_versions", "unknowns"):
        if k not in obj:
            raise ValueError(f"missing required field: {k}")
    if not isinstance(obj["expected_artifacts"], list) or len(obj["expected_artifacts"]) == 0:
        raise ValueError("expected_artifacts must be non-empty list")
    if not isinstance(obj["tool_versions"], dict):
        raise ValueError("tool_versions must be dict")
    if not isinstance(obj["unknowns"], list):
        raise ValueError("unknowns must be list")
    return obj


# ---------------------------------------------------------------------------
# T13 SK-04 knowledge 经验发布 专用 prompt
# 区别于 cve_impact_brief (出判断) / inspection_materials (出行动计划):
#   这里出"可复用经验" (Markdown + 前提/反例/证据/复查时间)
# 喂 knowledge_service.create_with_dsh → 落 draft knowledge (T13 SK-04)
# ---------------------------------------------------------------------------

KNOWLEDGE_PUBLISH_SCHEMA_V1 = {
    "title": "<经验标题, ≤ 200 字符>",
    "body": "<经验正文 Markdown, ≤ 100KB; 含原理/步骤/适用边界>",
    "prerequisites": ["<适用前提, 至少 1 个具体条件>"],
    "counter_examples": ["<不适用场景, 反例>"],
    "evidence_refs": [
        {
            "material_id": "MAT-XXX",
            "hash": "sha256 与 material.content_hash 一致",
            "quote": "≤ 500 字符原文片段"
        }
    ],
    "review_at": "ISO 8601 (下次复查时间, SK-06 触发)",
    "expiry_at": "ISO 8601 or null (有效期, null=长期)",
}


def build_knowledge_prompt(
    *,
    case_id: str,
    judgment_id: str,
    action_id: str,
    subject_name: str,
    cve_id: str,
    kind: str,
    evidence_materials: list[dict[str, Any]],
) -> str:
    """构造 SK-04 knowledge 经验发布的 dsh prompt.

    Parameters
    ----------
    case_id / judgment_id / action_id:
        上下文 ID, 用于派生 prerequisites 与 counter_examples 的具体边界.
    subject_name / cve_id:
        经验主题.
    kind:
        principle|pattern|anti_pattern|reference|playbook|checklist
    evidence_materials:
        [{id, title, content_hash, summary?}, ...] — 喂 LLM 出 evidence_refs.

    Returns
    -------
    完整 prompt.

    纪律
    ----
    - body ≤ 100KB (服务层校验, 超长 422)
    - title ≤ 200 字符
    - prerequisites 至少 1 个具体条件 (空 list 服务层补抛)
    - evidence_refs 至少 1 条; hash 必须对得上 material.content_hash (服务层 enforce, 同 T11 §5.2)
    - review_at 必填 (SK-06 触发 review_due 每日 job)
    - counter_examples 缺失时给空 list (T13 不强制)
    - expiry_at null = 长期; 否则 ISO 8601
    """
    materials_block = "\n\n".join(
        f"### material_id={m.get('id', '?')}\n"
        f"title: {m.get('title', '(no title)')}\n"
        f"content_hash: {m.get('content_hash', '?')}\n"
        f"summary: {m.get('summary', '(none)')[:300]}"
        for m in evidence_materials
    )
    schema_str = json.dumps(KNOWLEDGE_PUBLISH_SCHEMA_V1, ensure_ascii=False, indent=2)
    return (
        f"你是一名安全应急工程师 (蓝队), 针对一个已验收的修复行动, 提炼一份可复用的经验 (knowledge). \n\n"
        f"## 上下文\n\n"
        f"- case_id: {case_id}\n"
        f"- judgment_id: {judgment_id}\n"
        f"- action_id: {action_id}\n"
        f"- subject: {subject_name}\n"
        f"- cve_id: {cve_id}\n"
        f"- kind: {kind} (principle|pattern|anti_pattern|reference|playbook|checklist)\n\n"
        f"## 已有材料 (materials)\n\n"
        f"{materials_block or '(无 materials — 这是缺材料场景, prerequisites 必须显式列出前置资源/上下文)'}\n\n"
        f"## 输出要求 (严格 JSON, 不允许 prose 包裹)\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"## 纪律\n"
        f"1. body 长度 ≤ 100000 字符; 服务层超长 422 拒收\n"
        f"2. title ≤ 200 字符; 服务层超长 422 拒收\n"
        f"3. prerequisites 至少 1 条 (空 list 服务层抛); 写具体条件, 不写『一般情况』\n"
        f"4. counter_examples 必填, 缺则空 list; 列出不适用场景\n"
        f"5. evidence_refs 至少 1 条; hash 必须对得上 material.content_hash (服务层校验)\n"
        f"6. review_at 必填, ISO 8601 格式 (例 2026-12-01T00:00:00+00:00); SK-06 每日 job 扫到挂 case blocker\n"
        f"7. expiry_at null = 长期; 否则 ISO 8601\n"
        f"8. 不写『可能有用』/『建议关注』等模糊语言; 必须可复现 / 可验证\n"
        f"{_EVIDENCE_RULE}\n"
    )


def parse_knowledge_publish_response(raw: str) -> dict[str, Any]:
    """解析 dsh 返回的 knowledge JSON; 容错 + 必填字段校验."""
    if not raw or not raw.strip():
        raise ValueError("empty response from dsh")
    s = raw.strip()
    if "```" in s:
        for fence in ("```json", "```JSON", "```"):
            idx = s.find(fence)
            if idx >= 0:
                end = s.find("```", idx + len(fence))
                if end > idx:
                    s = s[idx + len(fence):end].strip()
                    break
    if "{" in s:
        s = s[s.find("{"):s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"dsh response not valid JSON: {e}; raw[:200]={raw[:200]!r}")
    for k in ("title", "body", "prerequisites", "counter_examples", "evidence_refs", "review_at"):
        if k not in obj:
            raise ValueError(f"missing required field: {k}")
    if not isinstance(obj["prerequisites"], list) or len(obj["prerequisites"]) == 0:
        raise ValueError("prerequisites must be non-empty list (SK-04 硬约束)")
    if not isinstance(obj["counter_examples"], list):
        raise ValueError("counter_examples must be list")
    if not isinstance(obj["evidence_refs"], list) or len(obj["evidence_refs"]) == 0:
        raise ValueError("evidence_refs must be non-empty list")
    if not obj.get("review_at"):
        raise ValueError("review_at required (SK-06 触发)")
    obj.setdefault("expiry_at", None)
    return obj


# ---------------------------------------------------------------------------
# T14 SK-01 daily-priority-intel 专用 prompt — 今日重点情报聚合
# 区别于 deep_read (面向阅读者): 这里出"今日 top N 重点 + 理由 + 原始来源"
# 喂 sk01_daily_priority.compute() 拼 admission_log + signals 聚合, 调 dsh
# ---------------------------------------------------------------------------

DAILY_PRIORITY_INTEL_SCHEMA_V1 = {
    "top_items": [
        {
            "rank": 1,
            "summary": "<一句话重点, ≤ 100 字符>",
            "subject_id": "SUBJ-XXX",
            "reason": "<为何重要 / 关联判断 / 受影响版本, ≤ 300 字符>",
            "source_refs": [{"material_id": "MAT-XXX", "signal_id": "SIG-XXX"}],
            "confidence": "low|medium|high",
        }
    ],
    "watchlist_changes": ["<已关注 subject 的最新状态变化, 例: SUBJ-001 从 unverified → verified>"],
    "suggested_actions": ["<下一步建议, 例: 启动 cve-impact-brief / inspection-materials 评估>"],
}


def build_daily_priority_intel_prompt(
    *,
    subject_id: str,
    admission_recent: list[dict[str, Any]],
    signals_recent: list[dict[str, Any]],
    watchlist_subjects: list[str] | None = None,
) -> str:
    """构造 SK-01 daily-priority-intel 的 dsh prompt.

    Parameters
    ----------
    subject_id:
        顶层 subject (可不传, 走全 subject).
    admission_recent:
        admission_log 近 7 天记录 [{material_id, verdict, reason, ts}, ...]
    signals_recent:
        signals 近 3 天记录 [{id, material_id, summary, subject_id, confidence, occurred_at}, ...]
    watchlist_subjects:
        关注的 subject_id 列表 (T08 watchlist; 默认空)

    Returns
    -------
    完整 prompt.
    """
    watch_block = ""
    if watchlist_subjects:
        watch_block = (
            "\n## 关注 subject (watchlist)\n\n"
            + "\n".join(f"- {s}" for s in watchlist_subjects)
            + "\n"
        )
    admission_block = "\n".join(
        f"- ts={a.get('ts', '?')}, material_id={a.get('material_id', '?')}, "
        f"verdict={a.get('verdict', '?')}, reason={a.get('reason', '(none)')[:120]}"
        for a in admission_recent[:20]
    ) or "(无 admission 记录)"
    signals_block = "\n".join(
        f"- id={s.get('id', '?')}, material_id={s.get('material_id', '?')}, "
        f"ts={s.get('occurred_at', '?')}, subject={s.get('subject_id', '?')}, "
        f"conf={s.get('confidence', '?')}, summary={s.get('summary', '(none)')[:200]}"
        for s in signals_recent[:20]
    ) or "(无 signals 记录)"
    schema_str = json.dumps(DAILY_PRIORITY_INTEL_SCHEMA_V1, ensure_ascii=False, indent=2)
    return (
        f"你是一名安全应急分析师, 帮一名蓝队值班员 (30 分钟内) 看清今天到底发生了什么, "
        f"决定先动哪条线.\n\n"
        f"## 上下文\n\n"
        f"- subject_id (可选): {subject_id or '(全 subject 视角)'}\n"
        f"{watch_block}\n"
        f"## 近 7 天 admission_log (准入决策)\n\n{admission_block}\n\n"
        f"## 近 3 天 signals (情报事件)\n\n{signals_block}\n\n"
        f"## 输出要求 (严格 JSON, 不允许 prose 包裹)\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"## 纪律\n"
        f"1. top_items 3-5 条; 每条 rank + 一句话重点 + 关联 subject + reason + 原始来源 "
        f"source_refs (material_id / signal_id 必须从上文原样回填, 不得改写或臆造)\n"
        f"2. watchlist_changes 仅列已关注 subject 的状态变化 (空数组表示无变化)\n"
        f"3. suggested_actions 给 1-3 条具体下一步 (例: '启动 cve-impact-brief 评估 CVE-2026-31337')\n"
        f"4. confidence: high = 有 ≥2 独立来源; medium = 1 强来源; low = 推断\n"
        f"5. 不写『可能有用』『建议关注』等模糊语言; 必须可复现 / 可验证\n"
        f"{_EVIDENCE_RULE}\n"
    )


def parse_daily_priority_intel_response(raw: str) -> dict[str, Any]:
    """解析 dsh 返回的 SK-01 JSON; 容错 + 必填字段校验."""
    if not raw or not raw.strip():
        raise ValueError("empty response from dsh")
    s = raw.strip()
    if "```" in s:
        for fence in ("```json", "```JSON", "```"):
            idx = s.find(fence)
            if idx >= 0:
                end = s.find("```", idx + len(fence))
                if end > idx:
                    s = s[idx + len(fence):end].strip()
                    break
    if "{" in s:
        s = s[s.find("{"):s.rfind("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"dsh response not valid JSON: {e}; raw[:200]={raw[:200]!r}")
    for k in ("top_items", "watchlist_changes", "suggested_actions"):
        if k not in obj:
            raise ValueError(f"missing required field: {k}")
    if not isinstance(obj["top_items"], list) or len(obj["top_items"]) == 0:
        raise ValueError("top_items must be non-empty list")
    if not isinstance(obj["watchlist_changes"], list):
        raise ValueError("watchlist_changes must be list")
    if not isinstance(obj["suggested_actions"], list):
        raise ValueError("suggested_actions must be list")
    return obj


def build_interest_advisor_prompt(
    *,
    ingest_7d: list[dict[str, Any]],
    behavior_30d: list[dict[str, Any]],
    current_selected: list[str],
    domain_labels: dict[str, str],
) -> str:
    """构造关注域 AI 推荐 prompt (density T3, 设计稿 §4.2).

    输入全部为聚合统计 (域计数/占比/行为分), 无原始 URL 与标题 —
    advisor 分析的是分布, 不是具体条目。严格域枚举约束写入 prompt,
    解析侧 (interest_domain_advisor) 仍做枚举校验双保险。

    域枚举经 ``domain_labels`` 由调用方注入 (advisor 传
    ``auto_classifier.PRACTICE_DOMAIN_LABELS``) — 本模块不 import
    业务模块: auto_classifier 惰性 import ai_hub.gateway, prompts
    若反向 import 它即成 R4 守卫拦截的 services 域惰性环。
    """
    enum_lines = "\n".join(f"- {d}: {label}" for d, label in domain_labels.items())
    ingest_lines = "\n".join(
        f"- {e['domain']}: {e['count']} 条 (占比 {e['share']:.0%})"
        for e in ingest_7d
    ) or "(近 7 天无命中条目)"
    behavior_lines = "\n".join(
        f"- {e['domain']}: 行为分 {e['score']}, 近 30 天事件 {e['events_30d']} 次"
        for e in behavior_30d
    ) or "(近 30 天无行为信号)"
    selected_block = ", ".join(current_selected) or "(未勾选)"
    return (
        "你是一名安全从业者的关注域顾问。根据以下聚合统计, 推荐最多 5 个值得"
        "关注的实践域 (可为已勾选域之外的新方向, 也可建议保留现有勾选)。\n\n"
        "## 合法域枚举 (recommended 只能取以下键, 之外的任何值都会被丢弃)\n\n"
        f"{enum_lines}\n\n"
        f"## 近 7 天各域入库分布\n\n{ingest_lines}\n\n"
        f"## 近 30 天各域行为聚合 (interest_signals)\n\n{behavior_lines}\n\n"
        f"## 当前勾选域\n\n{selected_block}\n\n"
        "## 输出要求 (严格 JSON, 不允许 prose 包裹)\n\n"
        '```json\n{"recommended": ["<合法域键, ≤5 个>"], '
        '"reasons": {"<合法域键>": "<一句话理由>"}}\n```\n\n'
        "## 纪律\n"
        "1. recommended 最多 5 个, 每个都必须在合法域枚举内\n"
        "2. reasons 只为 recommended 中的域各给一句话理由 (≤60 字)\n"
        "3. 依据入库占比与行为分偏离勾选的方向给出, 不编造枚举外的域\n"
    )


def build_content_pref_advisor_prompt(
    *,
    category_behavior: list[dict[str, Any]],
    source_behavior: list[dict[str, Any]],
    current_effective: dict[str, Any],
    category_labels: dict[str, str],
) -> str:
    """内容偏好 AI 优化建议 prompt (DEV-0316) — 输入全为聚合统计, 无原始 URL/标题。

    让模型据"各类目/来源行为净分 (正=偏好/负=反感)"给出对类目/来源的三级
    建议 (more/less)。枚举由调用方注入 (category_labels), 解析侧再做枚举校验。
    """
    cat_lines = "\n".join(
        f"- {e['category']} ({category_labels.get(e['category'], e['category'])}): "
        f"净分 {e['net']} (近 30 天 {e['events']} 次交互)"
        for e in category_behavior
    ) or "(近 30 天无类目行为信号)"
    src_lines = "\n".join(
        f"- {e['source']}: 净分 {e['net']} (近 30 天 {e['events']} 次交互)"
        for e in source_behavior
    ) or "(近 30 天无来源行为信号)"
    eff = current_effective or {}
    eff_block = (
        f"类目: {eff.get('categories') or {}} · 来源: {eff.get('sources') or {}}"
    )
    return (
        "你是安全资讯工作流的推荐调优顾问。基于以下聚合统计, 对**内容类目**与"
        "**信息源**给出排序偏好建议: 读者明显偏好/反感的, 建议 more/less; 无强信号的不提。\n\n"
        "## 合法类目枚举 (categories 只能取以下键)\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in category_labels.items())
        + "\n\n## 近 7 天各类目入库分布\n\n"
        + cat_lines
        + "\n\n## 近 30 天各来源行为净分 (正=偏好信号, 负=反感信号)\n\n"
        + src_lines
        + "\n\n## 当前生效偏好 (自动+手动合并)\n\n"
        + eff_block
        + "\n\n## 输出要求 (严格 JSON, 不包 prose)\n\n"
        '```json\n{"categories": {"<合法类目键>": "more|less"}, '
        '"sources": {"<来源名>": "more|less"}, '
        '"reasons": {"<键>": "<一句话理由>"}}\n```\n\n'
        "## 纪律\n"
        "1. categories 键必须在合法类目枚举内; sources 键用给定的来源名原文\n"
        "2. 每轴最多 5 项, 只提强信号 (净分明显偏正/偏负或占比异常), 弱信号不提\n"
        "3. reasons 为每个建议键各一句话 (≤60 字); 不编造枚举外的键\n"
    )


# ── 资讯告警复核 (2026-09-27 四模式 P1, gate 无关 — 常开) ──────────
_NEWS_ALERT_REVIEW_PROMPT = """你是安全资讯告警复核员。以下候选资讯已通过关键词初筛,
请逐条判断:读者(安全从业者/AI 从业者)是否需要**执行某个动作**(打补丁/排查资产/
修改配置/关注后续/参加响应), 而非纯知情。

候选列表 (JSON):
{candidates}

判定标准:
- execute=true: 有明确动作需求 — 如在野利用漏洞需排查版本、供应链投毒需查依赖、
  监管通报有报送时限
- execute=false: 纯知情/观点/行业动态, 无读者动作

只输出 JSON 数组, 不要输出其他文字:
[{{"id": "候选id", "execute": true 或 false, "reason": "一句话理由"}}"""


def build_news_alert_review_prompt(candidates: list[dict]) -> str:
    import json as _json
    slim = [
        {"id": c["id"], "rule": c["rule"], "title": c["title"][:100],
         "summary": (c.get("summary") or "")[:200]}
        for c in candidates
    ]
    return _NEWS_ALERT_REVIEW_PROMPT.format(candidates=_json.dumps(slim, ensure_ascii=False))


# ── 拒收日志解释 (2026-10-01 rejection-explain, 常开无 gate) ─────────
_REJECTION_EXPLAIN_PROMPT = """你是资讯质量门禁的解释员。以下条目被采集质量门禁拒收,
请根据标题与拒收 flag, 为每条生成一句面向普通用户的中文解释 (≤60字),
说清它为什么被拒 — 语气客观, 不评判读者, 不堆术语。

拒收条目 (JSON):
{items}

flag 参考含义: content_hash_duplicate=内容重复 / category_mismatch=分类不匹配 /
title_summary_inconsistent=标题摘要不一致 / empty_summary=摘要为空 /
author_unknown=作者无法验证 / title_spam_words=标题营销词 / noise_title=噪音标题

只输出 JSON 数组, 不要输出其他文字:
[{{"id": 条目id, "explain": "一句中文解释"}}]"""


def build_rejection_explain_prompt(items: list[dict]) -> str:
    import json as _json

    slim = [
        {"id": it["id"], "title": (it.get("title") or "")[:100],
         "flags": (it.get("reason") or "")[:120]}
        for it in items
    ]
    return _REJECTION_EXPLAIN_PROMPT.format(
        items=_json.dumps(slim, ensure_ascii=False)
    )


__all__ = [
    "COST_PER_1M_TOKENS",
    "CVE_IMPACT_BRIEF_SCHEMA_V1",
    "DAILY_PRIORITY_INTEL_SCHEMA_V1",
    "DEEP_READ_PROFILES",
    "DEEP_READ_PROFILE_VERSION",
    "INSPECTION_MATERIALS_SCHEMA_V1",
    "KNOWLEDGE_PUBLISH_SCHEMA_V1",
    "ScoreParseError",
    "_build_deep_read_prompt",
    "_build_extract_entities_prompt",
    "_build_score_prompt",
    "_build_summary_prompt",
    "_estimate_cost",
    "_make_cache_key",
    "_parse_entity_list",
    "_parse_score",
    "build_content_pref_advisor_prompt",
    "build_cve_impact_brief_prompt",
    "build_daily_priority_intel_prompt",
    "build_inspection_materials_prompt",
    "build_interest_advisor_prompt",
    "build_knowledge_prompt",
    "build_news_alert_review_prompt",
    "build_rejection_explain_prompt",
    "deep_read_framework_lens",
    "deep_read_profile_for",
    "deep_read_sections",
    "parse_cve_impact_brief_response",
    "parse_daily_priority_intel_response",
    "parse_inspection_materials_response",
    "parse_knowledge_publish_response",
]
