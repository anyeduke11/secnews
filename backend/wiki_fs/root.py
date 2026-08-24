"""Wiki root resolution — llm-wiki-2.0 为知识唯一存档根。

2026-08-24 裁决 (用户):
  - llm-wiki-2.0/ = 知识关键存档 (single source of truth), 全栈读写只指向它
  - SQLite        = 运营层 + 事件管理 (wiki_events 表为两世界唯一桥梁)
旧 knowledge/ 根不再被 pipeline / dashboard 写入或读取。
"""
from __future__ import annotations

import os


def resolve_wiki_root() -> str:
    """返回 wiki 存档根目录 (绝对路径)。

    优先级: HOTSPOT_WIKI_ROOT env 覆盖 > <repo>/llm-wiki-2.0
    (env 主要供测试与多环境部署使用)
    """
    env_root = os.environ.get("HOTSPOT_WIKI_ROOT")
    if env_root:
        return os.path.abspath(env_root)
    from backend.config import config
    base = os.path.dirname(os.path.abspath(config.db_path))
    return os.path.normpath(os.path.join(base, "..", "llm-wiki-2.0"))
