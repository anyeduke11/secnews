"""ai_hub — 知识写回唯一门面 (v0.5 §18.2 强约束 1)。

知识写入只有一条路: collector/agent/API 产出 → ai_hub → 写 ``.md`` 文件
→ watcher 同步 SQLite 索引。禁止绕过本模块直接拼 frontmatter 写 items/。

职责边界 (v0.5 M5 前的增量):
- 本模块当前只收敛 **items/*.md 的结构化写回** 与 concepts frontmatter
  回填两条路径, 并在 wiki_events 表留痕 (migration 065 承诺的写入方之一)。
- LLM 单出口 (合并 llm_service+ai_service) 属 M5 T19, 不在本模块范围。
- bookmark/cubox/history 三类导入器仍直写 md (历史遗留, 待后续版本迁移)。

事件语义:
- kind: ``agent_write`` (系统/agent 写回) | ``cli_agent_run`` (§19 外部 CLI)
- agent: 产生者标识, 如 ``api:patch_item`` / ``job:stub_backfill`` /
  ``kl:compiler`` / ``trigger:t4`` / ``mcp:wiki_write``
"""
from __future__ import annotations

import logging

log = logging.getLogger("hotspot.ai_hub")


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


__all__ = ["write_item", "update_frontmatter"]
