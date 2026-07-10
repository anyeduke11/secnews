"""手动触发 collect, 直接写日志, 然后看 DB"""
import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s: %(lineno)d - %(message)s",
    handlers=[logging.FileHandler("backend/logs/collect_manual.log", mode="w")],
)
logger = logging.getLogger("manual_collect")

from backend.services.collection_service import CollectionService
from backend.observability import set_start_time
from backend.repository.hotspot_repo import HotspotRepository

async def main():
    set_start_time(datetime.now(timezone.utc))
    svc = CollectionService()
    print("Starting collect...", flush=True)
    result = await svc.run_once()
    print(f"Done total={result.total}", flush=True)

asyncio.run(main())
