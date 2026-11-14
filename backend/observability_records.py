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
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
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
                   error: str | None = None,
                   meta: dict[str, Any] | None = None) -> None:
    """UPDATE job_runs SET status, finished_at, duration_ms, error (+ meta_json)。

    ok=False 时必传 error (≤500 字); rowid=None (start 失败) 时本调用直接返回。
    ``meta`` (v0.8.8 P2.5 M2): job 返回的指标 dict 落 meta_json; 未传则不动该列
    (避免把 start 阶段写入的 meta 清空)。超 2,000 字符丢弃 —— job_runs 是
    20,000 行环表, meta 不承担大对象存储。
    """
    if rowid is None:
        return
    try:
        sql = ("UPDATE job_runs SET status = ?, finished_at = ?, duration_ms = ?, "
               "error = ?")
        params: list[Any] = ["ok" if ok else "failed", _now_iso(),
                             int(duration_ms),
                             (str(error)[:500] if error else None)]
        meta_json = json.dumps(meta, ensure_ascii=False, default=str) if meta else None
        if meta_json is not None and len(meta_json) <= 2000:
            sql += ", meta_json = ?"
            params.append(meta_json)
        params.append(int(rowid))
        get_connection().execute(sql + " WHERE id = ?", params)
    except Exception as e:
        log.debug(f"finish_job_run failed: {e}")


def record_missed_job_run(job_type: str, job_id: str,
                          scheduled_run_time: str) -> int | None:
    """INSERT job_runs (status='missed') — v0.8.6 P0-5 / 审计 E4。

    APScheduler 错过 ``misfire_grace_time`` 的 run 此前被静默丢弃 (55/58
    job 无补跑无记录)。本函数由 scheduler 的 EVENT_MISSED listener 调用,
    把 "丢弃" 变成显式 outcome: started_at 记计划触发时间, error 说明原因。
    job_runs.status 无 CHECK 约束, 'missed' 直接可写 (无需迁移)。
    """
    try:
        cur = get_connection().execute(
            "INSERT INTO job_runs "
            "(job_id, job_type, trace_id, started_at, status, error) "
            "VALUES (?, ?, NULL, ?, 'missed', ?)",
            (job_id, job_type, scheduled_run_time,
             "misfire: 超过 misfire_grace_time 被调度器丢弃 (E4)"),
        )
        return cur.lastrowid
    except Exception as e:
        log.debug(f"record_missed_job_run failed: {e}")
        return None


# 失败优先排序权重 (failed 最先) — 查询面与写面同文件 (job_runs 单表单一 owner)
_ORDER_RANK = (
    "CASE status WHEN 'failed' THEN 0 WHEN 'missed' THEN 1 "
    "WHEN 'running' THEN 2 ELSE 3 END"
)


