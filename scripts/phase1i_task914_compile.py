"""Phase 1i Task 9.14: Batch compile PoC — 10 security items.

This script performs LLM-driven compilation (classification + concept extraction)
on 10 uncompiled security-domain items. It is a one-shot PoC script.

Compilation per item:
  Step 1: Classify (domain/topic/type/difficulty + tags) — LLM judgment
  Step 2: Extract 2-3 concepts (slug + title)
  Step 3: Update frontmatter.concepts
  Step 4: Update frontmatter.compiled = true

Then:
  - Create new concept .md files
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
# Each entry: item_id → {topic, type, difficulty, tags, concepts: [{slug, title}]}
COMPILED = {
    "53c6022766fd": {
        "topic": "compliance-regulation",
        "type": "news-digest",
        "difficulty": "beginner",
        "tags": ["合规", "监管", "网络安全法", "国家标准", "金融监管"],
        "concepts": [
            {"slug": "compliance-regulation", "title": "合规与监管"},
            {"slug": "financial-regulation", "title": "金融监管"},
            {"slug": "national-standards", "title": "国家标准"},
        ],
    },
    "a4ff8cbd3c74": {
        "topic": "api-monetization",
        "type": "product-announcement",
        "difficulty": "intermediate",
        "tags": ["Cloudflare", "x402", "API monetization", "stablecoin", "MCP"],
        "concepts": [
            {"slug": "api-monetization", "title": "API 货币化"},
            {"slug": "payment-gateway", "title": "支付网关"},
        ],
    },
    "b5e3d65f73d2": {
        "topic": "app-security-compliance",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["App安全", "银行", "通报", "监管", "民生银行"],
        "concepts": [
            {"slug": "app-security-compliance", "title": "App 安全合规"},
            {"slug": "banking", "title": "银行业务"},
            {"slug": "financial-regulation", "title": "金融监管"},
        ],
    },
    "afe527e5fc37": {
        "topic": "multi-agent-systems",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["多智能体", "AI", "LLM", "模型协作", "agent"],
        "concepts": [
            {"slug": "multi-agent-systems", "title": "多智能体系统"},
            {"slug": "ai-agent", "title": "AI Agent"},
        ],
    },
    "12fef42a2aa4": {
        "topic": "log-management",
        "type": "tool-comparison",
        "difficulty": "intermediate",
        "tags": ["日志存储", "ELK", "Loki", "开源工具", "可观测性"],
        "concepts": [
            {"slug": "log-management", "title": "日志管理"},
            {"slug": "observability", "title": "可观测性"},
        ],
    },
    "1d969fa66a40": {
        "topic": "devsecops",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["研发安全", "DevSecOps", "安全检测", "混沌工程", "自助式安全"],
        "concepts": [
            {"slug": "devsecops", "title": "DevSecOps"},
            {"slug": "security-fundamentals", "title": "安全基础"},
        ],
    },
    "a8ea6cb5ebc9": {
        "topic": "prompt-engineering",
        "type": "analysis",
        "difficulty": "advanced",
        "tags": ["提示词工程", "元提示", "prompt", "LLM", "自动生成"],
        "concepts": [
            {"slug": "prompt-engineering", "title": "提示词工程"},
            {"slug": "meta-prompting", "title": "元提示"},
        ],
    },
    "6154f9ea945f": {
        "topic": "security-sales",
        "type": "opinion",
        "difficulty": "beginner",
        "tags": ["售前", "销售", "安全方案", "客户沟通", "职场"],
        "concepts": [
            {"slug": "security-sales", "title": "安全售前与销售"},
            {"slug": "security-mindset", "title": "安全思维"},
        ],
    },
    "262220bf10d8": {
        "topic": "internet-governance",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["网信办", "互联网信息服务", "监管", "征求意见", "合规"],
        "concepts": [
            {"slug": "internet-governance", "title": "互联网治理"},
            {"slug": "compliance-regulation", "title": "合规与监管"},
        ],
    },
    "358bb8334d53": {
        "topic": "periodical-index",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["杂志", "期刊", "网络安全", "目录", "参考资料"],
        "concepts": [
            {"slug": "security-periodical", "title": "安全期刊"},
            {"slug": "industry-news", "title": "行业资讯"},
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


def _ensure_concept_md(slug: str, title: str, source_item_id: str) -> bool:
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
domain: "security"
source_items: {json.dumps([source_item_id])}
local_wiki_ref: null
updated_at: "{now}"
---

# {title}

> 自动编译生成（Phase 1i Task 9.14 PoC）

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

    item.topic = compiled_data["topic"]
    item.type = compiled_data["type"]
    item.difficulty = compiled_data["difficulty"]
    item.tags = compiled_data["tags"]
    item.concepts = [c["slug"] for c in compiled_data["concepts"]]
    item.compiled = True
    item.updated_at = now_iso()
    knowledge_repo.upsert_item(item)
    print(f"  ✓ synced to DB: {item_id}")


def _sync_concept_to_db(slug: str, title: str) -> None:
    """Upsert concept to SQLite."""
    path = CONCEPTS_DIR / f"{slug}.md"
    fm = parse_frontmatter(path) if path.exists() else None
    source_items = (
        fm.get("source_items", []) if fm and isinstance(fm.get("source_items"), list) else []
    )
    concept = KnowledgeConcept(
        slug=slug,
        title=title,
        domain="security",
        source_items=source_items,
        local_wiki_ref=None,
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_concept(concept)


def main() -> None:
    print("=" * 60)
    print("Phase 1i Task 9.14: Batch compile PoC — 10 security items")
    print("=" * 60)

    # Get existing concept slugs
    existing_concepts = set()
    if CONCEPTS_DIR.exists():
        for f in CONCEPTS_DIR.glob("*.md"):
            existing_concepts.add(f.stem)
    print(f"\nExisting concepts: {len(existing_concepts)}")

    compiled_count = 0
    new_concepts_count = 0

    for item_id, data in COMPILED.items():
        print(f"\n--- Compiling {item_id} ---")
        # Step 1-4: Update .md frontmatter
        _update_item_frontmatter(item_id, data)
        # Sync to SQLite
        _sync_item_to_db(item_id, data)
        compiled_count += 1

        # Create new concept .md files
        for concept in data["concepts"]:
            slug = concept["slug"]
            title = concept["title"]
            created = _ensure_concept_md(slug, title, item_id)
            if created:
                new_concepts_count += 1
            _sync_concept_to_db(slug, title)

    print(f"\n{'=' * 60}")
    print(f"Compiled: {compiled_count} items")
    print(f"New concepts: {new_concepts_count}")
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
    update_map()
    print("  ✓ _MAP.md updated")

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
