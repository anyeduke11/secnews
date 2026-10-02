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

无状态、无写操作; SQL 就地 (单表两查, 规模 <500k 行 + idx_job_runs_status_at
/ idx_job_runs_job_type_at 命中, 不值得下沉 service 层)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from backend.repository.db import get_connection

router = APIRouter(prefix="/api/ops", tags=["ops"])

_VALID_STATUS = {"running", "ok", "failed", "missed", "all"}
# 失败优先排序权重 (failed 最先)
_ORDER_RANK = "CASE status WHEN 'failed' THEN 0 WHEN 'missed' THEN 1 WHEN 'running' THEN 2 ELSE 3 END"


def _iso_hours_ago(hours: int) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


@router.get("/runs")
def list_runs(
    status: str = Query("failed,missed", description="csv 过滤; all=全部"),
    job_type: str | None = Query(None, description="job_type 精确过滤"),
    hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    cutoff = _iso_hours_ago(hours)
    conn = get_connection()

    statuses = [s.strip() for s in status.split(",") if s.strip()]
    invalid = [s for s in statuses if s not in _VALID_STATUS]
    if invalid:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {invalid}; valid={sorted(_VALID_STATUS)}",
        )
    want_all = "all" in statuses
    # 'missed' 行的 started_at=计划触发时间, 可能早于窗口 — 但窗口语义就是
    # "看这段时间该跑的", 计划时间在窗口内即命中。

    where = "started_at >= ?"
    params: list = [cutoff]
    if not want_all:
        where += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    if job_type:
        where += " AND job_type = ?"
        params.append(job_type)

    rows = conn.execute(
        f"SELECT id, job_id, job_type, status, started_at, finished_at, "
        f"duration_ms, error, trace_id FROM job_runs WHERE {where} "
        f"ORDER BY {_ORDER_RANK}, started_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()

    # summary: 窗口内全状态计数 (不受 status 过滤影响)
    summary_rows = conn.execute(
        "SELECT status, COUNT(*) FROM job_runs WHERE started_at >= ? "
        "GROUP BY status",
        (cutoff,),
    ).fetchall()
    summary = dict.fromkeys(("ok", "failed", "missed", "running"), 0)
    for r in summary_rows:
        if r[0] in summary:
            summary[r[0]] = r[1]
    # stale_running: 进程崩溃留下的僵尸 running (started_at 早于 2h 仍在跑)
    stale_cutoff = _iso_hours_ago(2)
    summary["stale_running"] = conn.execute(
        "SELECT COUNT(*) FROM job_runs WHERE status='running' AND started_at < ?",
        (stale_cutoff,),
    ).fetchone()[0]

    return {
        "runs": [dict(r) for r in rows],
        "summary": summary,
        "window_hours": hours,
        "filter_status": "all" if want_all else statuses,
    }


__all__ = ["router"]
