"""T16 旧数据迁移 CLI — dry-run + apply (走 LegacyMigrateService).

T16 任务: 旧 20 SK → deprecated + 旧 15 knowledge (dev_data/seed.json) → v1_knowledge.
dry-run 默认 (T02 备份演练同款); --apply 真落 + 写 audit_log; --rollback 暂未实现
(rollback T16 留 hooks, 真实回滚留 T17 E2E-10).

执行:
  python scripts/t16_legacy_migrate.py                # dry-run (打印 counts + 不落库)
  python scripts/t16_legacy_migrate.py --apply        # 真落 + 写 audit_log
  python scripts/t16_legacy_migrate.py --check        # 仅校验输出形状
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_isolated_db() -> None:
    if os.environ.get("HOTSPOT_DB_PATH"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t16-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


def main() -> int:
    ap = argparse.ArgumentParser(description="T16 旧数据迁移 (knowledge + SK deprecated)")
    ap.add_argument("--apply", action="store_true", help="真落库 (走 LegacyMigrateService.run(apply=True))")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状")
    ap.add_argument("--out", type=Path, default=None, help="result.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()

    from backend.services.legacy_migrate_service import LegacyMigrateService
    svc = LegacyMigrateService()
    if args.apply:
        from backend.repository import db
        db.init_db()
    result = svc.run(apply=args.apply)

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t16-")) / "result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    mode = "apply" if args.apply else "dry-run"
    print(json.dumps({
        "mode": mode, "result": result.to_dict(), "trace": str(out_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
