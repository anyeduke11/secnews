"""v1.7 Phase 1 三层标签提取器 — ExtractService.

PRD §4.2 Phase 1 / §6.3

三层提取 (置信度递减):
1. 正则提取 (confidence 1.0): CVE-2026-1234 → cve
2. 关键词提取 (confidence 0.7-0.8): "LangChain" → langchain
3. 分类→域映射 (confidence 0.5): category=ai → ai-security/llm

输出: [{"tag_id": "cve", "confidence": 1.0}, ...]
去重规则: 同一 tag_id 取最高置信度.

后续 Task 1.6b Extract API 会调用本模块, 将结果写入 hotspot_tags (pending → confirm).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_PATH = BASE_DIR / "data" / "tag_rules.json"

# 分类 → 域标签映射 (PRD §6.3)
CATEGORY_DOMAIN_MAP: dict[str, list[str]] = {
    "ai": ["ai-security", "llm"],
    "security": ["cve", "vulnerability", "network-security"],
    "finance": ["finance"],
    "startup": ["startup"],
    "bid": ["bid"],
    "tech": ["tech"],
    "github": ["github", "tech"],
}

_rules_cache: list[dict] | None = None


def _load_rules() -> list[dict]:
    """加载 tag_rules.json (带缓存, 进程内只读一次)."""
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache
    if not RULES_PATH.exists():
        _rules_cache = []
        return _rules_cache
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        _rules_cache = data.get("rules", [])
    except (json.JSONDecodeError, OSError):
        _rules_cache = []
    return _rules_cache


def _reload_rules() -> list[dict]:
    """强制重新加载规则 (测试用)."""
    global _rules_cache
    _rules_cache = None
    return _load_rules()


def _regex_extract(text: str, rules: list[dict]) -> list[dict]:
    """第一层: 正则匹配, 置信度最高."""
    out: list[dict] = []
    for rule in rules:
        pattern = rule.get("pattern")
        if pattern and re.search(pattern, text, re.IGNORECASE):
            out.append({"tag_id": rule["tag_id"], "confidence": rule.get("confidence", 1.0)})
    return out


def _keyword_extract(text: str, rules: list[dict]) -> list[dict]:
    """第二层: 关键词包含匹配."""
    out: list[dict] = []
    lower = text.lower()
    for rule in rules:
        keywords = rule.get("keywords", [])
        if not keywords:
            continue
        if any(kw.lower() in lower for kw in keywords):
            out.append({"tag_id": rule["tag_id"], "confidence": rule.get("confidence", 0.7)})
    return out


def _category_domain_extract(category: str) -> list[dict]:
    """第三层: 分类 → 域标签映射 (置信度最低)."""
    out: list[dict] = []
    for tag_id in CATEGORY_DOMAIN_MAP.get(category, []):
        out.append({"tag_id": tag_id, "confidence": 0.5})
    return out


def extract_tags(text: str, title: str = "", category: str = "") -> list[dict]:
    """三层提取入口.

    Args:
        text: 文章正文 / 摘要
        title: 标题 (会拼接到 text 前提取)
        category: hotspots.category (ai/security/finance/...)

    Returns:
        [{"tag_id": "cve", "confidence": 1.0}, ...] 去重后, 按 confidence 降序
    """
    if not text and not title:
        return []
    rules = _load_rules()
    combined = f"{title} {text}" if title else text

    results: list[dict] = []
    results.extend(_regex_extract(combined, rules))
    results.extend(_keyword_extract(combined, rules))
    if category:
        results.extend(_category_domain_extract(category))

    # 去重: 同一 tag_id 取最高置信度
    merged: dict[str, float] = {}
    for r in results:
        tid = r["tag_id"]
        merged[tid] = max(merged.get(tid, 0.0), r["confidence"])

    # 按 confidence 降序排序
    return [
        {"tag_id": k, "confidence": v}
        for k, v in sorted(merged.items(), key=lambda x: -x[1])
    ]


def extract_and_attach(
    hotspot_id: str,
    text: str,
    title: str = "",
    category: str = "",
    min_confidence: float = 0.5,
) -> list[dict]:
    """提取标签并自动关联到热点 (confidence >= min_confidence 才关联).

    Returns:
        实际关联的标签列表 [{tag_id, confidence}]
    """
    from backend.repository.tags_repo import TagRepository

    all_tags = extract_tags(text, title, category)
    to_attach = [t for t in all_tags if t["confidence"] >= min_confidence]
    if to_attach:
        repo = TagRepository()
        for t in to_attach:
            # 仅当标签存在于 tags 表时才关联 (避免引用不存在的 tag)
            if repo.get(t["tag_id"]):
                repo.attach(hotspot_id, t["tag_id"], t["confidence"])
    return to_attach
