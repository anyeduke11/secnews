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
from typing import Optional
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
) -> Optional[str]:
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
) -> Optional[str]:
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
) -> Optional[str]:
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
    """Full classification of a single item: domain, type, difficulty.

    Returns:
        {"domain": str|None, "type": str|None, "difficulty": str|None}
    """
    return {
        "domain": classify_domain(tags, title, source_url),
        "type": classify_type(tags, title),
        "difficulty": classify_difficulty(tags, title),
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
    "classify_domain",
    "classify_type",
    "classify_difficulty",
    "classify_item",
    "batch_classify",
    "batch_classify_with_terminology",
]