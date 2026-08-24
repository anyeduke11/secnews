"""Frontmatter contract — stable-order YAML serialization.

Defines the canonical key ordering and type constraints for wiki item
frontmatter to ensure deterministic serialization and diff-friendly storage.
"""
from __future__ import annotations

# Canonical key order for frontmatter output.
# Keys not in this list are appended alphabetically at the end.
_FM_KEY_ORDER = [
    "id",
    "title",
    "url",
    "source",
    "category",
    "tags",
    "summary",
    "severity",
    "kl_stage",
    "ingested_at",
    "published_at",
    "review_at",
    "related",
    "concept_links",
    "source_items",
]


def serialize_frontmatter(fm: dict) -> str:
    """Serialize a frontmatter dict to YAML with stable key ordering.

    - Keys in _FM_KEY_ORDER come first, in order.
    - Remaining keys are sorted alphabetically.
    - Lists use block-sequence format (- item).
    - Strings with special chars are quoted.
    """
    lines: list[str] = ["---"]
    ordered_keys = [k for k in _FM_KEY_ORDER if k in fm]
    extra_keys = sorted(k for k in fm if k not in ordered_keys)

    for key in ordered_keys + extra_keys:
        value = fm[key]
        lines.append(_format_kv(key, value))

    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter + body from a markdown string.

    Returns (fm_dict, body_str). If no frontmatter found, returns ({}, text).
    """
    text = text.strip()
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---.
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text

    fm_text = text[3:end].strip()
    body = text[end + 4:].strip()

    fm = _parse_simple_yaml(fm_text)
    return fm, body


def _format_kv(key: str, value: object) -> str:
    """Format a single key-value pair for frontmatter."""
    if isinstance(value, list):
        if not value:
            return f"{key}: []"
        items = "\n".join(f"  - {_quote(v)}" for v in value)
        return f"{key}:\n{items}"
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    if value is None:
        return f"{key}: null"
    if isinstance(value, (int, float)):
        return f"{key}: {value}"
    return f"{key}: {_quote(str(value))}"


def _quote(s: str) -> str:
    """Quote a string value if it contains special characters."""
    if not s:
        return '""'
    needs_quote = any(c in s for c in ":{}[]&*?|>!%@`,#'\"")
    if needs_quote:
        return f'"{s}"'
    return s


def _parse_simple_yaml(text: str) -> dict:
    """Minimal YAML parser for our frontmatter subset.

    Handles: key: value, key: [list], key:\\n  - item patterns.
    Does NOT handle nested objects, anchors, or multi-line strings.
    """
    result: dict = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.startswith("#"):
            i += 1
            continue

        if ":" not in line:
            i += 1
            continue

        colon_idx = line.index(":")
        key = line[:colon_idx].strip()
        val_str = line[colon_idx + 1:].strip()

        if val_str == "" or val_str == "":
            # Check for block sequence on next lines.
            items: list = []
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("- "):
                items.append(_unquote(lines[j].strip()[2:].strip()))
                j += 1
            if items:
                result[key] = items
                i = j
                continue
            result[key] = ""
        elif val_str == "[]":
            result[key] = []
        elif val_str.startswith("[") and val_str.endswith("]"):
            # Inline list.
            inner = val_str[1:-1]
            result[key] = [_unquote(v.strip()) for v in inner.split(",") if v.strip()]
        elif val_str == "null":
            result[key] = None
        elif val_str == "true":
            result[key] = True
        elif val_str == "false":
            result[key] = False
        else:
            # Try numeric.
            try:
                result[key] = int(val_str)
            except ValueError:
                try:
                    result[key] = float(val_str)
                except ValueError:
                    result[key] = _unquote(val_str)
        i += 1

    return result


def _unquote(s: str) -> str:
    """Remove surrounding quotes from a string value."""
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s
