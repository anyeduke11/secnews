"""Wiki filesystem — Python port of the LLM-Wiki fsstore.

Provides read/write operations for the knowledge/ directory structure
with YAML frontmatter contracts and FTS5 integration.
"""
from backend.wiki_fs.store import WikiFs

__all__ = ["WikiFs"]
