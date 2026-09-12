"""Auto classifier — rule-based domain/topic/type/difficulty assignment for knowledge items.

Design
------
- Tag-based: uses a curated tag→domain mapping table
- Title-based: keyword matching for items without domain-relevant tags
- URL-based: source URL domain as secondary signal
- All rules are deterministic, no LLM dependency
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

log = logging.getLogger("hotspot.auto_classifier")

# ═══════════════════════════════════════════════════════════════
# Domain classification rules
# ═══════════════════════════════════════════════════════════════

# Tag → domain mapping (primary classifier)
# A tag appearing in multiple domains is weighted toward the first match.
TAG_DOMAIN_MAP: dict[str, str] = {
    # AI / LLM
    "AI编程": "ai",
    "大模型进展": "ai",
    "Claude": "ai",
    "DeepSeek": "ai",
    "OpenAI": "ai",
    "模型": "ai",
    "Agent": "ai",
    "大模型安全": "ai",
    "AI安全": "ai",
    "AI应用": "ai",
    "设计生成": "ai",
    "AI驱动": "ai",
    "机器学习": "ai",
    "深度学习": "ai",
    "LLM": "ai",
    "GPT": "ai",
    "自然语言": "ai",
    "多模态": "ai",
    "AI": "ai",
    "AI产品": "ai",
    "AI工具": "ai",
    "Coding": "ai",
    "prompt": "ai",
    # Security
    "安全技术": "security",
    "安全管理": "security",
    "安全运营": "security",
    "安全事件": "security",
    "合规": "security",
    "攻防演练": "security",
    "漏洞管理": "security",
    "数据安全": "security",
    "安全架构": "security",
    "红队攻防": "security",
    "CISO": "security",
    "国标": "security",
    "标准规范": "security",
    "安全": "security",
    "网络安全": "security",
    "渗透测试": "security",
    "威胁情报": "security",
    "零信任": "security",
    "安全基础": "security",
    "隐私": "security",
    "加密": "security",
    "防火墙": "security",
    "等保": "security",
    "安全审计": "security",
    # Finance / Investment
    "金融科技": "finance",
    "银行业": "finance",
    "证券业": "finance",
    "金融监管": "finance",
    "宏观分析": "finance",
    "招投标": "finance",
    "商务": "finance",
    "投资": "finance",
    "财经": "finance",
    "央行": "finance",
    "保险": "finance",
    "支付": "finance",
    # Startup / Indie Dev
    "效率工具": "startup",
    "项目管理": "startup",
    "团队管理": "startup",
    "认知": "startup",
    "学习方法": "startup",
    "Skill技能": "startup",
    "知识管理": "startup",
    "写作": "startup",
    "阅读": "startup",
    "创业": "startup",
    "独立开发": "startup",
    "产品": "startup",
    "运营": "startup",
    "增长": "startup",
    "营销": "startup",
    # Dev / Engineering
    "编程": "dev",
    "技术": "dev",
    "技术原理": "dev",
    "教程实操": "dev",
    "开发者工具": "dev",
    "架构": "dev",
    "开源": "dev",
    "前端": "dev",
    "后端": "dev",
    "数据库": "dev",
    "DevOps": "dev",
    "Git": "dev",
    "测试": "dev",
    "部署": "dev",
}

# Title keyword → domain (secondary, for items without tags)
TITLE_DOMAIN_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"AI|大模型|LLM|GPT|Claude|DeepSeek|OpenAI|机器学习|深度学习|智能体|Agent|多模态"), "ai"),
    (re.compile(r"安全|漏洞|黑客|渗透|攻防|防火墙|加密|隐私|合规|等保|CISO|威胁"), "security"),
    (re.compile(r"金融|银行|证券|保险|投资|央行|财经|监管|支付"), "finance"),
    (re.compile(r"创业|独立开发|产品|运营|增长|营销|效率工具|项目管理"), "startup"),
    (re.compile(r"编程|开发|代码|开源|部署|架构师|Git|DevOps|前端|后端|数据库|API|程序员"), "dev"),
]

# Source URL domain → domain (tertiary)
URL_DOMAIN_MAP: dict[str, str] = {
    "mp.weixin.qq.com": None,  # too generic, skip
    "www.secrss.com": "security",
    "cn-sec.com": "security",
    "www.anquanke.com": "security",
    "m.freebuf.com": "security",
    "www.freebuf.com": "security",
    "xz.aliyun.com": "security",
    "blog.zgsec.cn": "security",
    "security.tencent.com": "security",
    "security.apple.com": "security",
    "www.qianxin.com": "security",
    "www.4hou.com": "security",
    "aihot.virxact.com": "ai",
    "github.com": "dev",
    "claude.com": "ai",
    "openrouter.ai": "ai",
    "gitbook.cn": "dev",
    "post.m.smzdm.com": "startup",
    "www.gov.cn": "finance",
    "www.cbirc.gov.cn": "finance",
    "www.pbc.gov.cn": "finance",
    "c.m.163.com": "finance",
    "www.woshipm.com": "startup",
    "www.sohu.com": "general",
    "blog.csdn.net": "dev",
    "clickhouse.com": "dev",
    "www.dama.org.cn": "security",
    "www.cbimc.cn": "finance",
}

# ═══════════════════════════════════════════════════════════════
# Practice domain classification (DEV-0176 — Workbench Focus PRD P0.1)
#
# 二级实践域: 面向安全从业者的工作方向, 与上面的粗粒度 domain 正交。
# 覆盖范围: 仅安全相关内容会有实践域; 非安全内容 (finance/dev/startup)
# 返回 None —— 相关性门禁靠"命中加权、未命中降权"消费, 不要求全量覆盖。
# 词表为数据驱动常量, P1 运营化时再考虑外置。
# ═══════════════════════════════════════════════════════════════

PRACTICE_DOMAINS: tuple[str, ...] = (
    "enterprise_security",   # 企业安全建设
    "vuln_research",         # 漏洞研究
    "threat_hunting",        # 威胁狩猎
    "incident_response",     # 应急响应
    "ai_security",           # AI 安全
    "appsec",                # 应用安全
    "cloud_data_security",   # 云与数据安全
    "compliance",            # 合规监管
)

PRACTICE_DOMAIN_LABELS: dict[str, str] = {
    "enterprise_security": "企业安全建设",
    "vuln_research": "漏洞研究",
    "threat_hunting": "威胁狩猎",
    "incident_response": "应急响应",
    "ai_security": "AI 安全",
    "appsec": "应用安全",
    "cloud_data_security": "云与数据安全",
    "compliance": "合规监管",
}

# Tag → practice domain (primary)。键顺序即优先级: 具体 tag 先于泛化 tag。
TAG_PRACTICE_MAP: dict[str, str] = {
    # AI 安全 (先于泛化 AI/安全 tag 命中)
    "大模型安全": "ai_security",
    "AI安全": "ai_security",
    "AI 安全": "ai_security",
    "模型安全": "ai_security",
    "提示注入": "ai_security",
    "Prompt注入": "ai_security",
    # 威胁狩猎
    "威胁情报": "threat_hunting",
    "威胁狩猎": "threat_hunting",
    "APT": "threat_hunting",
    "溯源": "threat_hunting",
    # 应急响应
    "应急响应": "incident_response",
    "安全事件": "incident_response",
    "勒索软件": "incident_response",
    # 漏洞研究
    "漏洞管理": "enterprise_security",  # 漏洞管理流程属安全建设; 具体漏洞研究靠标题关键词
    "漏洞": "vuln_research",
    "CVE": "vuln_research",
    "0day": "vuln_research",
    # 应用安全
    "渗透测试": "appsec",
    "代码审计": "appsec",
    "SDL": "appsec",
    "DevSecOps": "appsec",
    "Web安全": "appsec",
    "供应链安全": "appsec",
    # 云与数据安全
    "数据安全": "cloud_data_security",
    "云安全": "cloud_data_security",
    "隐私": "cloud_data_security",
    "加密": "cloud_data_security",
    # 合规监管
    "合规": "compliance",
    "等保": "compliance",
    "国标": "compliance",
    "标准规范": "compliance",
    "安全审计": "compliance",
    # 企业安全建设 (泛化 tag 放最后兜底)
    "安全管理": "enterprise_security",
    "安全运营": "enterprise_security",
    "安全架构": "enterprise_security",
    "安全建设": "enterprise_security",
    "零信任": "enterprise_security",
    "攻防演练": "enterprise_security",
    "红队攻防": "enterprise_security",
    "CISO": "enterprise_security",
    "防火墙": "enterprise_security",
}

# Title keyword → practice domain (secondary)。数组顺序即优先级, 具体 pattern 在前。
TITLE_PRACTICE_RULES: list[tuple[re.Pattern, str]] = [
    # AI 安全 (DEV-0179: 无偏人评发现缺口 — 真实语料常用攻击动词而非"AI安全"标签
    # 表述 Agent 攻击, 如 "Agent 再爆新攻击/智能体协作入侵/窃取 API 密钥", 补攻击动词系)
    (re.compile(r"大模型安全|AI安全|AI 安全|模型安全|提示注入|[Pp]rompt\s*[Ii]njection|越狱|数据投毒|对抗样本|AI红队|Agent安全|智能体.{0,8}(入侵|攻击)|Agent.{0,8}(攻击|入侵)|窃取\s*(API\s*)?密钥"), "ai_security"),
    # 漏洞研究
    (re.compile(r"CVE-\d{4}|0day|0-day|漏洞|POC|EXP|提权|反序列化|栈溢出|堆溢出|命令注入|SQL注入|复现"), "vuln_research"),
    # 威胁狩猎
    (re.compile(r"威胁狩猎|威胁情报|ATT&CK|APT|IOC|溯源|恶意样本|黑客组织|沙箱逃逸|TTP"), "threat_hunting"),
    # 应急响应
    (re.compile(r"应急响应|事件响应|勒索|入侵事件|安全事件处置|取证|隔离处置"), "incident_response"),
    # 应用安全
    (re.compile(r"应用安全|代码审计|SDL|DevSecOps|Web安全|渗透测试|移动安全|APP安全|供应链安全|SSRF|XSS|CSRF"), "appsec"),
    # 云与数据安全
    (re.compile(r"云安全|数据安全|容器安全|K8s\s*安全|Kubernetes\s*安全|云原生安全|隐私计算|数据泄露|数据出境|数据分类分级|密钥管理"), "cloud_data_security"),
    # 合规监管 (DEV-0179: +立法 — AI 立法监管动态是合规从业者的日常输入)
    (re.compile(r"等保|关基|数安法|个保法|网络安全法|合规|监管|网信办|工信部|征求意见|安全测评|安全标准|立法"), "compliance"),
    # 企业安全建设 (泛化兜底)
    (re.compile(r"安全建设|安全运营|安全体系|SOC|零信任|安全架构|安全意识|安全规划|成熟度|安全团队|防护体系|安全治理"), "enterprise_security"),
]


def classify_practice_domain(
    tags: list[str],
    title: str = "",
) -> str | None:
    """Classify the security practitioner practice domain (DEV-0176).

    Priority: tags → title keywords. Returns None for non-security content
    or when no rule matches — the relevance gate consumes None as
    "no boost, no filter" (降权不删).
    """
    # 1. Tag-based
    for tag in tags:
        domain = TAG_PRACTICE_MAP.get(tag)
        if domain:
            return domain

    # 2. Title-based
    for pattern, domain in TITLE_PRACTICE_RULES:
        if pattern.search(title):
            return domain

    return None


# ═══════════════════════════════════════════════════════════════
# Type classification rules
# ═══════════════════════════════════════════════════════════════

TYPE_TAG_MAP: dict[str, str] = {
    "教程实操": "tutorial",
    "技术原理": "paper",
    "行业研究": "report",
    "行业资讯": "news",
    "资讯": "news",
    "宏观分析": "analysis",
    "认知": "opinion",
    "学习方法": "tutorial",
    "国标": "standard",
    "标准规范": "standard",
    "工具": "tool",
    "效率工具": "tool",
    "开源": "tool",
    "产品": "tool",
}

TYPE_TITLE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"教程|指南|入门|实践|实操|怎么|如何|技巧"), "tutorial"),
    (re.compile(r"论文|研究|报告|分析|白皮书|技术原理"), "paper"),
    (re.compile(r"新闻|发布|公告|更新|正式|上线|\d+月\d+日"), "news"),
    (re.compile(r"工具|开源|推荐|神器"), "tool"),
    (re.compile(r"观点|思考|认知|方法论"), "opinion"),
    (re.compile(r"标准|规范|国标|政策|办法|通知|意见|新规|办法|征求意见"), "standard"),
]

# ═══════════════════════════════════════════════════════════════
# Difficulty classification rules
# ═══════════════════════════════════════════════════════════════

DIFFICULTY_TAG_MAP: dict[str, str] = {
    "教程实操": "beginner",
    "技术原理": "advanced",
    "行业研究": "intermediate",
    "宏观分析": "intermediate",
    "认知": "beginner",
    "学习方法": "beginner",
    "效率工具": "beginner",
}

DIFFICULTY_TITLE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"入门|基础|教程|指南|新手|初学者"), "beginner"),
    (re.compile(r"进阶|深入|原理|源码|内核|优化"), "advanced"),
    (re.compile(r"实践|实战|中级|工程"), "intermediate"),
]


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def classify_domain(
    tags: list[str],
    title: str = "",
    source_url: str = "",
) -> str | None:
    """Classify domain from tags, title, and source URL.

    Priority: tags → title → source_url.
    Returns None if no rule matches.
    """
    # 1. Tag-based
    for tag in tags:
        domain = TAG_DOMAIN_MAP.get(tag)
        if domain:
            return domain

    # 2. Title-based
    for pattern, domain in TITLE_DOMAIN_RULES:
        if pattern.search(title):
            return domain

    # 3. URL-based
    if source_url:
        try:
            netloc = urlparse(source_url).netloc
            domain = URL_DOMAIN_MAP.get(netloc)
            if domain:
                return domain
        except Exception:
            pass

    return None


def classify_type(
    tags: list[str],
    title: str = "",
) -> str | None:
    """Classify type (news/analysis/paper/tutorial/tool/opinion/standard) from tags and title."""
    # 1. Tag-based
    for tag in tags:
        t = TYPE_TAG_MAP.get(tag)
        if t:
            return t

    # 2. Title-based
    for pattern, t in TYPE_TITLE_RULES:
        if pattern.search(title):
            return t

    return None


def classify_difficulty(
    tags: list[str],
    title: str = "",
) -> str | None:
    """Classify difficulty (beginner/intermediate/advanced) from tags and title."""
    # 1. Tag-based
    for tag in tags:
        d = DIFFICULTY_TAG_MAP.get(tag)
        if d:
            return d

    # 2. Title-based
    for pattern, d in DIFFICULTY_TITLE_RULES:
        if pattern.search(title):
            return d

    return None


def classify_item(
    tags: list[str],
    title: str = "",
    source_url: str = "",
) -> dict:
    """Full classification of a single item: domain, type, difficulty, practice_domain.

    Returns:
        {"domain": str|None, "type": str|None, "difficulty": str|None,
         "practice_domain": str|None}   # practice_domain since DEV-0176
    """
    return {
        "domain": classify_domain(tags, title, source_url),
        "type": classify_type(tags, title),
        "difficulty": classify_difficulty(tags, title),
        "practice_domain": classify_practice_domain(tags, title),
    }


def batch_classify(items: list[dict]) -> list[dict]:
    """Batch classify a list of items from the knowledge repo.

    Each item dict must have at least: id, title, tags, source_url.
    Returns the same list with domain/type/difficulty populated.
    """
    results = []
    for item in items:
        tags = item.get("tags", [])
        if isinstance(tags, str):
            import json
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        tags = [t for t in tags if t]  # remove empty strings

        classification = classify_item(
            tags=tags,
            title=item.get("title", ""),
            source_url=item.get("source_url", ""),
        )
        item["domain"] = classification["domain"]
        item["type"] = classification["type"]
        item["difficulty"] = classification["difficulty"]
        item["practice_domain"] = classification["practice_domain"]
        # Derive topic from domain (simple fallback)
        if classification["domain"] and not item.get("topic"):
            item["topic"] = classification["domain"]
        results.append(item)

    return results


def batch_classify_with_terminology(
    items: list[dict],
    term_svc=None,
) -> list[dict]:
    """Optional security term normalization wrapper around batch_classify.

    If ``term_svc`` is provided, tags are normalized to canonical forms
    before classification. Falls back to vanilla batch_classify() when
    ``term_svc`` is None — preserving the pure-function contract.
    """
    if term_svc is None:
        return batch_classify(items)

    for item in items:
        tags = item.get("tags", [])
        if isinstance(tags, str):
            import json
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        tags = [t for t in tags if t]
        item["tags"] = term_svc.normalize_tags(tags)
    return batch_classify(items)


__all__ = [
    "PRACTICE_DOMAINS",
    "PRACTICE_DOMAIN_LABELS",
    "batch_classify",
    "batch_classify_with_terminology",
    "classify_difficulty",
    "classify_domain",
    "classify_item",
    "classify_practice_domain",
    "classify_type",
]