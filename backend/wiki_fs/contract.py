"""Frontmatter contract — stable-order YAML serialization.

Defines the canonical key ordering and type constraints for wiki item
frontmatter to ensure deterministic serialization and diff-friendly storage.
"""
from __future__ import annotations

import json
import re
import string

# json.dumps 默认 ensure_ascii=True 的历史产物: 中文被写成字面 \uXXXX 存进 md。
# 只认 "\u + 恰好 4 位十六进制", 因此 C:\users 这类真实反斜杠不会被误伤。
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")

_DQ_ESCAPES = {
    '"': '"', "\\": "\\", "/": "/",
    "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
}
_HEX = set(string.hexdigits)


def _decode_escapes(s: str) -> str:
    """把字面 \\uXXXX 序列还原成真实字符 (幂等: 真中文无反斜杠, 再跑不变)。"""
    if "\\" not in s:
        return s
    return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), s)


def _unescape_dq(body: str) -> str:
    """单遍解码双引号 YAML 标量内的转义 (\\\" \\\\ \\uXXXX)。

    必须单遍: 先替 \\\\ 再替 \\uXXXX 会把 `\\\\u0041` 错解成 `\\u0041`→'A'。
    """
    if "\\" not in body:
        return body
    out: list[str] = []
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "u" and i + 6 <= n and all(c in _HEX for c in body[i + 2:i + 6]):
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
            continue
        if nxt in _DQ_ESCAPES:
            out.append(_DQ_ESCAPES[nxt])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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
    "lifecycle",
    "kl_stage",
    "ingested_at",
    "published_at",
    "review_at",
    "related",
    "concept_links",
    "source_items",
]

# 生命周期阶段 (与 kl_pipeline.queue.STAGES 一致)。
LIFECYCLE_STAGES = ("kl:raw", "kl:refine", "kl:link", "kl:structure", "kl:publish")


def get_lifecycle(fm: dict) -> str:
    """读取条目生命周期阶段 (SCHEMA.md 契约字段为 ``lifecycle``)。

    缺失时默认 kl:raw; 兼容读取 Phase 0 开发期误写的 ``kl_stage``。
    """
    return fm.get("lifecycle") or fm.get("kl_stage") or "kl:raw"


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
    if isinstance(value, dict):
        # 本契约的标量解析器不支持嵌套映射; 落成合法转义的 JSON 字符串,
        # 比落到 str(dict) 的 Python repr (单引号 + 非法 YAML) 更安全。
        return f"{key}: {_quote(json.dumps(value, ensure_ascii=False))}"
    return f"{key}: {_quote(str(value))}"


def _quote(s: str) -> str:
    """Quote a string value if it contains special characters.

    双引号内必须转义 `\\` 与 `"` — 缺了它, 含 JSON 的值会写出非法 YAML
    (历史损坏: `retention: "{"initial": 1.0}"`)。
    """
    if not s:
        return '""'
    needs_quote = any(c in s for c in ":{}[]&*?|>!%@`,#'\"\\") or s != s.strip()
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
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
    """Remove surrounding quotes from a string value and decode its escapes."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return _unescape_dq(s[1:-1])
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return _decode_escapes(s)