def query_job_runs(*, cutoff_iso: str, statuses: list[str] | None = None,
                   job_type: str | None = None, limit: int = 50) -> list[dict]:
    """SELECT job_runs 窗口查询 (失败优先排序) — v0.8.6 P0-5 查询面。

    DEV-0287 (债务工单 D4): 自 /api/ops/runs 下沉 — api 层禁直连 SQL (R3);
    原 API 内 SQL 就地注释「不值得下沉」被 R3 守卫测试判违例, 归属反转。
    statuses=None 或含 'all' 时不加 status 过滤 (summary 语义)。
    """
    where = "started_at >= ?"
    params: list = [cutoff_iso]
    if statuses:
        where += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    if job_type:
        where += " AND job_type = ?"
        params.append(job_type)
    rows = get_connection().execute(
        f"SELECT id, job_id, job_type, status, started_at, finished_at, "
        f"duration_ms, error, trace_id FROM job_runs WHERE {where} "
        f"ORDER BY {_ORDER_RANK}, started_at DESC LIMIT ?",
        (*params, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def summarize_job_runs(*, cutoff_iso: str, stale_cutoff_iso: str) -> dict:
    """job_runs 窗口 summary (全状态计数 + stale_running 僵尸计数)。"""
    summary = dict.fromkeys(("ok", "failed", "missed", "running"), 0)
    for r in get_connection().execute(
        "SELECT status, COUNT(*) FROM job_runs WHERE started_at >= ? GROUP BY status",
        (cutoff_iso,),
    ).fetchall():
        if r[0] in summary:
            summary[r[0]] = r[1]
    summary["stale_running"] = get_connection().execute(
        "SELECT COUNT(*) FROM job_runs WHERE status='running' AND started_at < ?",
        (stale_cutoff_iso,),
    ).fetchone()[0]
    return summary


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
        conn = get_connection()
        # 写 audit_log 必须独立完成, 不污染调用方事务。
        # 若连接在 autocommit (isolation_level=None), 直接 INSERT 即可;
        # 若调用方已 BEGIN, 用 SAVEPOINT 隔离: 失败 ROLLBACK TO 仅回滚本审计行。
        iso = getattr(conn, "isolation_level", None)
        # savepoint 名是标识符插值, 白名单化字符 ( Mimosa triage T1: 防 action 携带特殊字符)
        sp_name = "sp_audit_" + re.sub(r"[^A-Za-z0-9_]", "_", action)[:40]
        in_tx = iso is not None  # isolation_level=None 表示 autocommit
        if in_tx:
            try:
                conn.execute(f"SAVEPOINT {sp_name}")
            except Exception:
                in_tx = False
        try:
            conn.execute(
                "INSERT INTO audit_log "
                "(actor, action, target, detail, trace_id, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (actor, action, target,
                 json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
                 trace_id, _now_iso()),
            )
            if in_tx:
                conn.execute(f"RELEASE SAVEPOINT {sp_name}")
        except Exception:
            if in_tx:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                except Exception:
                    pass
            raise
    except Exception as e:
        log.debug(f"record_audit failed: {e}")


# ── api_events (纯追加, v0.7 Batch ③) ──────────────────────────

def record_api_call(*, trace_id: str, method: str, path_template: str,
                    status: int, duration_ms: int,
                    error: str | None = None) -> None:
    """INSERT api_events (TraceIDMiddleware 收尾调一次).

    v0.7 Batch ③: middleware 已有 api_request/api_response log_event (文件
    日志), 本函数补 SQL 表 — 供 dashboard 查询与阈值扫. 失败 swallow,
    永不阻塞响应 (沿用 observability_records 不阻塞业务契约, PRD §10 红线 ②).

    path_template 必须用 FastAPI 路由模板 (e.g. /api/llm/status/{id}),
    不是 raw URL — 避免 query string 维度爆炸.
    """
    try:
        get_connection().execute(
            "INSERT INTO api_events "
            "(trace_id, method, path_template, status, duration_ms, error, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(trace_id), str(method).upper(), str(path_template),
             int(status), int(duration_ms),
             (str(error)[:500] if error else None), _now_iso()),
        )
    except Exception as e:
        log.debug(f"record_api_call failed: {e}")


# ── trunk stage spans (纯追加, v0.8.8 P4 R-10) ──────────────────
# 七段主干链路 (Item→Signal→Case→Claim→Run→Artifact→Knowledge) 每段的
# 写入口用 stage_span 包裹, span 行落 audit_log (R-10 "复用现表不新建表";
# PRD §4.4 R-04 已裁决 observability_records 表不存在, 实表 = audit_log):
#   actor='trunk' · action='stage.<stage>' · target='<域>:<id>' ·
#   detail={status, started_at, duration_ms[, error_code]} · trace_id 走 contextvar。
# 关闭开关: config.trunk_trace_enabled (env HOTSPOT_TRUNK_TRACE=0),
# 关闭后主链行为不变 (本模块写路径全部吞错, RA-6 fail-open)。

TRUNK_STAGES: tuple[str, ...] = (
    "item", "signal", "case", "claim", "run", "artifact", "knowledge",
)
_STAGE_ACTION_PREFIX = "stage."


def _error_code_of(exc: BaseException) -> str:
    """从异常提取失败原因码: HotspotException.code > HTTP status > 类名兜底。"""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return f"E_HTTP_{status}"
    return f"E_INTERNAL.{type(exc).__name__}"


class StageSpanHandle:
    """stage_span 的会话句柄 — 允许在函数体中段补写 target (id 产生后)。"""

    def __init__(self, target: str | None) -> None:
        self._target = target

    def set_target(self, target: str) -> None:
        """中段补写 target (如 repo.insert 产出实体 id 之后)。"""
        self._target = target


