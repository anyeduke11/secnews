"""SOUL.md service — read / regenerate role profile from real data."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.domain.knowledge_models import now_iso

log = logging.getLogger("hotspot.soul")

SOUL_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge" / "SOUL.md"
PENDING_DIR = SOUL_PATH.parent / "learning" / "tasks" / "pending"


def get_soul() -> dict:
    """Read SOUL.md. Create default template on first access."""
    if not SOUL_PATH.exists():
        content = _generate_soul_content()
        SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SOUL_PATH.write_text(content, encoding="utf-8")
        log.info("created SOUL.md")
        return {"content": content, "exists": False}
    return {"content": SOUL_PATH.read_text(encoding="utf-8"), "exists": True}


def create_soul_task() -> dict:
    """Regenerate SOUL.md inline from current data (no Agent needed)."""
    content = _generate_soul_content()
    SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOUL_PATH.write_text(content, encoding="utf-8")
    log.info("regenerated SOUL.md from data")
    return {"status": "done", "message": "SOUL.md regenerated from current knowledge data"}


def _generate_soul_content() -> str:
    """Generate SOUL.md content from current knowledge item statistics."""
    import sqlite3

    from backend.repository.db import get_connection
    from backend.repository.knowledge_repo import knowledge_repo

    items = knowledge_repo.list_items(limit=10000)
    concepts = knowledge_repo.list_concepts()

    total = len(items)
    with_domain = sum(1 for i in items if i.domain)
    with_concepts = sum(1 for i in items if i.concepts)
    compiled = sum(1 for i in items if i.compiled)
    orphan_items = knowledge_repo.count_orphan_items()

    # Domain distribution
    domain_counts: dict[str, int] = {}
    for item in items:
        d = item.domain or "未知"
        domain_counts[d] = domain_counts.get(d, 0) + 1

    # Domain label mapping
    DOMAIN_LABELS: dict[str, str] = {
        "security": "网络安全",
        "ai": "人工智能",
        "startup": "独立开发/创业",
        "finance": "金融/投资",
        "dev": "开发技术",
        "business": "企业管理",
        "general": "综合",
        "other": "其他",
    }

    # Concept by domain
    CONCEPT_DOMAIN_LABELS: dict[str, str] = {
        "security": "安全",
        "ai": "AI",
        "startup": "创业",
        "finance": "金融",
        "dev": "技术",
        "business": "管理",
        "general": "通用",
    }

    # Type distribution
    type_counts: dict[str, int] = {}
    for item in items:
        t = item.type or "未知"
        type_counts[t] = type_counts.get(t, 0) + 1

    # Difficulty distribution
    diff_counts: dict[str, int] = {}
    for item in items:
        d = item.difficulty or "未知"
        diff_counts[d] = diff_counts.get(d, 0) + 1

    # Concept by domain
    concept_by_domain: dict[str, list[str]] = {}
    for c in concepts:
        d = c.domain or "未知"
        if d not in concept_by_domain:
            concept_by_domain[d] = []
        concept_by_domain[d].append(c.title)

    # Build domain table
    domain_rows = ""
    domain_order = sorted(domain_counts.items(), key=lambda x: -x[1])
    for domain, count in domain_order:
        if domain == "未知":
            continue
        label = DOMAIN_LABELS.get(domain, domain)
        domain_rows += f"| {label} | — | {count} | 持续更新中 |\n"

    # Build concept table
    concept_rows = ""
    for d, names in sorted(concept_by_domain.items()):
        c_label = CONCEPT_DOMAIN_LABELS.get(d, d)
        display = "、".join(names[:6])
        if len(names) > 6:
            display += "…"
        concept_rows += f"| {c_label} | {len(names)} | {display} |\n"

    # Build type summary
    type_parts = []
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        if t == "未知":
            continue
        type_parts.append(f"{t} ({c})")
    type_summary = "、".join(type_parts[:6])

    diff_parts = []
    for d, c in sorted(diff_counts.items(), key=lambda x: -x[1]):
        if d == "未知":
            continue
        diff_parts.append(f"{d} ({c})")
    diff_summary = "、".join(diff_parts[:4])

    now = now_iso()

    # ── 兴趣趋势: 近 7 天 ingested_at 的 domain 分布 ────────────
    recent_domain_counts: dict[str, int] = {}
    recent_total = 0
    try:
        conn = get_connection()
        recent_rows = conn.execute(
            "SELECT domain, COUNT(*) FROM knowledge_items "
            "WHERE datetime(ingested_at) > datetime('now', '-7 days') "
            "GROUP BY domain ORDER BY COUNT(*) DESC"
        ).fetchall()
        for r in recent_rows:
            d = r[0] if r[0] else "未知"
            c = r[1]
            recent_domain_counts[d] = c
            recent_total += c
    except sqlite3.Error as e:
        log.warning("recent domain distribution query failed: %s", e)

    trend_lines: list[str] = []
    if recent_total > 0:
        top_recent = sorted(recent_domain_counts.items(), key=lambda x: -x[1])[:3]
        for domain, count in top_recent:
            if domain == "未知":
                continue
            label = DOMAIN_LABELS.get(domain, domain)
            recent_share = count / recent_total
            overall_share = domain_counts.get(domain, 0) / total if total > 0 else 0
            if recent_share > overall_share * 1.2:
                trend = "上升"
            elif recent_share < overall_share * 0.8:
                trend = "下降"
            else:
                trend = "稳定"
            trend_lines.append(f"- {trend}: {label}（近 7 天 {count} 条）")
        if not trend_lines:
            trend_lines.append(f"- 近 7 天新增 {recent_total} 条，以未分类领域为主")
    else:
        trend_lines.append("- 近 7 天无新增条目")
    trend_text = "\n".join(trend_lines)

    # ── 内容创作风格: content_drafts platform 分布 ──────────────
    platform_parts: list[str] = []
    try:
        conn = get_connection()
        platform_rows = conn.execute(
            "SELECT platform, COUNT(*) FROM content_drafts GROUP BY platform"
        ).fetchall()
        for r in platform_rows:
            p = r[0] if r[0] else "未指定"
            c = r[1]
            platform_parts.append(f"{p} ({c})")
    except sqlite3.Error as e:
        log.warning("content_drafts platform query failed: %s", e)

    if platform_parts:
        platform_summary = "、".join(platform_parts)
    else:
        platform_summary = "暂无创作记录"
    style_description = "偏好深度分析型长文，注重数据支撑和逻辑推演"

    return f"""---
updated_at: "{now}"
---

# SOUL.md — 角色画像

> 此文件由系统自动生成，基于 knowledge/items/ 和 knowledge/concepts/ 的统计聚合。

## 身份
- 角色: 安全与 AI 交叉领域从业者 / 独立开发者
- 核心领域: 网络安全、人工智能、效率工具

## 知识深度

| 主题 | 掌握度 | 条目数 | 最近学习 |
|------|--------|--------|----------|
{domain_rows}
### 概念覆盖 ({len(concepts)} 个概念)

| 领域 | 概念数 | 代表概念 |
|------|--------|----------|
{concept_rows}
## 兴趣趋势
{trend_text}

## 学习偏好
- 偏好类型: {type_summary}
- 偏好难度: {diff_summary}
- 学习节奏: 以微信公众号、安全资讯为主

## 内容创作风格
- 主要平台: {platform_summary}
- 风格描述: {style_description}
"""


__all__ = ["get_soul", "create_soul_task"]