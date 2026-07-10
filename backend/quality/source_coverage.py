"""源覆盖度评估 — Phase 9 招标源质量门禁（run-level 评估）。

与 :class:`backend.quality.base.BaseGate` 不同，源覆盖度不是对单条
``HotspotItem`` 评估，而是对一次 collect run 的整体产出做评估：

- 统计每源的产出（基于 ``CollectionResult.source_results``）
- 调用 :class:`SourceStatsRepository.upsert_after_run` 累加
- 输出 :class:`CoverageReport`，包含
    - 每分类的源覆盖度 (active / total)
    - 死源 / 僵源列表（运维重点关注）
    - 覆盖度告警（active 数 < min_active_sources）
- 写 :class:`CoverageRunRepository.write_run` 留痕

调用方式
--------
``CollectionService.run_once`` / ``run_one`` 在 collect 完成后调用
``evaluate_source_coverage(report)``，结果以日志 + API 形式暴露。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.domain.collection import CollectionReport, CollectionResult
from backend.logging_config import logger
from backend.repository.source_stats_repo import (
    CoverageRunRepository,
    SourceStatsRepository,
)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class SourceCoverage:
    """单条源在一次 collect run 中的表现。"""

    category: str
    source_name: str
    source_url: str
    item_count: int
    error: Optional[str]
    status: str = "active"  # active/stale/dead
    zero_yield_runs: int = 0
    total_runs: int = 0
    total_items: int = 0


@dataclass
class CategoryCoverage:
    """单分类的源覆盖度。"""

    category: str
    total_sources: int
    active_sources: int
    zero_sources: int
    coverage_ratio: float
    min_active_sources: int
    alert: bool = False
    alert_reason: str = ""
    details: list[SourceCoverage] = field(default_factory=list)


@dataclass
class CoverageReport:
    """一次 collect run 的整体覆盖度。"""

    run_id: str
    categories: list[CategoryCoverage] = field(default_factory=list)
    dead_sources: list[SourceCoverage] = field(default_factory=list)
    stale_sources: list[SourceCoverage] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def has_alert(self) -> bool:
        return bool(self.alerts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "categories": [
                {
                    "category": c.category,
                    "total_sources": c.total_sources,
                    "active_sources": c.active_sources,
                    "zero_sources": c.zero_sources,
                    "coverage_ratio": round(c.coverage_ratio, 3),
                    "min_active_sources": c.min_active_sources,
                    "alert": c.alert,
                    "alert_reason": c.alert_reason,
                    "details": [
                        {
                            "source_name": d.source_name,
                            "source_url": d.source_url,
                            "item_count": d.item_count,
                            "error": d.error,
                            "status": d.status,
                            "zero_yield_runs": d.zero_yield_runs,
                            "total_runs": d.total_runs,
                            "total_items": d.total_items,
                        }
                        for d in c.details
                    ],
                }
                for c in self.categories
            ],
            "dead_sources": [
                {
                    "category": d.category,
                    "source_name": d.source_name,
                    "source_url": d.source_url,
                    "zero_yield_runs": d.zero_yield_runs,
                    "total_runs": d.total_runs,
                }
                for d in self.dead_sources
            ],
            "stale_sources": [
                {
                    "category": d.category,
                    "source_name": d.source_name,
                    "source_url": d.source_url,
                    "zero_yield_runs": d.zero_yield_runs,
                    "total_runs": d.total_runs,
                }
                for d in self.stale_sources
            ],
            "alerts": self.alerts,
            "has_alert": self.has_alert,
        }


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def _read_min_active_sources(default: int = 3) -> int:
    """读 settings 表 quality.coverage_min_active_sources。"""
    from backend.repository.db import get_connection

    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("quality.coverage_min_active_sources",),
        ).fetchone()
        if row and row["value"] is not None:
            return int(row["value"])
    except Exception:
        pass
    return default


def _make_run_id() -> str:
    """每次 collect 唯一的 run id（与 CollectionReport 共用）。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def evaluate_source_coverage(
    report: CollectionReport,
    *,
    run_id: Optional[str] = None,
    stats_repo: Optional[SourceStatsRepository] = None,
    cov_repo: Optional[CoverageRunRepository] = None,
) -> CoverageReport:
    """评估一次 collect run 的源覆盖度。

    Parameters
    ----------
    report:
        :class:`CollectionReport` — 包含每个分类的 ``source_results``。
    run_id:
        可选 run 标识符；不传则自动生成。
    stats_repo / cov_repo:
        可注入 mock 用于测试。

    Returns
    -------
    :class:`CoverageReport` 同时副作用:

    - 累加写入 ``source_stats`` 表
    - 写入 ``coverage_runs`` 快照
    - 写日志（INFO + WARNING 当有告警）
    """
    if run_id is None:
        run_id = _make_run_id()
    stats_repo = stats_repo or SourceStatsRepository()
    cov_repo = cov_repo or CoverageRunRepository()
    min_active = _read_min_active_sources(default=3)
    out = CoverageReport(run_id=run_id)

    for cr in report.results:
        cat_value = cr.category.value
        sources = cr.source_results or []
        details: list[SourceCoverage] = []
        active_n = 0
        zero_n = 0
        for sr in sources:
            sc = SourceCoverage(
                category=cat_value,
                source_name=sr.source_name,
                source_url=sr.source_url,
                item_count=sr.item_count,
                error=sr.error_msg,
            )
            details.append(sc)
            if sr.item_count >= 1:
                active_n += 1
            else:
                zero_n += 1

            # 累加写入 source_stats
            try:
                stats_repo.upsert_after_run(
                    category=cat_value,
                    source_name=sr.source_name,
                    source_url=sr.source_url,
                    item_count=sr.item_count,
                    error_msg=sr.error_msg,
                )
                # 读回最新状态
                row = stats_repo.get_one(cat_value, sr.source_name)
                if row:
                    sc.status = str(row.get("status", "active"))
                    sc.zero_yield_runs = int(row.get("zero_yield_runs") or 0)
                    sc.total_runs = int(row.get("total_runs") or 0)
                    sc.total_items = int(row.get("total_items") or 0)
                    if sc.status == "dead":
                        out.dead_sources.append(sc)
                    elif sc.status == "stale":
                        out.stale_sources.append(sc)
            except Exception as e:
                logger.warning(
                    "source_stats upsert failed",
                    extra={
                        "trace_id": "",
                        "category": cat_value,
                        "source": sr.source_name,
                        "error": str(e),
                    },
                )

        total = len(sources)
        ratio = float(active_n) / float(total) if total else 0.0
        cat_cov = CategoryCoverage(
            category=cat_value,
            total_sources=total,
            active_sources=active_n,
            zero_sources=zero_n,
            coverage_ratio=ratio,
            min_active_sources=min_active,
            details=details,
        )
        if total > 0 and active_n < min_active:
            cat_cov.alert = True
            cat_cov.alert_reason = (
                f"active_sources={active_n} < min={min_active} "
                f"(zero_yield={zero_n}/{total})"
            )
            out.alerts.append(
                f"[{cat_value}] {cat_cov.alert_reason}"
            )
        out.categories.append(cat_cov)

        # 写 coverage_runs 快照
        try:
            cov_repo.write_run(
                run_id=run_id,
                category=cat_value,
                total_sources=total,
                active_sources=active_n,
                zero_sources=zero_n,
                details=[
                    {
                        "source_name": d.source_name,
                        "source_url": d.source_url,
                        "item_count": d.item_count,
                        "error": d.error,
                        "status": d.status,
                        "zero_yield_runs": d.zero_yield_runs,
                    }
                    for d in details
                ],
            )
        except Exception as e:
            logger.warning(
                "coverage_runs write failed",
                extra={"trace_id": "", "category": cat_value, "error": str(e)},
            )

    # 汇总日志
    if out.has_alert:
        logger.warning(
            "source coverage alert",
            extra={
                "trace_id": "",
                "run_id": run_id,
                "alerts": out.alerts,
                "dead_count": len(out.dead_sources),
                "stale_count": len(out.stale_sources),
            },
        )
    else:
        logger.info(
            "source coverage ok",
            extra={
                "trace_id": "",
                "run_id": run_id,
                "dead_count": len(out.dead_sources),
                "stale_count": len(out.stale_sources),
            },
        )

    return out


__all__ = [
    "SourceCoverage",
    "CategoryCoverage",
    "CoverageReport",
    "evaluate_source_coverage",
]
