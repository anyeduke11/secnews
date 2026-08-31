"""observability_records.py — v0.7 Batch 1 执行记录持久化 helper。

设计
----
观测相关的 4 张表 (job_runs / agent_runs / process_events / audit_log) 的
写入由本模块集中封装, 业务代码 (instrument_job / agent_bridge /
ProcessSupervisor) 只调语义清晰的薄包装函数, 避免在多处直接拼 SQL 与
复制 try/except 防御风格。所有写操作吞错, 永不阻塞主流程 (沿用
ai_hub/usage.py 的 "observability 不阻塞业务" 契约, PRD §10 红线 ②)。

每个表提供两类接口:
  - enter / finish: 双阶段 (开始写 running, 收尾 update status)
    适合 job / agent 这种"先 running 后 ok/failed"的语义
  - record: 单次追加, 适合 process_events / audit_log 这种纯追加语义

trace_id 一律从 observability.get_trace_id() 取 (上层 set_trace_id 后
本模块自动注入), 写入列允许 NULL 表示非 HTTP/job/agent 上下文 (例如
启动期事件)。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.observability import get_trace_id
from backend.repository.db import get_connection

log = logging.getLogger("hotspot.observability.records")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── job_runs ─────────────────────────────────────────────────────

def start_job_run(job_type: str, job_id: str, trace_id: str | None = None,
                  meta: dict[str, Any] | None = None) -> int | None:
    """INSERT job_runs (status='running')。返回 rowid, 失败返回 None。

    job_id 形式: "{job_type}-{int(time.time())}" (instrument_job 沿用约定)。
    """
    try:
        if not trace_id:
            trace_id = get_trace_id()
        cur = get_connection().execute(
            "INSERT INTO job_runs "
            "(job_id, job_type, trace_id, started_at, status, meta_json) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (job_id, job_type, trace_id, _now_iso(),
             json.dumps(meta, ensure_ascii=False) if meta else None),
        )
        return cur.lastrowid
    except Exception as e:
        log.debug(f"start_job_run failed: {e}")
        return None


def finish_job_run(rowid: int, *, ok: bool, duration_ms: int,
                   error: str | None = None) -> None:
    """UPDATE job_runs SET status, finished_at, duration_ms, error。

    ok=False 时必传 error (≤500 字); rowid=None (start 失败) 时本调用直接返回。
    """
    if rowid is None:
        return
    try:
        get_connection().execute(
            "UPDATE job_runs SET status = ?, finished_at = ?, duration_ms = ?, "
            "error = ? WHERE id = ?",
            ("ok" if ok else "failed", _now_iso(), int(duration_ms),
             (str(error)[:500] if error else None), int(rowid)),
        )
    except Exception as e:
        log.debug(f"finish_job_run failed: {e}")


# ── agent_runs ───────────────────────────────────────────────────

def start_agent_run(agent: str, protocol: str, task_kind: str | None = None,
                    trigger_source: str | None = None,
                    trace_id: str | None = None) -> int | None:
    """INSERT agent_runs (status='running')。返回 rowid。"""
    try:
        if not trace_id:
            trace_id = get_trace_id()
        cur = get_connection().execute(
            "INSERT INTO agent_runs "
            "(agent, protocol, task_kind, trigger_source, trace_id, "
            " started_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'running')",
            (agent, protocol, task_kind, trigger_source, trace_id, _now_iso()),
        )
        return cur.lastrowid
    except Exception as e:
        log.debug(f"start_agent_run failed: {e}")
        return None


def finish_agent_run(rowid: int, *, ok: bool, duration_ms: int,
                     result_excerpt: str | None = None,
                     error: str | None = None) -> None:
    """UPDATE agent_runs 收尾。rowid=None 时直接返回。"""
    if rowid is None:
        return
    try:
        get_connection().execute(
            "UPDATE agent_runs SET status = ?, finished_at = ?, duration_ms = ?, "
            "result_excerpt = ?, error = ? WHERE id = ?",
            ("ok" if ok else "failed", _now_iso(), int(duration_ms),
             (str(result_excerpt)[:500] if result_excerpt else None),
             (str(error)[:500] if error else None), int(rowid)),
        )
    except Exception as e:
        log.debug(f"finish_agent_run failed: {e}")


# ── process_events (纯追加) ──────────────────────────────────────

def record_process_event(name: str, event: str, *, pid: int | None = None,
                         uptime_s: float | None = None,
                         exit_code: int | None = None,
                         detail: str | None = None) -> None:
    """INSERT process_events (ProcessSupervisor 钩子使用)。

    event 约定: spawn | exit | restart | stop_requested | crash | health
    """
    try:
        get_connection().execute(
            "INSERT INTO process_events "
            "(name, event, pid, uptime_s, exit_code, detail, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, event, pid, uptime_s, exit_code,
             (str(detail)[:500] if detail else None), _now_iso()),
        )
    except Exception as e:
        log.debug(f"record_process_event failed: {e}")


# ── audit_log (纯追加) ──────────────────────────────────────────

def record_audit(actor: str, action: str, *, target: str | None = None,
                 detail: dict[str, Any] | None = None,
                 trace_id: str | None = None) -> None:
    """INSERT audit_log (批次②启用 LLM config 写入审计时调用)。

    actor 约定: web | system | agent:<name>
    action 约定: llm_config.update | dsh.start | dsh.stop | secrets.reveal ...
    """
    try:
        if not trace_id:
            trace_id = get_trace_id()
        get_connection().execute(
            "INSERT INTO audit_log "
            "(actor, action, target, detail, trace_id, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (actor, action, target,
             json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
             trace_id, _now_iso()),
        )
    except Exception as e:
        log.debug(f"record_audit failed: {e}")


__all__ = [
    "finish_agent_run",
    "finish_job_run",
    "record_audit",
    "record_process_event",
    "start_agent_run",
    "start_job_run",
]
