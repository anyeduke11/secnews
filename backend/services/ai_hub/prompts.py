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

# 默认评分兜底 (score 0-10)
DEFAULT_SCORE = 5.0

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


def _parse_score(raw: str) -> float:
    """从 LLM 响应中解析评分."""
    match = re.search(r"(\d+(?:\.\d+)?)", raw.strip())
    if match:
        val = float(match.group(1))
        return max(0.0, min(10.0, val))
    return DEFAULT_SCORE


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

DEEP_READ_PROFILE_VERSION = "v1"

_HEAD_SECTION = {"key": "key_takeaways", "title": "要点速读", "tone": "mint"}
_TAIL_SECTIONS = (
    {"key": "next_actions", "title": "我的动作", "tone": "mint"},
    {"key": "evidence_gaps", "title": "存疑与未证实", "tone": "amber"},
)

# 通用证据约束: 每条判断都要能对应原文, 否则进 evidence_gaps 而不是硬编。
_EVIDENCE_RULE = "每条判断须能对应原文片段; 无法对应的写进 evidence_gaps, 不要编造。"

DEEP_READ_PROFILES: dict[str, dict[str, Any]] = {
    "security": {
        "persona": "你是一名安全应急响应工程师（蓝队值班），需要在几分钟内判断这条情报要不要现在就动手",
        "extra_sections": (
            {"key": "impact_ioc", "title": "影响面与指标", "tone": "red"},
            {"key": "exploit_conditions", "title": "利用条件", "tone": "amber"},
            {"key": "remediation", "title": "处置清单", "tone": "mint"},
        ),
        "budget": 10000,
        "evidence": "尽量给出可核对的编号/受影响版本/组件名与具体缓解动作（补丁版本、配置项、检测规则）。",
    },
    "ai_security": {
        "persona": "你是一名 AI 安全研究员，关注模型与 Agent 系统的攻击面和可落地的加固手段",
        "extra_sections": (
            {"key": "attack_surface", "title": "攻击面与绕过", "tone": "red"},
            {"key": "mitigation", "title": "缓解与加固", "tone": "mint"},
            {"key": "detection", "title": "监测信号", "tone": "amber"},
        ),
        "budget": 10000,
        "evidence": "区分「论文/厂商自述」与「独立复现」；给出可监测的信号而不只是风险名词。",
    },
    "ai": {
        "persona": "你是一名 AI 平台负责人，判断这项能力对自己的产品是可用、可替代还是无关",
        "extra_sections": (
            {"key": "capability_boundary", "title": "能力边界", "tone": "mint"},
            {"key": "cost_alternatives", "title": "成本与替代", "tone": "amber"},
        ),
        "budget": 8000,
        "evidence": "基准分数须注明评测方与条件；区分宣传口径与可验证结果。",
    },
    "finance": {
        "persona": "你是一名金融机构合规负责人 / CISO，只关心这条监管信息约束了谁、何时生效、违反的后果",
        "extra_sections": (
            {"key": "regulation_points", "title": "监管要点", "tone": "mint"},
            {"key": "applicability", "title": "适用主体", "tone": "amber"},
            {"key": "obligations_timeline", "title": "义务与时限", "tone": "amber"},
            {"key": "penalty", "title": "罚则与追责", "tone": "amber"},
        ),
        "budget": 8000,
        "evidence": "禁止推测监管意图；只写原文出现的发文机关、条款、日期与罚则。",
    },
    "bid": {
        "persona": "你是一名投标负责人，要从公告里抠出资格硬门槛、评分规则和不能错过的时间点",
        "extra_sections": (
            {"key": "tender_card", "title": "项目卡", "tone": "mint"},
            {"key": "qualification", "title": "资格硬门槛", "tone": "amber"},
            {"key": "scoring", "title": "评分与商务项", "tone": "mint"},
            {"key": "key_dates", "title": "时间节点", "tone": "amber"},
        ),
        "budget": 12000,
        "evidence": "尽量引用原文条款号；预算、资质、截止时间这类字段缺失时必须写进 evidence_gaps。",
    },
    "github": {
        "persona": "你是一名开源选型工程师，判断这个项目能不能进自己的技术栈、替换成本多大",
        "extra_sections": (
            {"key": "positioning", "title": "定位与成熟度", "tone": "mint"},
            {"key": "adoption_cost", "title": "接入成本", "tone": "amber"},
            {"key": "license_risk", "title": "许可与合规", "tone": "amber"},
        ),
        "budget": 6000,
        "evidence": "区分 README 自述与实际能力；许可证结论须给出具体协议名与条款影响。",
    },
    "startup": {
        "persona": "你是一名独立开发者 / 一人公司经营者，从别人的融资与失败里找可复制的做法与要避的坑",
        "extra_sections": (
            {"key": "biz_signal", "title": "商业信号", "tone": "mint"},
            {"key": "playbook", "title": "可复制做法", "tone": "mint"},
            {"key": "pitfalls", "title": "踩坑与风险", "tone": "amber"},
        ),
        "budget": 6000,
        "evidence": "融资金额/轮次/投资方只写原文出现的；不要外推估值与赛道趋势。",
    },
    "tech": {
        "persona": "你是一名 IT 架构师，梳理事实并判断这条技术动态对自己既有系统的实际影响",
        "extra_sections": (
            {"key": "facts", "title": "事实梳理", "tone": "mint"},
            {"key": "system_impact", "title": "对既有系统影响", "tone": "amber"},
            {"key": "watch", "title": "后续看点", "tone": "mint"},
        ),
        "budget": 6000,
        "evidence": "把「已发布 / 已宣布 / 传闻」分开陈述，不混为既成事实。",
    },
}

