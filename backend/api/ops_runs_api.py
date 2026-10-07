"""ops_runs_api.py — /api/ops/runs: 统一 run record 查询 (v0.8.6 P0-5 / M5 最小版)。

数据源: job_runs 表 (instrument_job 注册口统一写入 + EVENT_MISSED listener
的 status='missed' 行)。PRD §2 验收: 「任一 job 失败 24h 内可在 UI 查到原因」
(G2 静默失败三类的 job 面)。

- GET /api/ops/runs
    ?status=failed,missed   (默认失败优先; all=全部; 合法值 running|ok|failed|missed|all)
    ?job_type=collect_all   (精确过滤)
    ?hours=24               (started_at 窗口)
    ?limit=50               (1..200)
返回 { runs: [...], summary: {ok, failed, missed, running, stale_running} }。
排序恒失败优先 (failed/missed 先于 running/ok, 同级按 started_at DESC)。

DEV-0287 (债务工单 D4): SQL 下沉 observability_records.query_job_runs /
summarize_job_runs — api 层禁直连 SQL (R3; 原注释「不值得下沉」被守卫测试
判违例, 归属反转为 records 单表单一 owner)。本文件只剩参数校验与装配。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from backend.observability_records import query_job_runs, summarize_job_runs

router = APIRouter(prefix="/api/ops", tags=["ops"])

_VALID_STATUS = {"running", "ok", "failed", "missed", "all"}


def _iso_hours_ago(hours: int) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


@router.get("/runs")
def list_runs(
    status: str = Query("failed,missed", description="csv 过滤; all=全部"),
    job_type: str | None = Query(None, description="job_type 精确过滤"),
    hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    from fastapi import HTTPException

    statuses = [s.strip() for s in status.split(",") if s.strip()]
    invalid = [s for s in statuses if s not in _VALID_STATUS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {invalid}; valid={sorted(_VALID_STATUS)}",
        )
    want_all = "all" in statuses
    # 'missed' 行的 started_at=计划触发时间, 可能早于窗口 — 但窗口语义就是
    # "看这段时间该跑的", 计划时间在窗口内即命中。

    runs = query_job_runs(
        cutoff_iso=_iso_hours_ago(hours),
        statuses=None if want_all else statuses,
        job_type=job_type,
        limit=limit,
    )
    summary = summarize_job_runs(
        cutoff_iso=_iso_hours_ago(hours),
        stale_cutoff_iso=_iso_hours_ago(2),
    )
    return {
        "runs": runs,
        "summary": summary,
        "window_hours": hours,
        "filter_status": "all" if want_all else statuses,
    }


__all__ = ["router"]
