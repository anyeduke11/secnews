"""Phase 21: 手动触发 security_collector 全源重采集,验证 24h 安全资讯 + author 修正"""
import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s: %(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler("backend/logs/security_collect_phase21.log", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("security_collect_phase21")

from backend.collectors.security_collector import SecurityCollector
from backend.domain.enums import Category
from backend.repository.hotspot_repo import HotspotRepository
from backend.services.collection_service import CollectionService
from backend.observability import set_start_time


async def main():
    set_start_time(datetime.now(timezone.utc))
    repo = HotspotRepository()
    collector = SecurityCollector()
    print(f"=== security 采集器共 {len(collector.sources)} 个源 ===", flush=True)
    for s in collector.sources:
        print(f"  - {s['name']} ({s['url']})", flush=True)

    print(f"\n=== 启动安全采集 (via CollectionService.run_one) ===", flush=True)
    svc = CollectionService()
    report = await svc.run_one(Category.SECURITY)
    items: list = []
    for r in report.results:
        items.extend(r.items)
    print(f"\n=== 采集完成: {len(items)} 条 (报告 total={report.total}) ===", flush=True)

    # 统计 author 情况
    src_counter: dict[str, int] = {}
    for it in items:
        src_counter[it.source] = src_counter.get(it.source, 0) + 1
    print(f"\n=== 按 source 统计 ===", flush=True)
    for src, n in sorted(src_counter.items(), key=lambda x: -x[1]):
        print(f"  {src}: {n}", flush=True)

    # 统计 DB 当前 24h 内的 security
    items_db, _ = repo.query(
        category=Category.SECURITY, time_range=__import__(
            "backend.domain.enums", fromlist=["TimeRange"]
        ).TimeRange.D3, limit=200
    )
    print(f"\n=== DB 24h 内 security: {len(items_db)} 条 ===", flush=True)
    for it in items_db[:10]:
        print(f"  - {it.source} | {it.title[:60]}", flush=True)


asyncio.run(main())
