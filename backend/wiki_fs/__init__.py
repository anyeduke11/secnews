"""Wiki filesystem — Python port of the LLM-Wiki fsstore.

Provides read/write operations for the knowledge/ directory structure
with YAML frontmatter contracts and FTS5 integration.
"""
from backend.wiki_fs.root import resolve_wiki_root
from backend.wiki_fs.store import WikiFs

__all__ = ["WikiFs", "resolve_wiki_root"]
