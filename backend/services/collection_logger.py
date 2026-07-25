"""v1.9 Phase 9 — 资讯抓取流程标准化: 结构化事件日志.

设计
----
- 单一入口 ``log_collect_event(event, **fields)``
- 复用 :func:`backend.observability.log_event` (loguru/info level)
- 标准化字段 (snake_case):
  - run_id, mode, category, source, items, duration_ms
  - error (truncated 200 chars)
  - extra (任意附加字段)

事件类型
--------
- collect_start: 一次 catchup/collect_all 开始
- source_start: 某个 source 开始抓取
- source_done: 某个 source 成功 (含 items)
- source_failed: 某个 source 失败
- source_skipped: 跨 run 续传时跳过
- collect_done: run 终态 (success/partial/failed/aborted)
- validate_done: 数据完整性验证完成
- gap_detected: 时间窗口空隙 (>1h 无 ingest)
- source_regression: 源退化 (历史有产出, 本次 0)

输出示例
--------
```
event=collect_start run_id=42 mode=manual since=2026-07-21T00:00:00+08:00
event=source_done run_id=42 category=ai source=hacker_news items=15 duration_ms=2300
event=collect_done run_id=42 status=success items_ingested=109 sources_succeeded=7
```
"""
from __future__ import annotations

import json
from typing import Any, Optional

from backend.observability import log_event as _base_log_event


# 标准字段白名单 (在 log_collect_event 中强制 snake_case)
_KNOWN_FIELDS = {
    "run_id",
    "mode",
    "category",
    "source",
    "source_name",  # alias for source
    "since",
    "until",
    "max_per_source",
    "items",
    "items_ingested",
    "items_skipped",
    "sources_attempted",
    "sources_succeeded",
    "duration_ms",
    "status",
    "error",
    "checkpoint_status",  # pending/done/failed/skipped
}


def _normalize(event: str, fields: dict[str, Any]) -> dict[str, Any]:
    """规范化字段:
    - source_name → source (统一语义)
    - error 截断 200 字符
    - 数字字段转 int
    """
    out: dict[str, Any] = {"event": event}
    for k, v in fields.items():
        if k == "source_name":
            out["source"] = str(v)
        elif k == "error" and isinstance(v, str):
            out[k] = v[:200]
        elif k in ("run_id", "sources_attempted", "sources_succeeded",
                   "items", "items_ingested", "items_skipped", "duration_ms",
                   "max_per_source"):
            try:
                out[k] = int(v) if v is not None else 0
            except (TypeError, ValueError):
                out[k] = 0
        else:
            out[k] = v
    return out


def log_collect_event(event: str, **fields: Any) -> None:
    """统一入口: 调 :func:`backend.observability.log_event` 输出结构化日志.

    Parameters
    ----------
    event : str
        事件类型 (见模块 docstring).
    **fields :
        任意字段, 常见字段见 _KNOWN_FIELDS.
    """
    payload = _normalize(event, fields)
    # observability.log_event 接受 event + **fields
    # 这里把 event 作为 keyword, 其余作为 fields
    _base_log_event(**payload)


def log_validation(
    run_id: int,
    validation_type: str,
    severity: str,
    payload: dict[str, Any],
) -> None:
    """便利: 写一条 validation 事件.

    severity: info / warn / error
    """
    log_collect_event(
        "validation",
        run_id=int(run_id),
        validation_type=validation_type,
        severity=severity,
        payload=json.dumps(payload, ensure_ascii=False)[:500],
    )


__all__ = [
    "log_collect_event",
    "log_validation",
]
