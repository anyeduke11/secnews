"""WikiFs path constants — single source of truth for llm-wiki-2.0 layout.

v0.6.3 P3-4 收官 (用户裁决 2026-08-30):
  - llm-wiki-2.0/ = 知识存档唯一根 (single source of truth)
  - 旧 knowledge/ 根全栈下线 (写入方/读取方全量重指向到本模块导出常量)
  - 子树迁移方案:
      knowledge/items       → llm-wiki-2.0/items        (已存在, 4149 条对账 1:1)
      knowledge/concepts    → llm-wiki-2.0/concepts     (已存在, 96 条对账 1:1)
      knowledge/learning/*  → llm-wiki-2.0/learning/*   (新建 + 整体搬迁)
      knowledge/content/*   → llm-wiki-2.0/content/*    (新建 + 整体搬迁)
      knowledge/summaries/* → llm-wiki-2.0/summaries/*  (新建 + 整体搬迁)
      knowledge/_SCHEMA.md  → 弃用 (wiki_fs/contract.py 已自描述, 实际无引用)
      knowledge/_MAP.md     → 弃用 (map_updater.py 唯一调用方已迁出本根)
      knowledge/SOUL.md     → 弃用 (soul_service 标记 deprecated, 用 llm-wiki-2.0/soul.md 替代)
      knowledge/inbox/      → llm-wiki-2.0/inbox        (已存在)
      knowledge/quarantine/ → llm-wiki-2.0/quarantine   (已存在)

调用约定
----
所有写入/读取方 (knowledge_sync / content_service / compiler / learning_service /
history_import / bookmark_sync / concept_linker / summary_service / api/knowledge.py)
必须从此模块导入路径常量, 禁止再硬编码 ``Path(...) / "knowledge" / ...``。
测试可 monkeypatch 本模块的全局常量 (test_wiki_tools.py 已沿用此模式)。

测试环境覆盖
------------
HOTSPOT_WIKI_ROOT env 改变 wiki_root() 解析, 本模块的 *DIR 常量都基于 wiki_root()
动态推导, 因此测试用 tmp_path 设 env 后所有路径自动跟随。
"""
from __future__ import annotations

from pathlib import Path

from backend.wiki_fs.root import resolve_wiki_root


def wiki_root() -> Path:
    """Wiki 存档唯一根 (llm-wiki-2.0/, 或 env 覆盖路径)。"""
    return Path(resolve_wiki_root())


# Items
ITEMS_DIR: Path = wiki_root() / "items"

# Concepts
CONCEPTS_DIR: Path = wiki_root() / "concepts"

# Inbox / Quarantine (WikiFs 内置, 保留兼容别名)
INBOX_DIR: Path = wiki_root() / "inbox"
QUARANTINE_DIR: Path = wiki_root() / "quarantine"

# Learning (任务队列 + 学习状态) — 从旧 knowledge/learning 整体迁移
LEARNING_DIR: Path = wiki_root() / "learning"
LEARNING_TASKS_DIR: Path = LEARNING_DIR / "tasks"
LEARNING_PENDING_DIR: Path = LEARNING_TASKS_DIR / "pending"
LEARNING_DONE_DIR: Path = LEARNING_TASKS_DIR / "done"
LEARNING_FAILED_DIR: Path = LEARNING_TASKS_DIR / "failed"

# Content (草稿 + 日历 + 模板) — 从旧 knowledge/content 整体迁移
CONTENT_DIR: Path = wiki_root() / "content"
DRAFTS_DIR: Path = CONTENT_DIR / "drafts"
CALENDAR_PATH: Path = CONTENT_DIR / "calendar.json"

# Summaries (周报) — 从旧 knowledge/summaries 整体迁移
SUMMARIES_DIR: Path = wiki_root() / "summaries"

# Graph (概念关系图谱) — concept_linker 写这里
GRAPH_PATH: Path = wiki_root() / "graph.json"

# SOUL.md — 角色画像, 从旧 knowledge/SOUL.md 迁出 (v0.6.3 P3-4)
SOUL_PATH: Path = wiki_root() / "soul.md"

# Deprecated single-file artefacts (旧 knowledge/_MAP.md / _SCHEMA.md)
# 保留符号便于 grep 残留引用, 实际写入方在迁出本模块后不再有生产者。
DEPRECATED_LEGACY_FILES = {
    "knowledge/SOUL.md": "soul_service 已迁至 llm-wiki-2.0/soul.md",
    "knowledge/_MAP.md": "map_updater 是唯一调用方, 已迁出, 不再生成",
    "knowledge/_SCHEMA.md": "无引用方, wiki_fs/contract.py 自描述",
}


__all__ = [
    "CALENDAR_PATH", "CONCEPTS_DIR", "CONTENT_DIR", "DEPRECATED_LEGACY_FILES",
    "DRAFTS_DIR", "GRAPH_PATH", "INBOX_DIR",
    "ITEMS_DIR", "LEARNING_DIR", "LEARNING_DONE_DIR", "LEARNING_FAILED_DIR",
    "LEARNING_PENDING_DIR", "LEARNING_TASKS_DIR", "QUARANTINE_DIR",
    "SOUL_PATH", "SUMMARIES_DIR", "wiki_root",
]