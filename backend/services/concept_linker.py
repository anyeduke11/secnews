"""Concept linker — map item tags to knowledge concepts, auto-create new concepts.

Design
------
Phase 1: Tag→concept matching (existing concepts)
Phase 2: Auto-create concept drafts for unmatched high-frequency tags
Phase 3: Update item frontmatter with concept associations
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("hotspot.concept_linker")

# ═══════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
ITEMS_DIR = KNOWLEDGE_DIR / "items"

# ═══════════════════════════════════════════════════════════════
# Tag → concept slug mapping
# ═══════════════════════════════════════════════════════════════

# Curated mapping: high-frequency tags → existing concept slugs
# This is the primary mapping for Phase 1.
TAG_TO_CONCEPT: dict[str, str] = {
    # AI
    "Agent": "ai-agent",
    "AI编程": "ai-development",
    "模型": "ai-agent",
    "大模型进展": "ai-development",
    "Claude": "ai-agent",
    "DeepSeek": "ai-agent",
    "OpenAI": "ai-agent",
    "AI安全": "ai-driven-attack",
    "大模型安全": "llm-security",
    # Security
    "安全技术": "security-fundamentals",
    "安全管理": "security-fundamentals",
    "安全运营": "security-fundamentals",
    "安全事件": "threat-intelligence",
    "攻防演练": "penetration-testing",
    "漏洞管理": "threat-intelligence",
    "数据安全": "defense-modernization",
    "安全架构": "zero-trust-architecture",
    "红队攻防": "penetration-testing",
    "合规": "defense-modernization",
    "威胁情报": "threat-intelligence",
    "零信任": "zero-trust-architecture",
    "安全基础": "security-fundamentals",
    "网络安全设备": "network-security-equipment",
    "渗透测试": "penetration-testing",
    "AI驱动安全": "ai-driven-security",
    "AI驱动攻击": "ai-driven-attack",
    # Business / Management
    "团队管理": "team-management",
    "项目管理": "team-management",
    "领导力": "leadership-anti-patterns",
    "认知": "leadership-anti-patterns",
    "学习方法": "automated-research",
    "知识管理": "automated-research",
    "效率工具": "developer-tools",
    "Skill技能": "developer-tools",
    "写作": "automated-research",
    "阅读": "automated-research",
    "编程": "developer-tools",
    "招投标": "procurement",
    "商务": "procurement",
    "行业研究": "automated-research",
    "宏观分析": "automated-research",
    "安全思维": "security-mindset",
}

# Tags that should auto-create new concepts (for Phase 2)
# Format: tag → {slug, domain, title}
AUTO_CONCEPT_TAGS: dict[str, dict] = {
    "金融科技": {"slug": "fintech", "title": "金融科技", "domain": "finance"},
    "银行业": {"slug": "banking", "title": "银行业", "domain": "finance"},
    "证券业": {"slug": "securities", "title": "证券业", "domain": "finance"},
    "金融监管": {"slug": "financial-regulation", "title": "金融监管", "domain": "finance"},
    "标准规范": {"slug": "standards", "title": "标准规范", "domain": "security"},
    "国标": {"slug": "national-standards", "title": "国标", "domain": "security"},
    "隐私": {"slug": "privacy", "title": "隐私", "domain": "security"},
    "加密": {"slug": "cryptography", "title": "加密", "domain": "security"},
    "防火墙": {"slug": "firewall", "title": "防火墙", "domain": "security"},
    "创业": {"slug": "entrepreneurship", "title": "创业", "domain": "startup"},
    "产品": {"slug": "product-management", "title": "产品管理", "domain": "startup"},
    "运营": {"slug": "operations", "title": "运营", "domain": "startup"},
    "增长": {"slug": "growth", "title": "增长", "domain": "startup"},
    "营销": {"slug": "marketing", "title": "营销", "domain": "startup"},
    "开源": {"slug": "open-source", "title": "开源", "domain": "dev"},
    "前端": {"slug": "frontend", "title": "前端开发", "domain": "dev"},
    "后端": {"slug": "backend", "title": "后端开发", "domain": "dev"},
    "数据库": {"slug": "database", "title": "数据库", "domain": "dev"},
    "DevOps": {"slug": "devops", "title": "DevOps", "domain": "dev"},
    "API": {"slug": "api", "title": "API", "domain": "dev"},
    "架构": {"slug": "architecture", "title": "架构", "domain": "dev"},
    "部署": {"slug": "deployment", "title": "部署", "domain": "dev"},
    "测试": {"slug": "testing", "title": "测试", "domain": "dev"},
    "投资": {"slug": "investment", "title": "投资", "domain": "finance"},
    "财经": {"slug": "finance-news", "title": "财经资讯", "domain": "finance"},
    "保险": {"slug": "insurance", "title": "保险", "domain": "finance"},
    "支付": {"slug": "payment", "title": "支付", "domain": "finance"},
    "AI产品": {"slug": "ai-product", "title": "AI产品", "domain": "ai"},
    "AI工具": {"slug": "ai-tools", "title": "AI工具", "domain": "ai"},
    "prompt": {"slug": "prompt-engineering", "title": "Prompt工程", "domain": "ai"},
    "独立开发": {"slug": "indie-dev", "title": "独立开发", "domain": "startup"},
    "教程实操": {"slug": "tutorials", "title": "教程实操", "domain": "general"},
    "技术原理": {"slug": "technical-principles", "title": "技术原理", "domain": "dev"},
    "安全审计": {"slug": "security-audit", "title": "安全审计", "domain": "security"},
    "等保": {"slug": "security-compliance", "title": "等保", "domain": "security"},
    "行业资讯": {"slug": "industry-news", "title": "行业资讯", "domain": "general"},
    "学习方法": {"slug": "learning-methods", "title": "学习方法", "domain": "startup"},
    "知识管理": {"slug": "knowledge-management", "title": "知识管理", "domain": "startup"},
    "设计生成": {"slug": "ai-design", "title": "AI设计", "domain": "ai"},
    "Claude": {"slug": "claude", "title": "Claude", "domain": "ai"},
    "DeepSeek": {"slug": "deepseek", "title": "DeepSeek", "domain": "ai"},
    "OpenAI": {"slug": "openai", "title": "OpenAI", "domain": "ai"},
    "Coding": {"slug": "coding", "title": "AI编程", "domain": "ai"},
    "多模态": {"slug": "multimodal", "title": "多模态", "domain": "ai"},
    "API": {"slug": "api", "title": "API", "domain": "dev"},
    "CISO": {"slug": "ciso", "title": "CISO", "domain": "security"},
    "工作汇报": {"slug": "work-report", "title": "工作汇报", "domain": "startup"},
    "金融科技": {"slug": "fintech", "title": "金融科技", "domain": "finance"},
    "金融监管": {"slug": "financial-regulation", "title": "金融监管", "domain": "finance"},
    "银行业": {"slug": "banking", "title": "银行业", "domain": "finance"},
    "证券业": {"slug": "securities", "title": "证券业", "domain": "finance"},
}


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def _get_existing_concept_slugs() -> set[str]:
    """Return set of existing concept slugs from the concepts directory."""
    if not CONCEPTS_DIR.exists():
        return set()
    return {f.stem for f in CONCEPTS_DIR.glob("*.md") if f.suffix == ".md" and f.stem != "graph"}


def _concept_md_path(slug: str) -> Path:
    return CONCEPTS_DIR / f"{slug}.md"


def _create_concept_md(slug: str, title: str, domain: str, source_item_ids: list[str]) -> bool:
    """Create a new concept .md file. Returns True if created, False if already exists."""
    path = _concept_md_path(slug)
    if path.exists():
        return False
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    content = f"""---
slug: "{slug}"
title: "{title}"
domain: "{domain}"
aliases: []
source_items: {json.dumps(source_item_ids)}
local_wiki_ref: null
updated_at: "{now}"
---

