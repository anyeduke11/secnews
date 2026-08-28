"""ai_hub/write_back.py — 知识写回唯一门面 (v0.5 §18.2 强约束 1)。

本模块封装 SPEC §18.2 强约束 1 的两个写路径:

- ``write_score`` — ``ai_scores`` 表唯一 INSERT 入口
- ``write_item`` / ``update_frontmatter`` — 知识 md 写回 + wiki_events 留痕

与 ``tasks.py`` (AIService 评价链路) 分离: 本模块只负责"写", 评价是 tasks。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.repository.db import get_connection
from backend.services.ai_hub.tasks import DEFAULT_SCORE

log = logging.getLogger("hotspot.ai_hub")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════
# ai_scores 写路径唯一入口 (SPEC §1 Task19)
# ═══════════════════════════════════════════════════════════════
def write_score(
    hotspot_id: str,
    score: float,
    *,
    reason: str = "ai_hub",
    scorer: str | None = None,
) -> int | None:
    """写入 ``ai_scores`` 表 — 生产代码唯一 INSERT 入口。

    SPEC §1 Task19: ``ai_scores`` 写路径仅本函数命中; mcp_agent_tools 的
    ``score_item`` 与 T1 的 LLM 评分审计都必须经此调用。

    Args:
        hotspot_id: 关联 hotspot / knowledge item id
        score: 0-10 评分
        reason: 评分理由/来源 (如 llm_service / agent:claude-desktop)
        scorer: 评分者标识 (MCP agent 工具用), 默认 None

    Returns:
        lastrowid; 失败返回 None (评分是审计增强, 静默降级不阻塞业务)。
    """
    try:
        cur = get_connection().execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scorer, scored_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (hotspot_id, float(score), reason, scorer, _now_iso()),
        )
        return cur.lastrowid
    except Exception as e:
        log.warning(f"write_score failed for {hotspot_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 知识写回唯一门面 (v0.5 §18.2 强约束 1)
# ═══════════════════════════════════════════════════════════════
def write_item(
    item: dict,
    content: str | None = None,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> None:
    """写回 ``knowledge/items/{id}.md`` 并在 wiki_events 留痕。

    md 写失败向上抛错 (真相源必须成功); 遥测失败静默降级 (不阻塞写路径)。

    Args:
        item: knowledge_items dict (须含 id)
        content: Markdown 正文 (None=保留文件已有正文, ''=清空)
        kind: wiki_events 事件类型, 默认 agent_write
        agent: 产生者标识, 如 api:patch_item / mcp:wiki_write
    """
    from backend.services import knowledge_sync

    knowledge_sync.write_item_to_md(item, content=content)
    item_id = str(item.get("id", ""))
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind=kind,
            wiki_path=f"items/{item_id}.md",
            db_table="knowledge_items",
            db_row_id=item_id,
            agent=agent,
        )
    except Exception as e:
        log.debug(f"wiki_events log skipped for items/{item_id}.md: {e}")


def update_frontmatter(
    rel_path: str,
    key: str,
    value: str,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> bool:
    """就地更新 md frontmatter 单字段并留痕。

    Args:
        rel_path: 相对 knowledge/ 的路径, 如 ``concepts/zero-trust.md``
        key/value: 要写入的 frontmatter 字段
        kind/agent: wiki_events 事件类型与产生者

    Returns True on success (同 knowledge_sync.update_md_frontmatter_field)。
    """
    from backend.services.knowledge_sync import KNOWLEDGE_DIR, update_md_frontmatter_field

    ok = update_md_frontmatter_field(KNOWLEDGE_DIR / rel_path, key, value)
    if ok:
        try:
            from backend.repository.wiki_event_repo import wiki_event_repo

            wiki_event_repo.log(kind=kind, wiki_path=rel_path, agent=agent)
        except Exception as e:
            log.debug(f"wiki_events log skipped for {rel_path}: {e}")
    return ok


__all__ = ["write_score", "write_item", "update_frontmatter"]
