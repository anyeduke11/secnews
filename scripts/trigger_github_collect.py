"""Phase 10 一次性脚本: 单独触发 github collect, 让 audit 能看到真实数据"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.collectors.github_collector import GitHubCollector
from backend.domain.enums import Category
from backend.repository.db import close_db, init_db
from backend.repository.hotspot_repo import HotspotRepository
from backend.logging_config import setup as setup_logging
import time


async def main():
    setup_logging()
    init_db()
    print("[trigger_github_collect] starting github collector...")
    t0 = time.time()
    collector = GitHubCollector()
    # 让门禁跑过 — base.collect() 默认会跑 (除非 _skip_quality=True)
    items = await collector.collect()
    duration = round((time.time() - t0) * 1000)
    print(f"[trigger_github_collect] collected {len(items)} items in {duration}ms")
    fallback_count = sum(1 for it in items if it.is_fallback)
    real = len(items) - fallback_count
    print(f"[trigger_github_collect] non-fallback: {real}, fallback: {fallback_count}")

    # 写入 DB
    repo = HotspotRepository()
    n = repo.upsert_many(items)
    print(f"[trigger_github_collect] upserted {n} items to DB")

    # 显示质量分数
    real_items = [it for it in items if not it.is_fallback]
    if real_items:
        avg_q = sum(it.quality_score for it in real_items) / len(real_items)
        print(f"[trigger_github_collect] avg quality_score: {avg_q:.1f}")
        for it in real_items[:3]:
            print(f"  - {it.title[:60]} (qs={it.quality_score} flags={it.quality_flags})")

    close_db()


if __name__ == "__main__":
    asyncio.run(main())
