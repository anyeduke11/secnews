"""Phase 1j Task 10.4: Batch compile 50 uncompiled knowledge items.

This script performs LLM-driven compilation (classification + concept extraction)
on 50 uncompiled items across all domains (ai/security/dev/finance/startup/general).

Compilation per item:
  Step 1: Classify (domain/topic/type/difficulty + tags) — LLM judgment
  Step 2: Extract 2-3 concepts (slug + title)
  Step 3: Update frontmatter.concepts
  Step 4: Update frontmatter.compiled = true

Then:
  - Create new concept .md files (domain-aware)
  - Sync to SQLite
  - Rebuild graph.json
  - Update _MAP.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.domain.knowledge_models import KnowledgeConcept, KnowledgeItem, now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.knowledge_sync import parse_frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ITEMS_DIR = PROJECT_ROOT / "knowledge" / "items"
CONCEPTS_DIR = PROJECT_ROOT / "knowledge" / "concepts"

# ── Compilation results (LLM judgment) ──────────────────────────
# Each entry: item_id → {domain, topic, type, difficulty, tags,
#                        concepts: [{slug, title}]}
COMPILED = {
    # ── Already classified by phase1j_groupx (need concepts + compiled) ──
    "4f3c7d046339": {
        "domain": "dev",
        "topic": "cs-curriculum",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["计算机科学", "开源课程", "GitHub", "学习资源"],
        "concepts": [
            {"slug": "cs-curriculum", "title": "计算机科学课程"},
            {"slug": "open-source-learning", "title": "开源学习资源"},
        ],
    },
    "4201940cd083": {
        "domain": "security",
        "topic": "vulnerability-database",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["漏洞库", "CNVD", "信息安全", "参考资料"],
        "concepts": [
            {"slug": "vulnerability-database", "title": "漏洞数据库"},
            {"slug": "security-fundamentals", "title": "安全基础"},
        ],
    },
    "898dd96c073c": {
        "domain": "finance",
        "topic": "private-equity",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["私募", "自购", "投资", "金融机构"],
        "concepts": [
            {"slug": "private-equity", "title": "私募股权"},
            {"slug": "investment", "title": "投资"},
        ],
    },
    "8c40203b708e": {
        "domain": "ai",
        "topic": "llm-cost",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["大模型", "Token成本", "银行AI", "成本控制"],
        "concepts": [
            {"slug": "llm-cost", "title": "大模型成本"},
            {"slug": "ai-finance", "title": "AI 金融应用"},
        ],
    },
    "c7500134ab49": {
        "domain": "general",
        "topic": "personal-website",
        "type": "opinion",
        "difficulty": "beginner",
        "tags": ["个人站点", "学习笔记", "随笔"],
        "concepts": [
            {"slug": "personal-knowledge", "title": "个人知识管理"},
            {"slug": "learning-notes", "title": "学习笔记"},
        ],
    },
    # ── New items: AI domain ──
    "23076240ea4a": {
        "domain": "ai",
        "topic": "ai-vulnerability-mining",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["AI安全", "漏洞挖掘", "小程序", "SRC", "自动化"],
        "concepts": [
            {"slug": "ai-vulnerability-mining", "title": "AI 漏洞挖掘"},
            {"slug": "bug-bounty", "title": "漏洞赏金"},
        ],
    },
    "0f19d127b1c7": {
        "domain": "ai",
        "topic": "ai-fundamentals",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["AI基础", "大模型", "核心概念", "入门指南", "深度解析"],
        "concepts": [
            {"slug": "ai-fundamentals", "title": "AI 基础概念"},
            {"slug": "llm-basics", "title": "大模型基础"},
        ],
    },
    "37b69931ba07": {
        "domain": "ai",
        "topic": "ai-applications",
        "type": "tutorial",
        "difficulty": "beginner",
        "tags": ["AI应用", "单兵AI", "销售", "行政", "财务"],
        "concepts": [
            {"slug": "ai-applications", "title": "AI 应用场景"},
            {"slug": "ai-productivity", "title": "AI 生产力工具"},
        ],
    },
    "d9cb75436a9d": {
        "domain": "ai",
        "topic": "ai-video-generation",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["AI视频", "Agent", "长视频", "产品发布", "Skill Hub"],
        "concepts": [
            {"slug": "ai-video-generation", "title": "AI 视频生成"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "a6a9b647ef1e": {
        "domain": "ai",
        "topic": "ai-coding",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["AI编程", "免费工具", "代码生成", "模型评测", "开发者工具"],
        "concepts": [
            {"slug": "ai-coding", "title": "AI 编程"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "2abc11638b79": {
        "domain": "ai",
        "topic": "ai-news-digest",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["AI资讯", "周报", "工具更新", "行业动态", "新闻摘要"],
        "concepts": [
            {"slug": "ai-news-digest", "title": "AI 资讯摘要"},
            {"slug": "industry-news", "title": "行业资讯"},
        ],
    },
    "d18de2ee42bf": {
        "domain": "ai",
        "topic": "ai-entrepreneurship",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["一人公司", "OPC", "AI产品", "公众号", "智能体"],
        "concepts": [
            {"slug": "ai-entrepreneurship", "title": "AI 创业"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "ab0fe0d7608c": {
        "domain": "ai",
        "topic": "agent-guide",
        "type": "reference",
        "difficulty": "intermediate",
        "tags": ["WorkBuddy", "Agent", "腾讯", "实战指南", "开源"],
        "concepts": [
            {"slug": "agent-guide", "title": "Agent 实战指南"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "04de48060135": {
        "domain": "ai",
        "topic": "self-hosted-agent",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["Octop", "自托管", "Agent", "腾讯云", "开源"],
        "concepts": [
            {"slug": "self-hosted-agent", "title": "自托管 Agent"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "16dc482aa286": {
        "domain": "ai",
        "topic": "llm-efficiency",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["Token密度", "大模型", "智能体", "效率优化", "万亿参数"],
        "concepts": [
            {"slug": "llm-efficiency", "title": "大模型效率"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "939fe1835768": {
        "domain": "ai",
        "topic": "browser-automation",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["浏览器自动化", "WorkBuddy", "反爬", "爬虫", "Skill"],
        "concepts": [
            {"slug": "browser-automation", "title": "浏览器自动化"},
            {"slug": "agent-skills", "title": "Agent Skills"},
        ],
    },
    "b97d060930ee": {
        "domain": "ai",
        "topic": "ai-security-attack",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["AI安全", "多智能体", "链式逃逸", "攻击模型", "对抗"],
        "concepts": [
            {"slug": "ai-driven-attack", "title": "AI 驱动攻击"},
            {"slug": "ai-security", "title": "AI 安全"},
        ],
    },
    "cefb71389b03": {
        "domain": "ai",
        "topic": "ai-supply-chain-security",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["Skills投毒", "免杀", "语义混淆", "供应链安全", "防御框架"],
        "concepts": [
            {"slug": "ai-supply-chain-security", "title": "AI 供应链安全"},
            {"slug": "ai-driven-security", "title": "AI 驱动安全"},
        ],
    },
    "2b525c5eec59": {
        "domain": "ai",
        "topic": "vulnerability-mining-agent",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["漏洞挖掘", "Agent", "客户端安全", "自动化", "架构设计"],
        "concepts": [
            {"slug": "ai-vulnerability-mining", "title": "AI 漏洞挖掘"},
            {"slug": "penetration-testing", "title": "渗透测试"},
        ],
    },
    "6da3013b2c36": {
        "domain": "ai",
        "topic": "agent-loop-design",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["Anthropic", "循环设计", "Agent", "Loop", "AI范式"],
        "concepts": [
            {"slug": "agent-loop-design", "title": "Agent 循环设计"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "af4479bdf78b": {
        "domain": "ai",
        "topic": "agent-infrastructure",
        "type": "product-announcement",
        "difficulty": "beginner",
        "tags": ["免费域名", "Agent", "公网访问", "HSK-CLI", "基础设施"],
        "concepts": [
            {"slug": "agent-infrastructure", "title": "Agent 基础设施"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "298f718fa9b4": {
        "domain": "ai",
        "topic": "ai-coding",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["Deep Code", "DeepSeek", "AI编程", "代码工具", "推荐"],
        "concepts": [
            {"slug": "ai-coding", "title": "AI 编程"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "4a62e2696ce4": {
        "domain": "ai",
        "topic": "llm-gateway",
        "type": "tool-comparison",
        "difficulty": "intermediate",
        "tags": ["AI网关", "免费Token", "模型聚合", "本地部署", "API"],
        "concepts": [
            {"slug": "llm-gateway", "title": "LLM 网关"},
            {"slug": "llm-cost", "title": "大模型成本"},
        ],
    },
    "7315232bd3d4": {
        "domain": "ai",
        "topic": "product-thinking",
        "type": "reference",
        "difficulty": "intermediate",
        "tags": ["产品经理", "思维模型", "Skill", "产品思维", "方法论"],
        "concepts": [
            {"slug": "product-thinking", "title": "产品思维"},
            {"slug": "learning-methods", "title": "学习方法"},
        ],
    },
    "cd04e53ebe2e": {
        "domain": "ai",
        "topic": "agentic-coding",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["Ornith", "Agentic Coding", "开源", "模型发布", "MIT"],
        "concepts": [
            {"slug": "agentic-coding", "title": "Agentic Coding"},
            {"slug": "ai-coding", "title": "AI 编程"},
        ],
    },
    "df1d3f61d0a8": {
        "domain": "ai",
        "topic": "subagent-architecture",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["Subagent", "模型委派", "架构设计", "任务分解", "OpenRouter"],
        "concepts": [
            {"slug": "subagent-architecture", "title": "Subagent 架构"},
            {"slug": "multi-agent-systems", "title": "多智能体系统"},
        ],
    },
    "658ae34ec9ee": {
        "domain": "ai",
        "topic": "ai-governance",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["AI治理", "API Key", "安全护栏", "成本控制", "模型升级"],
        "concepts": [
            {"slug": "ai-governance", "title": "AI 治理"},
            {"slug": "llm-cost", "title": "大模型成本"},
        ],
    },
    "c665a613aad4": {
        "domain": "ai",
        "topic": "llm-api-comparison",
        "type": "tool-comparison",
        "difficulty": "intermediate",
        "tags": ["LLM API", "免费", "对比", "Rate Limit", "成本分析"],
        "concepts": [
            {"slug": "llm-api-comparison", "title": "LLM API 对比"},
            {"slug": "llm-cost", "title": "大模型成本"},
        ],
    },
    "71dc479bfddb": {
        "domain": "ai",
        "topic": "ai-tools-overview",
        "type": "opinion",
        "difficulty": "beginner",
        "tags": ["AI工具", "2026", "工具选择", "洗牌", "效率"],
        "concepts": [
            {"slug": "ai-tools-overview", "title": "AI 工具概览"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "baebc69b3faf": {
        "domain": "ai",
        "topic": "agent-security-governance",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["TC260", "Agent安全", "生命周期", "部署指引", "合规"],
        "concepts": [
            {"slug": "agent-security-governance", "title": "Agent 安全治理"},
            {"slug": "compliance-regulation", "title": "合规与监管"},
        ],
    },
    "b3c0a491e490": {
        "domain": "ai",
        "topic": "ai-cloud-platform",
        "type": "product-announcement",
        "difficulty": "beginner",
        "tags": ["腾讯云", "EdgeOne", "免费Token", "AI部署", "云平台"],
        "concepts": [
            {"slug": "ai-cloud-platform", "title": "AI 云平台"},
            {"slug": "llm-cost", "title": "大模型成本"},
        ],
    },
    "6a10e0d75479": {
        "domain": "ai",
        "topic": "ai-coding-tool",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["Claude Code", "Anthropic", "一周年", "Agent", "软件开发"],
        "concepts": [
            {"slug": "ai-coding", "title": "AI 编程"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "3d82bb1020f4": {
        "domain": "ai",
        "topic": "ai-vulnerability-hunting",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["AI漏洞挖掘", "Copilot", "Claude", "ClickHouse", "Bug Bounty"],
        "concepts": [
            {"slug": "ai-vulnerability-mining", "title": "AI 漏洞挖掘"},
            {"slug": "penetration-testing", "title": "渗透测试"},
        ],
    },
    "3ea8f384fe60": {
        "domain": "ai",
        "topic": "agent-loop",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["Claude Code", "智能体循环", "Agent", "入门教程", "Loop"],
        "concepts": [
            {"slug": "agent-loop-design", "title": "Agent 循环设计"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "7dbe5a95957b": {
        "domain": "ai",
        "topic": "agent-loop",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["Agent Loop", "Turn-based", "Goal-based", "Time-based", "Proactive"],
        "concepts": [
            {"slug": "agent-loop-design", "title": "Agent 循环设计"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "c720a169ed09": {
        "domain": "ai",
        "topic": "ai-security-operations",
        "type": "news",
        "difficulty": "intermediate",
        "tags": ["Qwen3.7", "AI安全", "暴力破解", "入侵检测", "自动化响应"],
        "concepts": [
            {"slug": "ai-security-operations", "title": "AI 安全运营"},
            {"slug": "ai-driven-security", "title": "AI 驱动安全"},
        ],
    },
    "ab32b5c4e649": {
        "domain": "ai",
        "topic": "llm-model-evaluation",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["MiniMax", "M3", "模型评测", "执行层", "Claude Code"],
        "concepts": [
            {"slug": "llm-model-evaluation", "title": "LLM 模型评测"},
            {"slug": "ai-coding", "title": "AI 编程"},
        ],
    },
    "f1de94d918e2": {
        "domain": "ai",
        "topic": "agent-security-standard",
        "type": "news",
        "difficulty": "intermediate",
        "tags": ["网络安全标准", "智能体", "部署安全", "实践指南", "官方通知"],
        "concepts": [
            {"slug": "agent-security-governance", "title": "Agent 安全治理"},
            {"slug": "compliance-regulation", "title": "合规与监管"},
        ],
    },
    # ── New items: dev domain ──
    "a2ad2bb1f182": {
        "domain": "dev",
        "topic": "agent-skills",
        "type": "tool-comparison",
        "difficulty": "intermediate",
        "tags": ["OPC", "Skills", "开源", "一人公司", "市场调研"],
        "concepts": [
            {"slug": "agent-skills", "title": "Agent Skills"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "2664f9c30629": {
        "domain": "dev",
        "topic": "ai-creation-tools",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["AI创作", "开源项目", "革命", "工具", "创新"],
        "concepts": [
            {"slug": "ai-creation-tools", "title": "AI 创作工具"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "c71f419768a1": {
        "domain": "dev",
        "topic": "markdown-tools",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["Rust", "Markdown", "开源", "AI工具", "轻量级"],
        "concepts": [
            {"slug": "markdown-tools", "title": "Markdown 工具"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
    "89b8fcf76698": {
        "domain": "dev",
        "topic": "knowledge-architecture",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["知识管理", "AI工程", "知识分层", "护城河", "交付团队"],
        "concepts": [
            {"slug": "knowledge-architecture", "title": "知识架构"},
            {"slug": "knowledge-management", "title": "知识管理"},
        ],
    },
    # ── New items: security domain ──
    "3381eeaee1a5": {
        "domain": "security",
        "topic": "llm-api",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["Cloudflare", "免费API", "模型调用", "AI服务", "CDN"],
        "concepts": [
            {"slug": "llm-api", "title": "LLM API"},
            {"slug": "llm-cost", "title": "大模型成本"},
        ],
    },
    "f155176922e6": {
        "domain": "security",
        "topic": "self-media-platform",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["自媒体", "数据源", "开源", "全平台", "管理平台"],
        "concepts": [
            {"slug": "self-media-platform", "title": "自媒体平台"},
            {"slug": "data-skill", "title": "数据技能"},
        ],
    },
    "4434b053e162": {
        "domain": "security",
        "topic": "ai-app-development",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["微信小程序", "对话编程", "AI开发", "部署", "教程"],
        "concepts": [
            {"slug": "ai-app-development", "title": "AI 应用开发"},
            {"slug": "ai-coding", "title": "AI 编程"},
        ],
    },
    "3fca0b6f0cdd": {
        "domain": "security",
        "topic": "ai-security-operations",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["AI安全", "安全运营", "平台", "全栈AI", "Agent"],
        "concepts": [
            {"slug": "ai-security-operations", "title": "AI 安全运营"},
            {"slug": "ai-driven-security", "title": "AI 驱动安全"},
        ],
    },
    "eadc2bf70243": {
        "domain": "security",
        "topic": "security-industry-report",
        "type": "reference",
        "difficulty": "intermediate",
        "tags": ["数字安全", "产业报告", "2026", "行业分析", "白皮书"],
        "concepts": [
            {"slug": "security-industry-report", "title": "安全产业报告"},
            {"slug": "industry-news", "title": "行业资讯"},
        ],
    },
    "398e3ab6a596": {
        "domain": "security",
        "topic": "sensitive-info-detection",
        "type": "tool-comparison",
        "difficulty": "intermediate",
        "tags": ["敏感信息", "DigDeep", "自动化检测", "渗透测试", "代码审计"],
        "concepts": [
            {"slug": "sensitive-info-detection", "title": "敏感信息检测"},
            {"slug": "penetration-testing", "title": "渗透测试"},
        ],
    },
    # ── New items: startup domain ──
    "220153a0211f": {
        "domain": "startup",
        "topic": "data-skill",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["数据Skill", "自媒体", "数据源", "全平台", "管理工具"],
        "concepts": [
            {"slug": "data-skill", "title": "数据技能"},
            {"slug": "agent-skills", "title": "Agent Skills"},
        ],
    },
    "9e957f11f627": {
        "domain": "startup",
        "topic": "frontend-skills",
        "type": "reference",
        "difficulty": "intermediate",
        "tags": ["GitHub", "前端开发", "Skill", "动效", "交互设计"],
        "concepts": [
            {"slug": "frontend-skills", "title": "前端技能"},
            {"slug": "developer-tools", "title": "开发者工具"},
        ],
    },
}


def _update_item_frontmatter(item_id: str, compiled_data: dict) -> None:
    """Update item .md frontmatter with compilation results."""
    path = ITEMS_DIR / f"{item_id}.md"
    if not path.exists():
        print(f"  WARN: {item_id}.md not found, skipping")
        return

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        print(f"  WARN: {item_id}.md has no frontmatter, skipping")
        return

    parts = text.split("---", 2)
    if len(parts) < 3:
        return
    frontmatter = parts[1]
    body = parts[2]

    concept_slugs = [c["slug"] for c in compiled_data["concepts"]]

    # Update or insert each field
    updates = {
        "compiled": "true",
        "domain": compiled_data["domain"],
        "topic": compiled_data["topic"],
        "type": compiled_data["type"],
        "difficulty": compiled_data["difficulty"],
        "tags": json.dumps(compiled_data["tags"], ensure_ascii=False),
        "concepts": json.dumps(concept_slugs, ensure_ascii=False),
    }

    for key, value in updates.items():
        pattern = rf"^({key}:).*$"
        replacement = f"{key}: {value}"
        if re.search(pattern, frontmatter, re.MULTILINE):
            frontmatter = re.sub(pattern, replacement, frontmatter, flags=re.MULTILINE)
        else:
            frontmatter = frontmatter.rstrip() + f"\n{key}: {value}\n"

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")
    print(f"  ✓ updated frontmatter: {item_id}")


def _ensure_concept_md(slug: str, title: str, domain: str, source_item_id: str) -> bool:
    """Create concept .md if it doesn't exist. Returns True if created."""
    path = CONCEPTS_DIR / f"{slug}.md"
    if path.exists():
        # Append source_item_id to existing concept's source_items
        existing_fm = parse_frontmatter(path) or {}
        existing_sources = (
            existing_fm.get("source_items", [])
            if isinstance(existing_fm.get("source_items"), list)
            else []
        )
        if source_item_id not in existing_sources:
            existing_sources.append(source_item_id)
            _update_concept_source_items(path, existing_sources)
        return False

    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    now = now_iso()
    frontmatter = f"""---
slug: "{slug}"
title: "{title}"
domain: "{domain}"
source_items: {json.dumps([source_item_id])}
local_wiki_ref: null
updated_at: "{now}"
---

# {title}

> 自动编译生成（Phase 1j Task 10.4）

## 概述

（待补充）

## 关键要点

（待补充）

## 参考条目

- [[{source_item_id}]]
"""
    path.write_text(frontmatter, encoding="utf-8")
    print(f"  ✓ created concept: {slug}")
    return True


