"""Migration from llm-wiki-2.0 filesystem to integrated wiki.

One-time import that scans the external llm-wiki-2.0 directory and
copies valid items into the integrated knowledge/ store.
"""
from __future__ import annotations

from pathlib import Path

from backend.logging_config import logger
from backend.wiki_fs.store import WikiFs
from backend.wiki_fs.contract import parse_frontmatter


def migrate_from_external(src_root: str, dest_fs: WikiFs) -> dict:
    """Migrate items from an external llm-wiki-2.0 directory.

    Args:
        src_root: Path to the source knowledge/ directory.
        dest_fs: Target WikiFs instance.

    Returns:
        {"migrated": int, "skipped": int, "errors": int}
    """
    src = Path(src_root)
    items_dir = src / "items"
    if not items_dir.exists():
        logger.warning(f"migrate: source items/ not found at {items_dir}")
        return {"migrated": 0, "skipped": 0, "errors": 0}

    migrated = 0
    skipped = 0
    errors = 0

    for f in sorted(items_dir.glob("*.md")):
        if f.stem.startswith("_"):
            skipped += 1
            continue
        try:
            text = f.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            item_id = fm.get("id", f.stem)

            # Skip if already exists in destination.
            existing = dest_fs.read_item(item_id)
            if existing is not None:
                skipped += 1
                continue

            # Ensure required fields.
            fm.setdefault("id", item_id)
            fm.setdefault("kl_stage", "kl:raw")
            dest_fs.write_item(item_id, {"fm": fm, "body": body})
            migrated += 1
        except Exception as exc:
            logger.warning(f"migrate: error on {f.name}: {exc}")
            errors += 1

    logger.info(f"migrate complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return {"migrated": migrated, "skipped": skipped, "errors": errors}
