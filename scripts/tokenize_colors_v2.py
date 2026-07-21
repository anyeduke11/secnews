#!/usr/bin/env python3
"""Phase 5B (round 2): Tokenize remaining hardcoded colors and rgba values."""
import re
from pathlib import Path

ROOT = Path("/Users/duke/Documents/hotspot/frontend/src/components")

# Additional hex mappings
HEX_TO_VAR = {
    "#06b6d4": "var(--color-info)",       # cyan (alt)
    "#10b981": "var(--color-success)",     # emerald
    "#888": "var(--text-muted)",          # 3-digit muted
    "#fff": "var(--text-on-color)",       # white text on saturated bg
    "#000": "var(--text-on-light)",       # black text on light bg
    "#0a0a0f": "var(--text-on-light)",    # dark text on light bg
    "#0a0d12": "var(--text-on-light)",    # dark text on light bg
    "#0a1f15": "var(--text-on-light)",    # dark text on green bg
    "#1a1d24": "var(--text-on-light)",    # dark text on yellow bg
    "#1a1a2e": "var(--text-primary)",     # dark theme text-primary (but used in JS as constant)
}

# rgba → either var(--bg-overlay) or color-mix
def rgba_replace(content):
    # Modal backdrops: rgba(0, 0, 0, 0.4-0.5)
    content = re.sub(
        r"rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\.[45]\s*\)",
        "var(--bg-overlay)",
        content
    )
    # KnowledgeSearchBar source tints
    content = re.sub(
        r"rgba\(\s*149\s*,\s*117\s*,\s*205\s*,\s*0\.\d+\s*\)",
        "color-mix(in srgb, var(--color-startup) 15%, transparent)",
        content
    )
    content = re.sub(
        r"rgba\(\s*92\s*,\s*159\s*,\s*224\s*,\s*0\.\d+\s*\)",
        "color-mix(in srgb, var(--color-info) 15%, transparent)",
        content
    )
    # SyncHistory pink tints
    content = re.sub(
        r"rgba\(\s*255\s*,\s*107\s*,\s*157\s*,\s*0\.2\s*\)",
        "color-mix(in srgb, var(--color-error) 20%, transparent)",
        content
    )
    content = re.sub(
        r"rgba\(\s*255\s*,\s*107\s*,\s*157\s*,\s*0\.3\s*\)",
        "color-mix(in srgb, var(--color-error) 30%, transparent)",
        content
    )
    return content

def transform_text(content: str) -> str:
    out = content
    for hex_code, replacement in HEX_TO_VAR.items():
        pattern = re.compile(re.escape(hex_code), re.IGNORECASE)
        out = pattern.sub(replacement, out)
    out = rgba_replace(out)
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