def _update_concept_source_items(path: Path, source_items: list[str]) -> None:
    """Update source_items line in concept .md frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    parts = text.split("---", 2)
    if len(parts) < 3:
        return
    frontmatter = parts[1]
    body = parts[2]
    frontmatter = re.sub(
        r"^source_items:.*$",
        f"source_items: {json.dumps(source_items, ensure_ascii=False)}",
        frontmatter,
        flags=re.MULTILINE,
    )
    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")


def _sync_item_to_db(item_id: str, compiled_data: dict) -> None:
    """Update SQLite with compiled fields."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        print(f"  WARN: {item_id} not in DB, skipping DB sync")
        return

    item.domain = compiled_data["domain"]
    item.topic = compiled_data["topic"]
    item.type = compiled_data["type"]
    item.difficulty = compiled_data["difficulty"]
    item.tags = compiled_data["tags"]
    item.concepts = [c["slug"] for c in compiled_data["concepts"]]
    item.compiled = True
    item.updated_at = now_iso()
    knowledge_repo.upsert_item(item)
    print(f"  ✓ synced to DB: {item_id}")


def _sync_concept_to_db(slug: str, title: str, domain: str) -> None:
    """Upsert concept to SQLite."""
    path = CONCEPTS_DIR / f"{slug}.md"
    fm = parse_frontmatter(path) if path.exists() else None
    source_items = (
        fm.get("source_items", []) if fm and isinstance(fm.get("source_items"), list) else []
    )
    concept = KnowledgeConcept(
        slug=slug,
        title=title,
        domain=domain,
        source_items=source_items,
        local_wiki_ref=None,
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_concept(concept)


def main() -> None:
    print("=" * 60)
    print("Phase 1j Task 10.4: Batch compile 50 uncompiled items")
    print("=" * 60)

    # Get existing concept slugs
    existing_concepts = set()
    if CONCEPTS_DIR.exists():
        for f in CONCEPTS_DIR.glob("*.md"):
            existing_concepts.add(f.stem)
    print(f"\nExisting concepts: {len(existing_concepts)}")

    compiled_count = 0
    new_concepts_count = 0
    skipped = 0

    for item_id, data in COMPILED.items():
        print(f"\n--- Compiling {item_id} ---")
        path = ITEMS_DIR / f"{item_id}.md"
        if not path.exists():
            print(f"  WARN: {item_id}.md not found, skipping")
            skipped += 1
            continue
        # Step 1-4: Update .md frontmatter
        _update_item_frontmatter(item_id, data)
        # Sync to SQLite
        _sync_item_to_db(item_id, data)
        compiled_count += 1

        # Create new concept .md files
        for concept in data["concepts"]:
            slug = concept["slug"]
            title = concept["title"]
            domain = data["domain"]
            created = _ensure_concept_md(slug, title, domain, item_id)
            if created:
                new_concepts_count += 1
            _sync_concept_to_db(slug, title, domain)

    print(f"\n{'=' * 60}")
    print(f"Compiled: {compiled_count} items")
    print(f"New concepts: {new_concepts_count}")
    print(f"Skipped: {skipped}")
    print(f"{'=' * 60}")

    # Rebuild graph.json
    print("\nRebuilding graph.json...")
    from backend.services.graph_builder import build_graph
    graph = build_graph(domain=None, include_local=True)
    graph_path = CONCEPTS_DIR / "graph.json"
    graph_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✓ graph.json: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    # Update _MAP.md
    print("\nUpdating _MAP.md...")
    from backend.services.map_updater import update_map
    stats = update_map()
    print(f"  ✓ _MAP.md updated: {stats}")

    # Final stats
    total_items = knowledge_repo.count_items()
    compiled_total = knowledge_repo.count_items(compiled=True)
    ratio = compiled_total / total_items if total_items > 0 else 0
    print(f"\n{'=' * 60}")
    print(f"Total items: {total_items}")
    print(f"Compiled: {compiled_total} (ratio: {ratio:.1%})")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
