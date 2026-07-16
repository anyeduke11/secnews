"""Phase 1j Group X — 快速修复脚本.

Task 10.1: 7 条 domain=null 自动分类（LLM 判断写入）
Task 10.2: ingested_at 时区格式统一为 UTC Z
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ITEMS_DIR = PROJECT_ROOT / "knowledge" / "items"

# ── Task 10.1: 7 条 domain=null 分类 ────────────────────────────
# 基于 LLM 阅读标题+正文后的分类判断
CLASSIFICATIONS = {
    "898dd96c073c": {
        "domain": "finance",
        "topic": "private-equity",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["私募", "自购", "投资", "金融机构"],
    },
    "4201940cd083": {
        "domain": "security",
        "topic": "vulnerability-database",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["漏洞库", "CNVD", "信息安全", "参考资料"],
    },
    "4f3c7d046339": {
        "domain": "dev",
        "topic": "cs-curriculum",
        "type": "reference",
        "difficulty": "beginner",
        "tags": ["计算机科学", "开源课程", "GitHub", "学习资源"],
    },
    "c7500134ab49": {
        "domain": "general",
        "topic": "personal-website",
        "type": "opinion",
        "difficulty": "beginner",
        "tags": ["个人站点", "学习笔记", "随笔"],
    },
    "8c40203b708e": {
        "domain": "ai",
        "topic": "llm-cost",
        "type": "analysis",
        "difficulty": "intermediate",
        "tags": ["大模型", "Token成本", "银行AI", "成本控制"],
    },
    "1341281528e2": {
        "domain": "security",
        "topic": "national-security",
        "type": "news",
        "difficulty": "beginner",
        "tags": ["国家安全", "基础设施", "政策", "中央财经委"],
    },
    "0684a8ff48da": {
        "domain": "ai",
        "topic": "prompt-engineering",
        "type": "tutorial",
        "difficulty": "intermediate",
        "tags": ["Loop Engineering", "Prompt", "AI交互", "教程"],
    },
}


def update_frontmatter_field(frontmatter: str, key: str, value: str) -> str:
    """Update or insert a key in YAML frontmatter block."""
    pattern = rf"^({key}:).*$"
    replacement = f"{key}: {value}"
    if re.search(pattern, frontmatter, re.MULTILINE):
        return re.sub(pattern, replacement, frontmatter, flags=re.MULTILINE)
    return frontmatter.rstrip() + f"\n{key}: {value}\n"


def task_10_1_classify_null_domain() -> int:
    """Update 7 items with domain=null."""
    print("=== Task 10.1: 7 条 domain=null 自动分类 ===")
    count = 0
    for item_id, data in CLASSIFICATIONS.items():
        path = ITEMS_DIR / f"{item_id}.md"
        if not path.exists():
            print(f"  WARN: {item_id}.md not found")
            continue

        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        frontmatter = parts[1]
        body = parts[2]

        frontmatter = update_frontmatter_field(frontmatter, "domain", data["domain"])
        frontmatter = update_frontmatter_field(frontmatter, "topic", data["topic"])
        frontmatter = update_frontmatter_field(frontmatter, "type", data["type"])
        frontmatter = update_frontmatter_field(frontmatter, "difficulty", data["difficulty"])
        frontmatter = update_frontmatter_field(
            frontmatter, "tags", json.dumps(data["tags"], ensure_ascii=False)
        )

        path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")
        print(f"  ✓ {item_id}: domain={data['domain']} topic={data['topic']}")
        count += 1

    print(f"  Total: {count} items classified")
    return count


# ── Task 10.2: ingested_at 时区统一 ────────────────────────────

def _normalize_ingested_at(value: str) -> str:
    """Convert +0800/+00:00 format to UTC Z suffix.

    Examples:
      "2026-07-13T18:56:08.381+0800" → "2026-07-13T10:56:08Z"
      "2026-07-16T11:30:18.164778+00:00" → "2026-07-16T11:30:18Z"
      "2026-07-14T10:00:00Z" → unchanged
    """
    value = value.strip().strip('"').strip("'")
    if value.endswith("Z"):
        return value

    # Try parsing with various timezone formats
    # Handle +0800 (no colon) and +08:00 (with colon)
    try:
        # Python 3.7+ fromisoformat handles +00:00 but not +0800
        # First try replacing +0800 with +08:00
        normalized = value
        # Match timezone at end: +HHMM or +HH:MM
        tz_match = re.search(r"([+-])(\d{2}):?(\d{2})$", value)
        if tz_match:
            sign, hours, minutes = tz_match.groups()
            # Replace with ISO format
            normalized = value[:tz_match.start()] + f"{sign}{hours}:{minutes}"

        dt = datetime.fromisoformat(normalized)
        # Convert to UTC
        dt_utc = dt.astimezone(timezone.utc)
        # Format as ISO 8601 UTC with Z (no microseconds for cleanliness)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return value  # Return original if parsing fails


def task_10_2_normalize_timestamps() -> int:
    """Normalize ingested_at to UTC Z format."""
    print("\n=== Task 10.2: ingested_at 时区格式统一 ===")
    count = 0
    skipped = 0

    for md_path in ITEMS_DIR.glob("*.md"):
        text = md_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        frontmatter = parts[1]
        body = parts[2]

        # Find ingested_at line
        match = re.search(r'^ingested_at:\s*"([^"]+)"', frontmatter, re.MULTILINE)
        if not match:
            continue

        original = match.group(1)
        if original.endswith("Z"):
            skipped += 1
            continue

        normalized = _normalize_ingested_at(original)
        if normalized == original:
            skipped += 1
            continue

        # Update frontmatter
        new_frontmatter = re.sub(
            r'^(ingested_at:\s*")[^"]+(")',
            rf'\g<1>{normalized}\g<2>',
            frontmatter,
            flags=re.MULTILINE,
        )
        md_path.write_text(f"---{new_frontmatter}---{body}", encoding="utf-8")
        count += 1

    print(f"  Normalized: {count} items")
    print(f"  Already Z format (skipped): {skipped} items")
    return count


def main() -> None:
    print("=" * 60)
    print("Phase 1j Group X — 快速修复")
    print("=" * 60)

    c1 = task_10_1_classify_null_domain()
    c2 = task_10_2_normalize_timestamps()

    # Sync to SQLite
    print("\n=== Syncing to SQLite ===")
    from backend.services.knowledge_sync import full_sync_items_to_db
    synced = full_sync_items_to_db()
    print(f"  Synced {synced} items to SQLite")

    # Verify
    print("\n=== Verification ===")
    from backend.repository.knowledge_repo import knowledge_repo
    null_count = knowledge_repo.count_items() - knowledge_repo.count_items(domain=None) if False else None
    # Actually, let's count properly
    conn_items = knowledge_repo.list_items(limit=1000)
    null_domain = [i for i in conn_items if i.domain is None]
    print(f"  Items with domain=null: {len(null_domain)} (expected 0)")

    # Check ingested_at format
    import sqlite3
    from backend.config import config
    conn = sqlite3.connect(str(config.db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT ingested_at FROM knowledge_items WHERE ingested_at NOT LIKE '%Z' LIMIT 5"
    ).fetchall()
    print(f"  Non-Z ingested_at (sample 5): {len(rows)}")
    for r in rows:
        print(f"    {r['ingested_at']}")
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"Group X complete: {c1} classified + {c2} timestamps normalized")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
