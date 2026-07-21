#!/usr/bin/env python3
"""Phase 5B: Tokenize hardcoded colors in frontend components.

Mapping strategy:
- Semantic colors → CSS variables
- Light tints (rgba with low alpha) → color-mix() with var()
- Light text on bright bg (#fff, #0a0a0f, etc.) → keep as constants
"""
import re
from pathlib import Path

ROOT = Path("/Users/duke/Documents/hotspot/frontend/src/components")

# Hardcoded color → CSS variable mapping
# Note: tokens must be added to index.css first; we're using --color-success/warning/error/info
# which already exist (Phase 1A)
HEX_TO_VAR = {
    # Saturated semantic colors
    "#e85d5d": "var(--color-error)",      # was security red, semantic = error
    "#00c96a": "var(--color-success)",    # was general green, semantic = success
    "#00bcd4": "var(--color-info)",       # was AI cyan, semantic = info
    "#f0c929": "var(--color-warning)",    # was finance yellow, semantic = warning
    "#888899": "var(--text-muted)",       # was muted gray
    "#8888a0": "var(--text-secondary)",   # dark theme text-secondary value
    "#5cb85c": "var(--color-success)",    # success
    "#f0ad4e": "var(--color-warning)",    # warning
    "#5bc0de": "var(--color-info)",       # info
    "#3b82f6": "var(--color-info)",       # blue (info-like)
    "#8b5cf6": "var(--color-startup)",    # purple
    "#9575cd": "var(--color-startup)",    # purple
    "#5c9fe0": "var(--color-info)",       # blue
    "#7c6aff": "var(--color-startup)",    # purple
    "#e8891a": "var(--color-bid)",        # bid orange
    "#22c55e": "var(--color-success)",    # already a token
    "#eab308": "var(--color-warning)",    # already a token
    "#ef4444": "var(--color-error)",      # already a token
    "#ff6b9d": "var(--color-error)",      # pink → error (closest semantic)
    # Tints with alpha (#RRGGBBAA)
    "#e85d5d22": "color-mix(in srgb, var(--color-error) 13%, transparent)",
    "#e85d5d14": "color-mix(in srgb, var(--color-error) 8%, transparent)",
    "#00c96a14": "color-mix(in srgb, var(--color-success) 8%, transparent)",
    "#00c96a20": "color-mix(in srgb, var(--color-success) 13%, transparent)",
    "#3b82f614": "color-mix(in srgb, var(--color-info) 8%, transparent)",
    "#3b82f620": "color-mix(in srgb, var(--color-info) 13%, transparent)",
}

# rgba → color-mix
RGBA_TO_MIX = [
    # (rgb, alpha) → color-mix expression
    ((232, 93, 93), "var(--color-error)"),
    ((0, 201, 106), "var(--color-success)"),
    ((0, 188, 212), "var(--color-info)"),
    ((240, 201, 41), "var(--color-warning)"),
    ((92, 184, 92), "var(--color-success)"),
    ((136, 136, 153), "var(--text-muted)"),
    ((6, 182, 212), "var(--color-info)"),
]

def transform_text(content: str) -> str:
    """Apply all color token mappings to a string."""
    out = content

    # 1. Replace exact hex codes (longest first to handle #aabbccdd before #aabbcc)
    sorted_hex = sorted(HEX_TO_VAR.keys(), key=len, reverse=True)
    for hex_code in sorted_hex:
        replacement = HEX_TO_VAR[hex_code]
        # Case-insensitive match
        pattern = re.compile(re.escape(hex_code), re.IGNORECASE)
        out = pattern.sub(replacement, out)

    # 2. Replace rgba() with color-mix()
    for (rgb, var_name) in RGBA_TO_MIX:
        r, g, b = rgb
        # Match rgba(r, g, b, ALPHA) with various whitespace
        pattern = re.compile(
            rf"rgba\(\s*{r}\s*,\s*{g}\s*,\s*{b}\s*,\s*([0-9.]+)\s*\)"
        )
        def make_repl(var_name):
            def repl(m):
                alpha = float(m.group(1))
                # Convert 0.12 → 12, 0.15 → 15, etc.
                pct = round(alpha * 100)
                return f"color-mix(in srgb, {var_name} {pct}%, transparent)"
            return repl
        out = pattern.sub(make_repl(var_name), out)

    return out

def main():
    files = list(ROOT.rglob("*.tsx")) + list(ROOT.rglob("*.ts"))
    files = [f for f in files if ".test." not in f.name]

    changed = []
    for f in files:
        original = f.read_text(encoding="utf-8")
        updated = transform_text(original)
        if updated != original:
            f.write_text(updated, encoding="utf-8")
            changed.append(str(f.relative_to(ROOT.parent.parent.parent)))

    print(f"Updated {len(changed)} files:")
    for path in sorted(changed):
        print(f"  {path}")

if __name__ == "__main__":
    main()