@contextmanager
def stage_span(stage: str, *, target: str | None = None) -> Iterator[StageSpanHandle]:
    """七段主干链路 span — 包住一个 stage 的写入口, 出口写一行 span。

    用法::

        with stage_span("case", target=f"case:{case_id}"):
            case = _create(req)

        # id 在函数体中段才产生时:
        with stage_span("case") as span:
            case = repo.create(payload)
            span.set_target(f"case:{case.id}")

    - 正常退出: detail.status='ok'; 异常退出: status='failed' + error_code,
      且异常原样重抛 (埋点只观测不拦截)。
    - trace_id 取当前 contextvar (HTTP 请求 = TraceIDMiddleware 注入,
      job = instrument_job 注入), 无上下文时 audit_log.trace_id 为 NULL。
    - 阶段名拼错立即 ValueError (fail loud — stage 名是查询契约的一部分)。
    - 写入失败吞掉 (record_audit 内层 + 本层 finally 双保险), 开销为一次
      本地 INSERT, 不引入跨段阻塞 (R-10 技术约束 ①②)。
    """
    if stage not in TRUNK_STAGES:
        raise ValueError(f"unknown trunk stage: {stage!r} (expected one of {TRUNK_STAGES})")
    handle = StageSpanHandle(target)
    started_mono = time.monotonic()
    started_at = _now_iso()
    error_code: str | None = None
    try:
        yield handle
    except BaseException as exc:
        error_code = _error_code_of(exc)
        raise
    finally:
        try:
            record_stage_span(
                stage, ok=error_code is None, started_at=started_at,
                duration_ms=int((time.monotonic() - started_mono) * 1000),
                target=handle._target, error_code=error_code,
            )
        except Exception as e:  # pragma: no cover — 双保险, 理论不可达
            log.debug(f"stage_span write failed: {e}")


def record_stage_span(stage: str, *, ok: bool, started_at: str, duration_ms: int,
                      target: str | None = None,
                      error_code: str | None = None) -> None:
    """写一行七段 span (stage_span 出口调用; 也可由 job 直接批量补记)。

    config.trunk_trace_enabled=False 时不写 (R-10 验收④ 关闭开关)。
    """
    from backend.config import (
        config,  # 函数内 import: 避免 config↔records 环 & 测试 monkeypatch 单例
    )

    if not config.trunk_trace_enabled:
        return
    detail: dict[str, Any] = {
        "status": "ok" if ok else "failed",
        "started_at": started_at,
        "duration_ms": int(duration_ms),
    }
    if error_code:
        detail["error_code"] = error_code
    record_audit("trunk", f"{_STAGE_ACTION_PREFIX}{stage}",
                 target=target, detail=detail)


def query_stage_spans(trace_id: str, *, limit: int = 100) -> dict:
    """按 trace_id 查七段 span, occurred_at 升序 (R-10 验收①② 的查询面)。

    返回 {trace_id, stages: [...], missing_stages: [七段中未出现的]}。
    与写面同文件 (DEV-0287 D4「查询面与写面同文件」先例)。
    """
    rows = get_connection().execute(
        "SELECT action, target, detail, occurred_at FROM audit_log "
        "WHERE trace_id = ? AND action LIKE ? "
        "ORDER BY occurred_at ASC, rowid ASC LIMIT ?",
        (trace_id, _STAGE_ACTION_PREFIX + "%", int(limit)),
    ).fetchall()
    stages: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        stage = r["action"][len(_STAGE_ACTION_PREFIX):]
        try:
            detail = json.loads(r["detail"]) if r["detail"] else {}
        except Exception:
            detail = {}
        stages.append({"stage": stage, **detail,
                       "target": r["target"], "occurred_at": r["occurred_at"]})
        seen.add(stage)
    missing = [s for s in TRUNK_STAGES if s not in seen]
    return {"trace_id": trace_id, "stages": stages, "missing_stages": missing}


__all__ = [
    "TRUNK_STAGES",
    "finish_agent_run",
    "finish_job_run",
    "query_job_runs",
    "query_stage_spans",
    "record_api_call",
    "record_audit",
    "record_missed_job_run",
    "record_process_event",
    "record_stage_span",
    "stage_span",
    "start_agent_run",
    "start_job_run",
    "summarize_job_runs",
]
