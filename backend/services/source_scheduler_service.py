"""Source-level scheduler — per-source tick execution with priority queue and concurrency control.

Phase 3: 源级调度器负责每 60s tick 查询待调度源，按优先级 + 并发度执行单源采集。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.logging_config import logger
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.settings_repo import SettingsRepository
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.services.source_health_machine import SourceHealthMachine

_logger = logger.bind(component="source_scheduler_service")

# ---------------------------------------------------------------------------
# 采集闭环 T4: 质量自适应 cadence (纯函数, 便于测试)
# ---------------------------------------------------------------------------
QUALITY_WINDOW = 20        # 质量信号滑动窗口 (每源最近 N 条)
QUALITY_MIN_SAMPLES = 5    # 窗口条数 < 5 → 无信号, 不调倍率
QUALITY_FAST_AT = 75.0     # avg ≥ 75 → 0.5× (加密采集)
QUALITY_SLOW_AT = 40.0     # avg < 40 → 2.0× (降频); 中间档 1.0×
CADENCE_FLOOR_S = 600.0    # 调整后下限 (防打爆), 夹取区间下界分量

# ---------------------------------------------------------------------------
# 密度门禁 T2 (2026-09-24): 三信号复合乘子 — M_r 拒收健康 / M_i 关注命中。
# 阈值集中在此常量区 (设计稿 §3 乘子表单一真相源)。
# ---------------------------------------------------------------------------
REJECTION_WINDOW_DAYS = 7    # 拒收/入库聚合窗口 (天)
REJECTION_MIN_ATTEMPTS = 10  # attempts (拒收+入库) < 10 → 无信号, 不调倍率
REJECTION_WARN_AT = 0.3      # 拒收率 r ≥ 0.3 → 1.3× (轻度降频)
REJECTION_BAD_AT = 0.6       # 拒收率 r ≥ 0.6 → 1.8× (白跑大户强降频)
INTEREST_HIT_AT = 0.5        # 命中比 h ≥ 0.5 → 0.7× (关注域加密)
INTEREST_MISS_MULT = 1.4     # h = 0 且样本足 → 1.4× (零命中降频)
INTEREST_MIN_SAMPLES = 10    # 窗口条数 < 10 → 无信号


def quality_cadence_multiplier(avg_quality: float | None, sample_count: int) -> float:
    """质量分 → cadence 倍率映射 (纯函数)。

    avg ≥ 75 → 0.5× (高质量加密采集); 40 ≤ avg < 75 → 1.0×;
    avg < 40 → 2.0× (低质量降频)。窗口样本 < ``QUALITY_MIN_SAMPLES``
    视为无信号, 恒 1.0×。
    """
    if avg_quality is None or sample_count < QUALITY_MIN_SAMPLES:
        return 1.0
    if avg_quality >= QUALITY_FAST_AT:
        return 0.5
    if avg_quality >= QUALITY_SLOW_AT:
        return 1.0
    return 2.0


def rejection_cadence_multiplier(
    rejection_rate: float | None, attempts: int
) -> float:
    """拒收率 → cadence 倍率映射 M_r (纯函数, density T2)。

    r < 0.3 → 1.0×; 0.3 ≤ r < 0.6 → 1.3×; r ≥ 0.6 → 1.8×。
    attempts (近窗口拒收+入库) < ``REJECTION_MIN_ATTEMPTS`` 视为无信号,
    恒 1.0×。
    """
    if rejection_rate is None or attempts < REJECTION_MIN_ATTEMPTS:
        return 1.0
    if rejection_rate >= REJECTION_BAD_AT:
        return 1.8
    if rejection_rate >= REJECTION_WARN_AT:
        return 1.3
    return 1.0


def interest_cadence_multiplier(
    hit_ratio: float | None, count: int, configured: bool
) -> float:
    """关注域命中比 → cadence 倍率映射 M_i (纯函数, density T2)。

    未配置关注域 (``configured=False``) 或窗口样本 < ``INTEREST_MIN_SAMPLES``
    → 恒 1.0× (用户显式意图是唯一开关); h ≥ 0.5 → 0.7×; 0 < h < 0.5 →
    1.0×; h = 0 → 1.4× (零命中降频 — 与高质量 M_q=0.5 复合得 0.7 仍加密,
    裁决②质量豁免由复合结构自然给出, 不特判)。
    """
    if not configured or count < INTEREST_MIN_SAMPLES:
        return 1.0
    if hit_ratio is None:
        return 1.0
    if hit_ratio >= INTEREST_HIT_AT:
        return 0.7
    if hit_ratio > 0:
        return 1.0
    return INTEREST_MISS_MULT


def clamp_adjusted_cadence(base_seconds: float, adjusted_seconds: float) -> float:
    """倍率乘后夹取 [max(600, base×0.25), base×4] (纯函数, 防御性)。"""
    low = max(CADENCE_FLOOR_S, base_seconds * 0.25)
    high = base_seconds * 4.0
    return min(high, max(low, adjusted_seconds))


def build_cadence_overrides(
    sources: list[dict],
    quality_stats: dict[str, dict],
    rejection_stats: dict[str, dict] | None = None,
    practice_domains: list[str] | None = None,
) -> dict[str, float]:
    """由全量源行 + 三路信号构建 cadence override 表 (纯函数, density T2 复合)。

    key 对齐: ``quality_stats`` / ``rejection_stats`` 以
    ``hotspots.source`` (源名称) 为 key, 与 ``crawler_sources.name`` 匹配
    (hotspots 入库口径); 返回表以 ``crawler_sources.id`` 为 key (调度口径)。
    倍率 = M_q × M_r × M_i 后夹取 [max(600, base×0.25), base×4]
    (夹取与 T4 一致); 倍率 1.0× 的源不入表 → 调度回落 base cadence。

    - M_r: ``rejection_stats`` 每源 ``{"rejections", "accepted"}``;
      attempts = rejections + accepted, r = rejections/attempts;
      缺源 / None → 1.0×。
    - M_i: 仅当 ``practice_domains`` 非空 (已配置) 且 ``quality_stats``
      每源含 ``hit_count`` (repo 传入关注域时才有) 时生效; 否则 1.0×。
    """
    configured = bool(practice_domains)
    overrides: dict[str, float] = {}
    for s in sources:
        name = str(s.get("name") or "")
        stat = quality_stats.get(name)
        mult_q = quality_cadence_multiplier(
            stat.get("avg_quality") if stat else None,
            stat.get("count", 0) if stat else 0,
        )
        rstat = (rejection_stats or {}).get(name)
        attempts = (
            int(rstat["rejections"]) + int(rstat["accepted"]) if rstat else 0
        )
        rate = rstat["rejections"] / attempts if rstat and attempts > 0 else None
        mult_r = rejection_cadence_multiplier(rate, attempts)
        count = stat.get("count", 0) if stat else 0
        hit_ratio = (
            stat["hit_count"] / count
            if configured and stat and "hit_count" in stat and count > 0
            else None
        )
        mult_i = interest_cadence_multiplier(hit_ratio, count, configured)
        mult = mult_q * mult_r * mult_i
        if mult == 1.0:
            continue
        base = float(s.get("cadence_seconds") or 1800)
        overrides[str(s["id"])] = clamp_adjusted_cadence(base, base * mult)
    return overrides


class SourceSchedulerService:
    """源级调度器 — 每 60s tick 执行一次。
    
    Attributes:
        repo: SourceSchedulerRepository 实例
        health_machine: SourceHealthMachine 实例
        concurrency: 并发上限
        _running: set[str] 当前正在执行的源 ID 集合
    """

    def __init__(self, concurrency: int = 3):
        self.repo = SourceSchedulerRepository()
        self.hotspot_repo = HotspotRepository()
        self.health_machine = SourceHealthMachine()
        self.concurrency = concurrency
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
        # 密度门禁 T2: 三路信号 → cadence 复合倍率, 仅作用于本次 due 计算
        # (不回写 cadence_seconds 静态配置, 可回退)。
        # - M_q: 近窗口质量分 (T4);
        # - M_r: 近 7d 拒收率 (rejections/(rejections+accepted));
        # - M_i: 关注域命中比 — 关注域从 settings.kv 读, 空 = 未配置 →
        #   M_i 恒 1.0 (用户显式意图是唯一开关, advisor/行为信号不进调度)。
        try:
            practice_domains = (
                SettingsRepository().get("interest.practice_domains", []) or []
            )
        except Exception:
            practice_domains = []
        quality_stats = self.hotspot_repo.get_recent_quality_stats(
            window=QUALITY_WINDOW,
            practice_domains=practice_domains or None,
        )
        rejection_stats = self.hotspot_repo.get_recent_rejection_stats(
            days=REJECTION_WINDOW_DAYS
        )
        cadence_overrides = build_cadence_overrides(
            self.repo.list_all(),
            quality_stats,
            rejection_stats,
            practice_domains,
        )
        candidates = self.repo.get_schedulable(
            limit=self.concurrency,
            now_iso=now_iso,
            cadence_overrides=cadence_overrides,
        )
        
        if not candidates:
            return {"scheduled": 0, "succeeded": 0, "failed": 0, "skipped": 0, "source_results": []}
        
        # Filter out already running sources
        sources_to_run = [s for s in candidates if s["id"] not in self._running]
        skipped = len(candidates) - len(sources_to_run)
        
        if not sources_to_run:
            return {"scheduled": 0, "succeeded": 0, "failed": 0, "skipped": skipped, "source_results": []}
        
        # Execute in parallel with concurrency control
        # v0.8.2 Y-A1: 全局 "source_fetch" 组预算 (惰性取, 原 __init__ 裸 Semaphore)
        from backend.utils.concurrency import get_semaphore

        sem = get_semaphore("source_fetch", size=max(1, self.concurrency))

        async def _run_one(source: dict) -> dict:
            source_id = source["id"]
            self._running.add(source_id)
            try:
                async with sem:
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
    "CADENCE_FLOOR_S",
    "INTEREST_HIT_AT",
    "INTEREST_MIN_SAMPLES",
    "INTEREST_MISS_MULT",
    "QUALITY_FAST_AT",
    "QUALITY_MIN_SAMPLES",
    "QUALITY_SLOW_AT",
    "QUALITY_WINDOW",
    "REJECTION_BAD_AT",
    "REJECTION_MIN_ATTEMPTS",
    "REJECTION_WARN_AT",
    "REJECTION_WINDOW_DAYS",
    "SourceSchedulerService",
    "build_cadence_overrides",
    "clamp_adjusted_cadence",
    "get_scheduler_service",
    "interest_cadence_multiplier",
    "quality_cadence_multiplier",
    "rejection_cadence_multiplier",
    "set_scheduler_service",
]