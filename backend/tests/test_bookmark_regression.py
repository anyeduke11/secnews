"""Regression test for bookmark import with non-ASCII (Chinese) tags.

Bug: _update_bookmark_md_frontmatter used json.dumps(tags) (default
ensure_ascii=True) inside a re.sub() replacement, which raised
`re.PatternError: bad escape \\u` when tags contained non-ASCII characters.
The bug only triggered on the 2nd import (dedupe path) since the 1st
import calls _write_bookmark_md which is a plain write — no regex.

This test exercises the full HTML import flow twice and asserts:
1. Both calls return 200 / no exception.
2. The .md file written contains readable UTF-8 tags, not `\\uXXXX` escapes.
3. The dedupe path correctly merges tags.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest


def test_reimport_with_chinese_tags_does_not_crash(tmp_path, monkeypatch):
    """Reproduces the 500 → 200 regression: re-importing a bookmark with
    Chinese folder names must not crash the regex-based frontmatter updater."""
    from backend.repository import knowledge_repo
    from backend.services import bookmark_sync

    # Redirect ITEMS_DIR to a temp path so we don't pollute knowledge/items/
    monkeypatch.setattr(bookmark_sync, "ITEMS_DIR", tmp_path)

    # Use a unique URL per test run so the knowledge_repo doesn't already
    # have it from a previous test or integration run (we share the same DB).
    import uuid
    test_url = f"https://example.com/page-{uuid.uuid4().hex[:8]}"

    html = f"""<!DOCTYPE NETSCAPE-Bookmark-file-1>
<TITLE>Bookmarks</TITLE>
<DL><p>
    <DT><H3>工作</H3>
    <DL><p>
        <DT><A HREF="{test_url}">GitHub</A>
    </DL><p>
</DL><p>
"""

    # 1st import: writes new .md via _write_bookmark_md (no regex, no crash)
    r1 = bookmark_sync.import_bookmarks(
        bookmark_sync.parse_chrome_html(html)
    )
    assert r1["imported"] == 1, f"expected 1 imported, got {r1}"
    assert r1["skipped_duplicates"] == 0

    # 2nd import: hits _update_bookmark_md_frontmatter (regex replacement)
    # BEFORE FIX: raises re.PatternError: bad escape \\u -> 500
    # AFTER FIX: succeeds and merges tags
    r2 = bookmark_sync.import_bookmarks(
        bookmark_sync.parse_chrome_html(html)
    )
    assert r2["imported"] == 0, f"expected 0 imported (deduped), got {r2}"
    assert r2["skipped_duplicates"] == 1

    # Verify the .md file contains readable UTF-8, not \\u escapes
    from backend.services.data_cleaning import item_id_from_url
    item_id = item_id_from_url(test_url)
    md_path = tmp_path / f"{item_id}.md"
    assert md_path.exists(), f"expected {md_path} to exist"
    text = md_path.read_text(encoding="utf-8")
    assert "工作" in text, f"expected Chinese tag '工作' in {text!r}"
    # ensure no \\uXXXX escapes left
    assert "\\u" not in text, f"unexpected \\u escape in {text!r}"


def test_json_dumps_replacement_is_ascii_safe():
    """Direct unit test: ensure json.dumps(ensure_ascii=False) does not
    introduce regex escape sequences into a re.sub replacement string."""
    import re

    tags = ["工作", "学习"]
    replacement = f"tags: {json.dumps(tags, ensure_ascii=False)}"
    # The default json.dumps(tags) would produce: tags: ["\u5de5\u4f5c", "\u5b66\u4f7f"]
    # which would crash re.sub. With ensure_ascii=False it should be safe.
    assert "工作" in replacement
    text = "tags: []\n"
    out = re.sub(r"^tags:.*$", replacement, text, flags=re.MULTILINE)
    assert out == "tags: [\"工作\", \"学习\"]\n"