# {title}

## 定义

*待补充——自动创建*

## 相关知识条目

"""
    for item_id in source_item_ids:
        content += f"- [[{item_id}]]\n"
    path.write_text(content, encoding="utf-8")
    log.info(f"created new concept: {slug} ({title}) with {len(source_item_ids)} items")
    return True


def link_tags_to_concepts(tags: list[str]) -> list[str]:
    """Map a list of tags to concept slugs.

    Phase 1: Use TAG_TO_CONCEPT mapping.
    Returns list of concept slugs (may be empty).
    """
    slugs = []
    seen = set()
    for tag in tags:
        slug = TAG_TO_CONCEPT.get(tag)
        if slug and slug not in seen:
            slugs.append(slug)
            seen.add(slug)
    return slugs


def auto_create_concepts(tags: list[str], item_id: str) -> list[str]:
    """Auto-create new concept drafts for unmatched tags, return their slugs.

    Phase 2: For tags in AUTO_CONCEPT_TAGS that don't have existing .md files,
    create them.
    """
    existing = _get_existing_concept_slugs()
    created = []
    for tag in tags:
        info = AUTO_CONCEPT_TAGS.get(tag)
        if not info:
            continue
        slug = info["slug"]
        if slug in existing:
            continue
        if _create_concept_md(slug, info["title"], info["domain"], [item_id]):
            created.append(slug)
            existing.add(slug)  # prevent duplicate creation in the same batch
    return created


def update_item_concepts(
    item_id: str,
    tags: list[str],
) -> list[str]:
    """Full pipeline: link tags to concepts + auto-create new concepts.

    Returns final list of concept slugs for the item.
    """
    # Phase 1: link existing concepts
    concepts = link_tags_to_concepts(tags)

    # Phase 2: auto-create new concept drafts
    new_concepts = auto_create_concepts(tags, item_id)
    concepts.extend(new_concepts)

    # Deduplicate
    seen = set()
    deduped = []
    for c in concepts:
        if c not in seen:
            deduped.append(c)
            seen.add(c)

    return deduped


def batch_link_items(items: list[dict]) -> list[dict]:
    """Batch process items: link concepts for all items.

    Each item dict must have: id, tags.
    Mutates items in place, adding 'concepts' key.
    Returns items for chaining.
    """
    for item in items:
        tags = item.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        tags = [t for t in tags if t]

        # Only process items without concepts yet
        existing_concepts = item.get("concepts", [])
        if isinstance(existing_concepts, str):
            try:
                existing_concepts = json.loads(existing_concepts)
            except (json.JSONDecodeError, TypeError):
                existing_concepts = []
        if existing_concepts:
            continue  # Already has concepts

        concepts = update_item_concepts(item["id"], tags)
        item["concepts"] = concepts

    return items


__all__ = [
    "link_tags_to_concepts",
    "auto_create_concepts",
    "update_item_concepts",
    "batch_link_items",
]