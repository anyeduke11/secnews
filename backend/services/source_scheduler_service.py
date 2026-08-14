"""Source-level scheduler — per-source tick execution with priority queue and concurrency control.

Phase 3: 源级调度器负责每 60s tick 查询待调度源，按优先级 + 并发度执行单源采集。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.logging_config import logger
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.services.source_health_machine import SourceHealthMachine

_logger = logger.bind(component="source_scheduler_service")


class SourceSchedulerService:
    """源级调度器 — 每 60s tick 执行一次。
    
    Attributes:
        repo: SourceSchedulerRepository 实例
        health_machine: SourceHealthMachine 实例
        concurrency: 并发上限
        _semaphore: 并发控制信号量
        _running: set[str] 当前正在执行的源 ID 集合
    """
    
    def __init__(self, concurrency: int = 3):
        self.repo = SourceSchedulerRepository()
        self.health_machine = SourceHealthMachine()
        self.concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running: set[str] = set()
        self._collection_service = None  # injected later
    
    def attach_collection_service(self, service) -> None:
        """注入 CollectionService 实例（由 scheduler 在 start() 前调用）。"""
        self._collection_service = service
    
    async def tick(self) -> dict:
        """执行一次调度 tick。
        
        1. 查询待调度源（排除 dead/disabled/cooldown 中源）
        2. 按 priority DESC 排序，取并发度上限的源
        3. 对每个源调用 CollectionService.run_one_source()
        4. 采集完成后触发 SourceHealthMachine.apply_run_result()
        5. 写 crawler_runs 记录
        
        Returns:
            dict: {scheduled: int, succeeded: int, failed: int, skipped: int, 
                   source_results: list[dict]}
        """
        if self._collection_service is None:
            _logger.warning("collection_service not attached, skipping tick")
            return {"scheduled": 0, "succeeded": 0, "failed": 0, "skipped": 0, "source_results": []}
        
        now_iso = datetime.now(timezone.utc).isoformat()
        candidates = self.repo.get_schedulable(limit=self.concurrency, now_iso=now_iso)
        
        if not candidates:
            return {"scheduled": 0, "succeeded": 0, "failed": 0, "skipped": 0, "source_results": []}
        
        # Filter out already running sources
        sources_to_run = [s for s in candidates if s["id"] not in self._running]
        skipped = len(candidates) - len(sources_to_run)
        
        if not sources_to_run:
            return {"scheduled": 0, "succeeded": 0, "failed": 0, "skipped": skipped, "source_results": []}
        
        # Execute in parallel with concurrency control
        async def _run_one(source: dict) -> dict:
            source_id = source["id"]
            self._running.add(source_id)
            try:
                async with self._semaphore:
                    _logger.info(f"scheduler tick: running source {source_id} ({source.get('name', '')})")
                    run_result = await self._collection_service.run_one_source(source_id)
                    
                    # Apply health state machine
                    health_result = self.health_machine.apply_run_result(source_id, run_result)
                    _logger.info(
                        f"scheduler tick: source {source_id} done: "
                        f"status={run_result.get('status')} "
                        f"fetched={run_result.get('fetched_count')} "
                        f"health={health_result.get('transition', 'none')} "
                        f"state={health_result.get('new_status', '?')}"
                    )
                    
                    return {
                        "source_id": source_id,
                        "status": run_result.get("status", "failed"),
                        "fetched_count": run_result.get("fetched_count", 0),
                        "accepted_count": run_result.get("accepted_count", 0),
                        "duration_ms": run_result.get("duration_ms", 0),
                        "error_msg": run_result.get("error_msg"),
                        "health_transition": health_result.get("transition", "none"),
                        "new_status": health_result.get("new_status", "?"),
                    }
            except Exception as e:
                _logger.error(f"scheduler tick: source {source_id} crashed: {e}")
                return {
                    "source_id": source_id,
                    "status": "failed",
                    "fetched_count": 0,
                    "accepted_count": 0,
                    "duration_ms": 0,
                    "error_msg": f"{type(e).__name__}: {str(e)[:200]}",
                    "health_transition": "error",
                    "new_status": "?",
                }
            finally:
                self._running.discard(source_id)
        
        tasks = [_run_one(s) for s in sources_to_run]
        results = await asyncio.gather(*tasks)
        
        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")
        
        return {
            "scheduled": len(sources_to_run),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "source_results": results,
        }
    
    async def get_status(self) -> dict:
        """返回调度器当前状态。"""
        stats = self.repo.get_stats_summary()
        return {
            "concurrency": self.concurrency,
            "running_count": len(self._running),
            "running_sources": list(self._running),
            "stats": stats,
        }


# Module-level singleton for scheduler injection
_scheduler_instance: SourceSchedulerService | None = None


def get_scheduler_service() -> SourceSchedulerService | None:
    return _scheduler_instance


def set_scheduler_service(svc: SourceSchedulerService) -> None:
    global _scheduler_instance
    _scheduler_instance = svc


__all__ = [
    "SourceSchedulerService",
    "get_scheduler_service",
    "set_scheduler_service",
]