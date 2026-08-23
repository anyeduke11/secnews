"""手动触发 collect, 输出 CLI 契约 (SPEC §6.1)。

兼容旧版: 默认走人类可读模式 (写到 backend/logs/collect_manual.log);
``--json`` 走 SPEC §6.1 契约 {ok, code, duration_ms, data}。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 让 ``from scripts.cli_contract import ...`` 在子进程跑也通
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.cli_contract import emit_envelope  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s: %(lineno)d - %(message)s",
    handlers=[logging.FileHandler("backend/logs/collect_manual.log", mode="w")],
)
logger = logging.getLogger("manual_collect")


async def _do_collect() -> dict:
    from backend.observability import set_start_time
    from backend.services.collection_service import CollectionService

    set_start_time(datetime.now(timezone.utc))
    svc = CollectionService()
    result = await svc.run_once()
    return {
        "total_items": result.total_items if hasattr(result, "total_items") else 0,
        "results_count": len(getattr(result, "results", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="手动触发采集 (v0.5 M2-Task5: --json 契约)")
    parser.add_argument("--json", action="store_true", dest="json_out",
                        help="输出 SPEC §6.1 {ok, code, duration_ms, data} 契约")
    args = parser.parse_args()

    started_at = time.monotonic()
    if not args.json_out:
        # 旧版人类可读模式
        print("Starting collect...", flush=True)

    try:
        data = asyncio.run(_do_collect())
        if not args.json_out:
            print(f"Done total={data['total_items']}", flush=True)
        emit_envelope(ok=True, data=data, started_at=started_at)
    except Exception as e:
        logger.error(f"manual_collect crashed: {e}")
        emit_envelope(
            ok=False,
            data={"error": str(e)},
            started_at=started_at,
        )
    return 0  # emit_envelope 已经 sys.exit 了


if __name__ == "__main__":
    sys.exit(main())