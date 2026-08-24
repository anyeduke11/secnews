"""WikiFs — wiki filesystem store for knowledge/ directory.

Handles items/, concepts/, inbox/, quarantine/ directories with
YAML frontmatter contracts and atomic file operations.
"""
from __future__ import annotations

import hashlib
import html.parser
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.logging_config import logger
from backend.wiki_fs.contract import parse_frontmatter, serialize_frontmatter


class WikiFs:
    """Filesystem-backed wiki store rooted at ``knowledge/``."""

    def __init__(self, root: str) -> None:
        self.root = root
        self._items_dir = Path(root) / "items"
        self._concepts_dir = Path(root) / "concepts"
        self._inbox_dir = Path(root) / "inbox"
        self._quarantine_dir = Path(root) / "quarantine"

    def _ensure_dirs(self) -> None:
        for d in (self._items_dir, self._concepts_dir, self._inbox_dir, self._quarantine_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def list_ids(self) -> list[str]:
        """List all item IDs (without .md extension)."""
        if not self._items_dir.exists():
            return []
        return sorted(
            f.stem for f in self._items_dir.glob("*.md") if f.stem != "_MAP"
        )

    def read_item(self, item_id: str) -> dict | None:
        """Return {"fm": dict, "body": str} or None if not found."""
        path = self._items_dir / f"{item_id}.md"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            return {"fm": fm, "body": body}
        except Exception as exc:
            logger.warning(f"read_item failed: {item_id}: {exc}")
            return None

    def write_item(self, item_id: str, doc: dict) -> None:
        """Atomic write (.tmp → rename) with stable frontmatter ordering."""
        self._ensure_dirs()
        path = self._items_dir / f"{item_id}.md"
        fm = doc.get("fm", {})
        body = doc.get("body", "")

        fm_str = serialize_frontmatter(fm)
        content = f"{fm_str}\n\n{body}\n" if body else f"{fm_str}\n"

        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(path)

    def ingest_url(self, url: str, title: str, text: str) -> dict:
        """Import a URL as a new item. Returns {"id": str, "title": str}."""
        item_id = _slug_from_url(url)
        now = datetime.now(timezone.utc).isoformat()
        fm = {
            "id": item_id,
            "title": title,
            "url": url,
            "source": "url-import",
            "lifecycle": "kl:raw",
            "ingested_at": now,
            "tags": [],
        }
        self.write_item(item_id, {"fm": fm, "body": text})
        logger.info(f"ingest_url: {item_id} <- {url}")
        return {"id": item_id, "title": title}

    def import_bookmarks(self, html_content: str) -> dict:
        """Parse Netscape bookmark HTML and import each link. Returns {added, dup}."""
        self._ensure_dirs()
        parser = _BookmarkParser()
        parser.feed(html_content)
        added = 0
        dup = 0
        for bm in parser.bookmarks:
            url = bm.get("href", "")
            title = bm.get("title", url)
            if not url:
                continue
            item_id = _slug_from_url(url)
            if (self._items_dir / f"{item_id}.md").exists():
                dup += 1
                continue
            now = datetime.now(timezone.utc).isoformat()
            fm = {
                "id": item_id,
                "title": title,
                "url": url,
                "source": "bookmark-import",
                "lifecycle": "kl:raw",
                "ingested_at": now,
                "tags": bm.get("tags", []),
            }
            self.write_item(item_id, {"fm": fm, "body": ""})
            added += 1
        return {"added": added, "dup": dup}

    def scan_inbox(self) -> dict:
        """Scan inbox/ — move valid items to items/, bad ones to quarantine/."""
        self._ensure_dirs()
        moved = 0
        quarantined = 0
        for f in self._inbox_dir.glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(text)
                if not fm.get("title") and not body.strip():
                    # Empty file → quarantine.
                    dest = self._quarantine_dir / f.name
                    f.rename(dest)
                    quarantined += 1
                else:
                    item_id = fm.get("id", f.stem)
                    fm.setdefault("id", item_id)
                    fm.setdefault("lifecycle", "kl:raw")
                    self.write_item(item_id, {"fm": fm, "body": body})
                    f.unlink()
                    moved += 1
            except Exception as exc:
                logger.warning(f"scan_inbox: {f.name} error: {exc}")
                dest = self._quarantine_dir / f.name
                f.rename(dest)
                quarantined += 1
        return {"moved": moved, "quarantined": quarantined}

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------
    def list_concepts(self) -> list[dict]:
        """List all concept cards."""
        if not self._concepts_dir.exists():
            return []
        results = []
        for f in sorted(self._concepts_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(text)
                fm["_body"] = body
                results.append(fm)
            except Exception:
                pass
        return results

    def create_concept(self, concept_id: str, name: str, tags: list[str]) -> None:
        """Create a concept card."""
        self._ensure_dirs()
        fm = {"id": concept_id, "name": name, "tags": tags}
        path = self._concepts_dir / f"{concept_id}.md"
        content = f"{serialize_frontmatter(fm)}\n"
        path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Search / Related
    # ------------------------------------------------------------------
    def find_related(self, item_id: str, top_k: int = 10) -> list[dict]:
        """FTS co-occurrence query — returns [{id, weight}]."""
        doc = self.read_item(item_id)
        if doc is None:
            return []
        tags = doc["fm"].get("tags", [])
        title = doc["fm"].get("title", "")
        query_terms = list(tags[:5])
        if title:
            query_terms.append(title)
        if not query_terms:
            return []

        # Simple keyword-based matching against all items.
        scores: dict[str, float] = {}
        for other_id in self.list_ids():
            if other_id == item_id:
                continue
            other = self.read_item(other_id)
            if other is None:
                continue
            other_tags = set(t.lower() for t in other["fm"].get("tags", []))
            other_title = other["fm"].get("title", "").lower()
            weight = 0.0
            for term in query_terms:
                term_lower = term.lower()
                if term_lower in other_tags:
                    weight += 1.0
                if term_lower in other_title:
                    weight += 0.5
            if weight > 0:
                scores[other_id] = weight

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"id": k, "weight": v} for k, v in ranked[:top_k]]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _slug_from_url(url: str) -> str:
    """Generate a stable item ID from a URL."""
    clean = re.sub(r'https?://', '', url).strip('/')
    clean = re.sub(r'[^a-zA-Z0-9]+', '-', clean)[:80].strip('-')
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{clean}-{h}" if clean else f"item-{h}"


class _BookmarkParser(html.parser.HTMLParser):
    """Parse Netscape bookmark HTML to extract links."""

    def __init__(self) -> None:
        super().__init__()
        self.bookmarks: list[dict] = []
        self._current: dict | None = None
        self._in_a = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() == "a":
            self._in_a = True
            self._current = {}
            for k, v in attrs:
                if k.lower() == "href":
                    self._current["href"] = v
                elif k.lower() == "tags":
                    self._current["tags"] = [t.strip() for t in v.split(",")]

    def handle_data(self, data: str) -> None:
        if self._in_a and self._current is not None:
            self._current["title"] = data.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_a:
            self._in_a = False
            if self._current and self._current.get("href"):
                self.bookmarks.append(self._current)
            self._current = None