# 未识别分类的兜底视角（不抛错，保证深度阅读总能出结果）
_GENERAL_PROFILE: dict[str, Any] = {
    "persona": "你是一名安全资讯研判员，为这条内容做结构化摘要与要点提炼",
    "extra_sections": (
        {"key": "context", "title": "背景与来龙去脉", "tone": "mint"},
        {"key": "significance", "title": "为什么值得注意", "tone": "amber"},
    ),
    "budget": 8000,
    "evidence": _EVIDENCE_RULE,
}


def deep_read_profile_for(category: str | None) -> dict[str, Any]:
    """按文章分类取视角; 未知分类回落通用视角而不是抛错。"""
    return DEEP_READ_PROFILES.get(str(category or ""), _GENERAL_PROFILE)


def deep_read_sections(category: str | None) -> list[dict[str, str]]:
    """该分类的有序分节定义: 要点速读 + 专属节 + 我的动作 + 存疑与未证实。"""
    profile = deep_read_profile_for(category)
    return [_HEAD_SECTION, *profile["extra_sections"], *_TAIL_SECTIONS]


def _build_deep_read_prompt(
    category: str | None,
    entity_meta: dict[str, str],
    content: str,
) -> str:
    """构建分类型深度解读 prompt。

    返回的 JSON schema 由 ``deep_read_sections(category)`` 的 key 决定 —— 调用方
    必须用同一函数解析, 否则分节键会漂移。
    """
    profile = deep_read_profile_for(category)
    sections = deep_read_sections(category)
    schema = json.dumps(
        {s["key"]: "<本节内容, markdown, 60~120 字>" for s in sections},
        ensure_ascii=False,
        indent=2,
    )
    titles = "；".join(f"{s['key']}={s['title']}" for s in sections)
    budget = int(profile["budget"])
    meta_lines = "".join(
        f"[{k}] {v}\n" for k, v in entity_meta.items() if v and k != "entity_type"
    )
    return (
        f"{profile['persona']}。请分析下面这条资讯, 生成结构化深度解读。\n\n"
        "严格要求:\n"
        "1. 必须返回合法 JSON, 键严格匹配下方 schema, 不得省略或新增键。\n"
        "2. 每节用 markdown (可用列表/粗体/代码), 不要套外层 ```json 围栏。\n"
        "3. 每节 60~120 字, 直接给结论与信息点, 禁止空话、复述原文、无信息量总结。\n"
        f"4. 证据约束: {profile['evidence']} {_EVIDENCE_RULE}\n"
        f"5. 各节含义: {titles}\n\n"
        f"JSON schema:\n{schema}\n\n"
        f"来源元信息:\n{meta_lines or '(无)'}\n\n"
        f"待分析内容 (最多 {budget} 字符):\n{content[:budget]}"
    )


__all__ = [
    "COST_PER_1M_TOKENS",
    "DEEP_READ_PROFILES",
    "DEEP_READ_PROFILE_VERSION",
    "DEFAULT_SCORE",
    "_build_deep_read_prompt",
    "_build_extract_entities_prompt",
    "_build_score_prompt",
    "_build_summary_prompt",
    "_estimate_cost",
    "_make_cache_key",
    "_parse_entity_list",
    "_parse_score",
    "deep_read_profile_for",
    "deep_read_sections",
]
