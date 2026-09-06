"""T18 旧 knowledge_items 数据迁移 CLI — dry-run + apply.

T16 旧 15 knowledge 走 dev_data/seed.json (T03 已落 v1.0 形状, 含 body);
T18 真落 853 行走 warm.knowledge_items (T00 备份演练已 attach, 18 字段无 body, migration 105 ADD body 列).

执行:
  python scripts/t18_legacy_items_migrate.py                # dry-run counts
  python scripts/t18_legacy_items_migrate.py --apply        # 真落
  python scripts/t18_legacy_items_migrate.py --check        # 仅校验
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_isolated_db() -> None:
    if os.environ.get("HOTSPOT_DB_PATH"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t18-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WARM_DB_PATH"] = str(tmp / "hotspot-warm.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


def main() -> int:
    ap = argparse.ArgumentParser(description="T18 旧 knowledge_items 数据迁移")
    ap.add_argument("--apply", action="store_true", help="真落 (走 WARM_DB → v1_knowledge)")
    ap.add_argument("--check", action="store_true", help="仅校验")
    ap.add_argument("--out", type=Path, default=None, help="result.json 落盘")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()
        from backend.repository import db
        db.init_db()

    from backend.services.legacy_items_migrate_service import LegacyItemsMigrateService
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=args.apply)

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t18-cli-")) / "result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"mode": "apply" if args.apply else "dry-run", "result": r.to_dict()},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": "apply" if args.apply else "dry-run",
                          "items_candidates": r.items_candidates,
                          "items_applied": r.items_applied,
                          "items_skipped": r.items_skipped,
                          "result": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
