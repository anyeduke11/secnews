"""Concept linker — map item tags to knowledge concepts, auto-create new concepts.

Design
------
Phase 1: Tag→concept matching (existing concepts)
Phase 2: Auto-create concept drafts for unmatched high-frequency tags
Phase 3: Update item frontmatter with concept associations
Phase 4 (v0.5 M3.5): Runtime fill ``llm-wiki-2.0/graph.json`` — 6 typed edges.
  - ``uses`` 边由条目→概念共现自动累积 (weight=共现次数, source_observation_count=支撑条目数)
  - 其余 5 种边 (depends/contradicts/caused/fixed/supersedes) 保留人工/LLM 标注, 不覆盖
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("hotspot.concept_linker")

# ═══════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
ITEMS_DIR = KNOWLEDGE_DIR / "items"

# v0.5: llm-wiki-2.0 知识图谱主存储 (SPEC §18.2 强约束 1: 知识写入唯一路径)
LLM_WIKI_DIR = Path(__file__).resolve().parent.parent.parent / "llm-wiki-2.0"
GRAPH_PATH = LLM_WIKI_DIR / "graph.json"

# 6 种 typed relationships (SPEC §18 / wiki v2 §10.12)
EDGE_TYPES: tuple[str, ...] = (
    "uses", "depends", "contradicts", "caused", "fixed", "supersedes",
)

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
    "CISO": {"slug": "ciso", "title": "CISO", "domain": "security"},
    "工作汇报": {"slug": "work-report", "title": "工作汇报", "domain": "startup"},
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

    Side effect (v0.5 M3.5 Task13): after linking, accumulates the batch's
    item→concept co-occurrence into ``llm-wiki-2.0/graph.json`` (``uses`` edges).
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

    # v0.5 M3.5 Task13: 运行时填入 graph.json (uses 边, 共现累积)
    try:
        update_graph_from_batch(items)
    except Exception as e:
        log.warning(f"graph.json update skipped: {e}")

    return items


# ═══════════════════════════════════════════════════════════════
# v0.5 M3.5 Task13 — llm-wiki-2.0/graph.json 运行时填充 (6 种边)
# ═══════════════════════════════════════════════════════════════

def _load_graph() -> dict:
    """加载 llm-wiki-2.0/graph.json; 缺失/损坏时返回空 schema 骨架。"""
    if not GRAPH_PATH.exists():
        return {"$schema_version": "0.5.0", "nodes": [], "edges": []}
    try:
        return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"graph.json unreadable, returning empty: {e}")
        return {"$schema_version": "0.5.0", "nodes": [], "edges": []}


def _atomic_write_graph(graph: dict) -> None:
    """原子写 graph.json (.tmp → os.replace), 与 wiki_archiver 同一模式。"""
    import os

    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GRAPH_PATH.with_suffix(GRAPH_PATH.suffix + ".tmp")
    tmp.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, GRAPH_PATH)


def update_graph_from_item(item_id: str, concepts: list[str]) -> dict:
    """把单个条目的概念共现累积进 graph.json (``uses`` 边)。

    每个条目概念对 (c1, c2) 生成/递增一条 ``uses`` 边:
    - weight: 共现次数
    - source_observation_count: 支撑条目数
    已存在的非 uses 边 (depends/contradicts/caused/fixed/supersedes) 原样保留,
    不覆盖人工/LLM 标注。

    Returns: {"nodes", "edges", "updated"} 统计。
    """
    concepts = [c for c in (concepts or []) if c]
    if len(concepts) < 2:
        g = _load_graph()
        return {
            "nodes": len(g.get("nodes", [])),
            "edges": len(g.get("edges", [])),
            "updated": 0,
        }

    graph = _load_graph()
    nodes: dict[str, dict] = {n["id"]: n for n in graph.get("nodes", [])}
    for c in concepts:
        if c not in nodes:
            nodes[c] = {
                "id": c, "label": c, "domain": None,
                "count": 0, "wiki": "hotspot", "type": "concept",
            }

    edge_map: dict[tuple[str, str, str], dict] = {}
    for e in graph.get("edges", []):
        if isinstance(e, dict):
            edge_map[(e["source"], e["target"], e.get("type", "uses"))] = e

    updated = 0
    for i, c1 in enumerate(concepts):
        for c2 in concepts[i + 1:]:
            src, tgt = sorted([str(c1), str(c2)])
            key = (src, tgt, "uses")
            if key in edge_map:
                edge_map[key]["weight"] = int(edge_map[key].get("weight", 0)) + 1
                edge_map[key]["source_observation_count"] = (
                    int(edge_map[key].get("source_observation_count", 1)) + 1
                )
            else:
                edge_map[key] = {
                    "source": src, "target": tgt, "weight": 1,
                    "type": "uses", "source_observation_count": 1,
                }
            updated += 1

    graph["nodes"] = list(nodes.values())
    graph["edges"] = list(edge_map.values())
    _atomic_write_graph(graph)
    return {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "updated": updated,
    }


def update_graph_from_batch(items: list[dict]) -> dict:
    """批量累积多条目的概念共现进 graph.json。幂等 (重复跑只递增 weight)。

    Args:
        items: 每个含 ``id`` + ``concepts`` 的 dict

    Returns: {"nodes", "edges", "updated", "items"} 统计。
    """
    stats = {"nodes": 0, "edges": 0, "updated": 0, "items": 0}
    for item in items:
        concepts = item.get("concepts") or []
        if isinstance(concepts, str):
            try:
                concepts = json.loads(concepts)
            except (json.JSONDecodeError, TypeError):
                concepts = []
        concepts = [c for c in concepts if c]
        if len(concepts) < 2:
            continue
        item_stats = update_graph_from_item(item.get("id", ""), concepts)
        stats["updated"] += item_stats["updated"]
        stats["items"] += 1
    final = _load_graph()
    stats["nodes"] = len(final.get("nodes", []))
    stats["edges"] = len(final.get("edges", []))
    return stats


def validate_graph_schema(graph: dict) -> list[str]:
    """校验 graph.json schema (6 种边 + weight + source_observation_count + 节点引用)。

    Args:
        graph: 反序列化后的 graph.json dict

    Returns:
        错误字符串列表; 空 = 校验通过。
    """
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph.json 顶层必须是 JSON object"]

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list):
        return ["nodes 必须是数组"]
    if not isinstance(edges, list):
        return ["edges 必须是数组"]

    node_ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict) or not n.get("id"):
            errors.append(f"无效节点: {n!r}")
        else:
            node_ids.add(str(n["id"]))

    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        if not isinstance(e, dict):
            errors.append(f"无效边: {e!r}")
            continue
        etype = e.get("type")
        src, tgt = str(e.get("source", "")), str(e.get("target", ""))
        if etype not in EDGE_TYPES:
            errors.append(f"边 {src}→{tgt} 类型非法: {etype!r} (允许 {EDGE_TYPES})")
        if not isinstance(e.get("weight"), (int, float)) or e.get("weight", 0) < 1:
            errors.append(f"边 {src}→{tgt} 缺少/非法 weight")
        if not isinstance(e.get("source_observation_count"), (int, float)) or e.get("source_observation_count", 0) < 1:
            errors.append(f"边 {src}→{tgt} 缺少/非法 source_observation_count")
        if src not in node_ids:
            errors.append(f"边 source {src!r} 不在 nodes 中")
        if tgt not in node_ids:
            errors.append(f"边 target {tgt!r} 不在 nodes 中")
        key = (src, tgt, str(etype))
        if key in seen:
            errors.append(f"重复边 {src}→{tgt} ({etype})")
        seen.add(key)
    return errors


__all__ = [
    "EDGE_TYPES",
    "GRAPH_PATH",
    "auto_create_concepts",
    "batch_link_items",
    "link_tags_to_concepts",
    "update_graph_from_batch",
    "update_graph_from_item",
    "update_item_concepts",
    "validate_graph_schema",
]