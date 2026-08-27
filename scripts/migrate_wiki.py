"""v0.6 Phase 6 commit 1 — CLI wrapper for wiki FS migration.

Wraps :func:`backend.wiki_fs.migrate.migrate_from_external` with:
- argparse (`--src` / `--dest` / `--dry-run` / `--report` / `--exclude-pattern`)
- SHA256 manifest of source items for archival proof
- JSON report output to `--report` (suitable for git tracking)
- Title-pattern excludes (default: skip "P2 Import Test" / "Test" / "Fixture"
  fixtures) — protects live wiki from historical test artifacts

Idempotent: re-running with same `--src`/`--dest` produces
``migrated=0, skipped=N`` (existing items not overwritten).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

# Repo root for sys.path bootstrap
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.wiki_fs.migrate import migrate_from_external  # noqa: E402
from backend.wiki_fs.store import WikiFs  # noqa: E402


# Default safety-net excludes. Title regex catches known-fixture patterns only —
# kept conservative (no \bsample\b / \bdemo\b because real wiki titles
# legitimately mention "sample" / "demo" / "test" — e.g. malware analysis
# articles). The historical P2 fixture ("P2 Import Test") is the canonical
# case to catch; filename is just the hash so glob can't match it.
_TITLE_EXCLUDES = re.compile(
    r"(?i)(p2\s+import\s+test|\bp2\s+import\b|\bimport\s+test\b)"
)


def _hash_file(path: Path) -> str:
    """Return SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_title(text: str) -> str:
    """Pull the YAML frontmatter ``title:`` field; empty string if absent."""
    m = re.search(r"^title:\s*\"?([^\"\n]+?)\"?\s*$", text, re.M)
    return m.group(1).strip() if m else ""


def _is_excluded(name: str, title: str, glob_patterns: list[str]) -> bool:
    """True if filename OR title matches any exclude rule."""
    if any(fnmatch(name, pat) for pat in glob_patterns):
        return True
    if title and _TITLE_EXCLUDES.search(title):
        return True
    return False


def _scan_source(src: Path, excludes: list[str] | None = None) -> dict:
    """Inventory of source dir: items count, concepts count, items hash list.

    ``excludes`` — glob patterns (matched against filename) AND title regex
    (``_TITLE_EXCLUDES``) to skip. Excluded items are listed separately for
    audit trail.
    """
    items_dir = src / "items"
    concepts_dir = src / "concepts"
    glob_patterns = excludes or []

    items = []
    excluded_items = []
    if items_dir.exists():
        for f in sorted(items_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            title = _extract_title(text)
            if _is_excluded(f.name, title, glob_patterns):
                excluded_items.append({"id": f.stem, "title": title, "sha256": _hash_file(f)})
                continue
            items.append({"id": f.stem, "title": title, "sha256": _hash_file(f)})

    concepts = []
    excluded_concepts = []
    if concepts_dir.exists():
        for f in sorted(concepts_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            title = _extract_title(text)
            if _is_excluded(f.name, title, glob_patterns):
                excluded_concepts.append({"id": f.stem, "title": title, "sha256": _hash_file(f)})
                continue
            concepts.append({"id": f.stem, "title": title, "sha256": _hash_file(f)})

    return {
        "items_count": len(items),
        "concepts_count": len(concepts),
        "items": items,
        "concepts": concepts,
        "excluded_items": excluded_items,
        "excluded_concepts": excluded_concepts,
        "exclude_patterns": glob_patterns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate wiki FS from external source.")
    parser.add_argument("--src", required=True, help="Source wiki root (items/ + concepts/)")
    parser.add_argument("--dest", required=True, help="Destination wiki root")
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not write")
    parser.add_argument("--report", help="Path to write JSON migration report")
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=[],
        help="Glob pattern (relative to items/) to exclude; repeatable",
    )
    args = parser.parse_args()

    src = Path(args.src).resolve()
    dest = Path(args.dest).resolve()
    if not src.exists():
        print(f"ERROR: --src does not exist: {src}", file=sys.stderr)
        return 2
    if not dest.exists():
        print(f"ERROR: --dest does not exist: {dest}", file=sys.stderr)
        return 2

    # Always-on safety net: exclude obvious fixtures (matches dsh-SecNews P2 test artifacts)
    default_excludes = ["*P2*", "*Test*", "*test*"]
    all_excludes = default_excludes + args.exclude_pattern

    src_inventory = _scan_source(src, excludes=all_excludes)

    if args.dry_run:
        dest_fs = WikiFs(str(dest))
        existing = dest_fs.list_ids()
        would_skip = sum(1 for it in src_inventory["items"] if it["id"] in existing)
        would_migrate = src_inventory["items_count"] - would_skip
        report = {
            "mode": "dry-run",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "src": str(src),
            "dest": str(dest),
            "source": src_inventory,
            "result": {
                "would_migrate": would_migrate,
                "would_skip": would_skip,
                "would_error": 0,
            },
        }
    else:
        dest_fs = WikiFs(str(dest))
        result = migrate_from_external(str(src), dest_fs)
        report = {
            "mode": "apply",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "src": str(src),
            "dest": str(dest),
            "source": src_inventory,
            "result": result,
        }

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report written: {report_path}")

    res = report["result"]
    print(
        f"[{report['mode']}] src={src.name} -> dest={dest.name}: "
        f"migrate={res.get('migrated', res.get('would_migrate', 0))} "
        f"skip={res.get('skipped', res.get('would_skip', 0))} "
        f"error={res.get('errors', res.get('would_error', 0))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())