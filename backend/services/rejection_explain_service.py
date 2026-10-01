"""拒收日志 LLM 批量解释服务 (2026-10-01 spec §4)。

post-ingest 尾部 _rejection_explain_tick 调用: 为 explain IS NULL 的
quality_rejection_log 行合并单次 pi 调用生成中文解释。词典兜底在前端
(rejectionReasons.ts), 本服务失败不写坏数据 — explain 保持 NULL 下轮重试。
"""
from __future__ import annotations

from typing import Any


def run_rejection_explain(batch_limit: int = 200) -> dict[str, int]:
    """批量解释入口。全程不抛; 返回 {"explained": N}。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, item_title, reason FROM quality_rejection_log "
        "WHERE explain IS NULL ORDER BY id DESC LIMIT ?",
        (batch_limit,),
    ).fetchall()
    if not rows:
        return {"explained": 0}

    items = [
        {"id": r["id"], "title": r["item_title"], "reason": r["reason"]}
        for r in rows
    ]
    parsed = _call_and_parse(items)
    if not parsed:
        return {"explained": 0}

    explained = 0
    for v in parsed:
        if not isinstance(v, dict):
            continue
        rid, text = v.get("id"), v.get("explain")
        if rid is None or not text or not str(text).strip():
            continue
        conn.execute(
            "UPDATE quality_rejection_log SET explain = ? WHERE id = ? "
            "AND explain IS NULL",
            (str(text).strip()[:200], rid),
        )
        explained += 1
    return {"explained": explained}


def _call_and_parse(items: list[dict[str, Any]]) -> list[Any] | None:
    """单次 LLM 调用 + 容错解析; 任何失败返回 None (调用方按 0 处理)。"""
    import asyncio
    import json as _json
    import re as _re

    try:
        from backend.services.ai_hub.gateway import llm_service
        from backend.services.ai_hub.prompts import (
            build_rejection_explain_prompt,
        )

        raw = asyncio.run(llm_service.generate(
            build_rejection_explain_prompt(items),
            task="rejection_explain",
        ))
        m = _re.search(r"\[.*\]", raw or "", _re.DOTALL)
        if not m:
            return None
        data = _json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except Exception:
        return None


__all__ = ["run_rejection_explain"]
