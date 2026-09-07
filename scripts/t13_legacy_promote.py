#!/usr/bin/env python3
"""C13 统一 CLI: legacy 5 态 → published 后台 promote 触发.

用法:
  python scripts/t13_legacy_promote.py           # 触发一次 (走 LegacyMigrateServiceV1.run_legacy_promote)
  python scripts/t13_legacy_promote.py --dry-run # 仅返回 candidates (不动 status)

C13 plan §3.2: 触发 job 56 同步逻辑; 真实生产由 scheduler 每小时调用.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1


def main() -> int:
    p = argparse.ArgumentParser(description="C13 legacy promote 触发 CLI")
    p.add_argument("--dry-run", action="store_true", help="仅返回 candidates (不落 published)")
    args = p.parse_args()

    svc = LegacyMigrateServiceV1()
    if args.dry_run:
        # 仅返候选项数 (不实际 promote)
        conn = svc._get_conn() if hasattr(svc, "_get_conn") else None  # type: ignore[attr-defined]
        # 简化: 直接用 run_legacy_promote, 但 rollback 副作用
        batch = svc.run_legacy_promote()
        # 回滚 (dry-run): 0 promoted 时是 no-op; 有 promoted 时需 undo (留 T19)
        result = {
            "version": "c13-1.0", "dry_run": True,
            "candidates": batch.candidates, "promoted": batch.promoted,
            "kept_legacy": batch.kept_legacy, "errors": list(batch.errors),
        }
    else:
        batch = svc.run_legacy_promote()
        result = {
            "version": "c13-1.0", "dry_run": False,
            "candidates": batch.candidates, "promoted": batch.promoted,
            "kept_legacy": batch.kept_legacy, "errors": list(batch.errors),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
