#!/usr/bin/env python3
"""C13 统一 CLI: 旧数据迁移入口 (3 源 seed/warm/wiki/all).

用法:
  python scripts/t13_legacy_migrate.py --source=warm --apply  # 真落 warm
  python scripts/t13_legacy_migrate.py --source=all --dry-run  # 全 3 源 dry-run
  python scripts/t13_legacy_migrate.py --source=warm --apply --offset=0 --limit=500 --batch-id=b-001

C13 plan §3.2: --source=seed|warm|wiki|all, --apply, --batch-id, --offset, --limit, --out
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
    p = argparse.ArgumentParser(description="C13 旧数据迁移 CLI (3 源统一)")
    p.add_argument("--source", default="all", choices=["seed", "warm", "wiki", "all"],
                   help="迁移源 (default: all)")
    p.add_argument("--apply", action="store_true", help="真落库 (默认 dry-run 仅计数)")
    p.add_argument("--batch-id", default=None, help="幂等游标 (留 None 自动生成)")
    p.add_argument("--offset", type=int, default=0, help="warm 分页起点 (ASC 游标)")
    p.add_argument("--limit", type=int, default=500, help="warm 分页大小")
    p.add_argument("--out", default=None, help="结果输出 JSON 路径 (默认 stdout)")
    args = p.parse_args()

    svc = LegacyMigrateServiceV1()
    results: dict = {"version": "c13-1.0", "apply": args.apply, "source": args.source}

    if args.source == "seed":
        bid = args.batch_id or "cli-seed"
        results["seed"] = svc.migrate_seed(apply=args.apply, batch_id=bid).to_dict()
    elif args.source == "warm":
        bid = args.batch_id or "cli-warm"
        results["warm"] = svc.migrate_warm(
            apply=args.apply, batch_id=bid, offset=args.offset, limit=args.limit,
        ).to_dict()
    elif args.source == "wiki":
        bid = args.batch_id or "cli-wiki"
        results["wiki"] = svc.migrate_wiki(apply=args.apply, batch_id=bid).to_dict()
    elif args.source == "all":
        bid = args.batch_id or "cli-all"
        results["seed"] = svc.migrate_seed(apply=args.apply, batch_id=f"{bid}-seed").to_dict()
        results["warm"] = svc.migrate_warm(
            apply=args.apply, batch_id=f"{bid}-warm",
            offset=args.offset, limit=args.limit,
        ).to_dict()
        results["wiki"] = svc.migrate_wiki(apply=args.apply, batch_id=f"{bid}-wiki").to_dict()

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"result written to {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
