"""scheduler jobs 运行时状态与插桩 (v0.6 P0-③ 自 jobs.py 搬运)。

_service 由 scheduler 注入；job_done_event/instrument_job 为全部 job 共用的
SSE 插桩。可变状态集中于此模块，门面 __init__ 经委托函数暴露，避免快照。

v0.7 Observability Batch 1 (PRD §7.1): instrument_job 在 enter/finally
写 job_runs 表 (start_job_run / finish_job_run) - 通用 job 执行历史,
覆盖 40+ job 之前 "失败只 log.error" 的缺口 (缺口④)。同时 set_trace_id
("job:<type>:<ts>"), 内部 LLM 调用 (record_llm_call) 与 api_events
等自动串联。
"""
import asyncio
import time

from backend.logging_config import logger

# 全局 service 实例（由 scheduler.py 注入）
_service = None
_logger = logger.bind(component="jobs")


def set_service(service) -> None:
    """scheduler.py 在 start() 前注入"""
    global _service
    _service = service


def reset_service() -> None:
    global _service
    _service = None


# fire-and-forget 任务的强引用集 (RUF006): 防止事件循环在任务完成前 GC 掉弱引用 task
_pending_event_tasks: set[asyncio.Task] = set()


def job_done_event(job_type: str, job_id: str, duration_ms: int, ok: bool) -> None:
    """v0.5 M2-Task5: job_done SSE 事件发布 (SPEC §6.2 契约:
    payload = {type, id, duration_ms, ok})。

    用 fire-and-forget 模式 (create_task), 不阻塞 job 主体。
    失败只 log.warning, 避免污染业务流。
    """
    try:
        from backend.api.events import publish_event
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            publish_event("job_done", {
                "type": job_type,
                "id": job_id,
                "duration_ms": duration_ms,
                "ok": ok,
            })
        )
        _pending_event_tasks.add(task)
        task.add_done_callback(_pending_event_tasks.discard)
    except Exception as e:
        _logger.warning(f"job_done_event publish failed ({job_type}/{job_id}): {e}")


def instrument_job(job_type: str):
    """装饰器: 自动包 job 函数, 完成后推 job_done SSE + 落 job_runs 表。

    v0.7 Batch 1: enter 时 set_trace_id("job:<type>:<ts>") + INSERT
    job_runs (status=running); finally UPDATE status=ok/failed +
    duration_ms + error (异常时)。成功失败都落表, 失败 finally 必走
    (不依赖异常冒泡)。所有观测写操作吞错 (沿用 PRD §10 红线 ②)。

    用法::

        @instrument_job("collect_all")
        async def collect_all_job() -> None: ...

    注意: APScheduler 直接调 job 函数, 装饰器必须在 schedule_jobs 之前完成。
    """
    def decorator(coro):
        async def wrapper(*args, **kwargs):
            started_at = time.time()
            job_id = f"{job_type}-{int(started_at)}"
            # trace_id: job:<type>:<ts> (非 UUID, 便于 grep); 同时 set contextvar
            # 让 job 内 LLM 调用 (record_llm_call) 自动串联到 llm_usage_log.trace_id
            from backend.observability import (
                reset_trace_id,
                set_trace_id,
            )
            trace_id = f"job:{job_type}:{int(started_at)}"
            trace_token = set_trace_id(trace_id)

            # INSERT job_runs (status=running), 失败 rowid=None, 收尾 noop
            from backend.observability_records import finish_job_run, start_job_run
            rowid = start_job_run(job_type=job_type, job_id=job_id,
                                  trace_id=trace_id)
            ok = False
            error_msg: str | None = None
            try:
                result = await coro(*args, **kwargs)
                ok = True
                return result
            except Exception as e:
                _logger.error(f"{job_type} crashed: {e}")
                error_msg = f"{type(e).__name__}: {e}"
                raise
            finally:
                duration_ms = int((time.time() - started_at) * 1000)
                job_done_event(job_type, job_id, duration_ms, ok)
                finish_job_run(rowid, ok=ok, duration_ms=duration_ms,
                               error=error_msg)
                reset_trace_id(trace_token)

        wrapper.__name__ = coro.__name__
        wrapper.__doc__ = coro.__doc__
        return wrapper

    return decorator
