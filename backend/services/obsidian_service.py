"""Obsidian integration service.

- :func:`open_vault` returns an ``obsidian://open`` URL for the knowledge dir.
- :func:`get_conflicts` lists conflict snapshots written by the watchdog to
  ``knowledge/.conflicts/``.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from backend.services.knowledge_sync import KNOWLEDGE_DIR
from backend.services.knowledge_watcher import CONFLICTS_DIR

log = logging.getLogger("hotspot.obsidian_service")


def open_vault() -> dict:
    """Return an obsidian://open URL + filesystem path for the knowledge vault."""
    vault_path = str(KNOWLEDGE_DIR)
    encoded = quote(vault_path, safe="")
    return {
        "url": f"obsidian://open?path={encoded}",
        "path": vault_path,
    }


def get_conflicts() -> list[dict]:
    """List .md conflict snapshots in ``knowledge/.conflicts/``.

    Returns an empty list when the directory does not exist yet (no conflicts
    have ever been recorded).
    """
    if not CONFLICTS_DIR.exists():
        return []
    conflicts: list[dict] = []
    for f in sorted(CONFLICTS_DIR.glob("*.md")):
        stat = f.stat()
        conflicts.append(
            {
                "filename": f.name,
                "path": str(f),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return conflicts
