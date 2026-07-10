"""Phase 3.5 异步调度任务。

- :func:`run_url_content_check` 抽样跑 URLContent gate
- :func:`run_source_reputation_rebuild` 重算 source 信誉
"""
from __future__ import annotations

import asyncio
import random
from typing import Optional

from backend.domain.collection import GateResult
from backend.domain.enums import TimeRange
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.quality.config import QualityConfig
from backend.quality.url_content_gate import URLContentGate
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.quality_repo import QualityLogRepository

_quality_logger = logger.bind(component="quality_runner")


async def run_url_content_check(
    config: Optional[QualityConfig] = None,
) -> dict[str, int]:
    """抽样 N% 的非 fallback items 跑 :class:`URLContentGate`。

    Phase 45 增强: 同 URL 重复入库的 items (含 ``duplicate_link_real_title``
    或 ``title_replaced`` flag) 强制 100% 抽样, 必须跑门禁验证 — 否则:
    - 长 title 的 list 摘要可能错当 winner
    - URLContentGate 抽样没抽到, 错 title 永远不进 verified

    Returns
    -------
    dict with keys ``sampled / verified / mismatch / failed`` for
    scheduler / log inspection.
    """
    cfg = config or QualityConfig()
    hrepo = HotspotRepository()
    log_repo = QualityLogRepository()

    # 取最近 7d 所有 item
    items, _ = hrepo.query(category=None, time_range=TimeRange.D7, limit=200)

    # 过滤 fallback + 已有 verified/mismatch 的
    candidates = [
        it for it in items
        if not it.is_fallback
        and (it.url_check_status in (None, "pending", "skipped"))
    ]

    # Phase 45: 同 URL 重复入库的 items 强制 100% 抽样 (不参与 10% 抽样)
    duplicate_url_items = {
        it.id: it for it in candidates
        if it.quality_flags
        and ("duplicate_link_real_title" in it.quality_flags
             or "title_replaced" in it.quality_flags)
    }

    sample_n = max(1, int(len(candidates) * cfg.url_check_sample_rate))
    if sample_n == 0 and not duplicate_url_items:
        return {"sampled": 0, "verified": 0, "mismatch": 0, "failed": 0}

    # 抽样: 10% 随机 + 所有 duplicate_url_items (并集去重)
    regular_sample = (
        random.sample(candidates, min(sample_n, len(candidates)))
        if sample_n > 0 else []
    )
    sampled_set: dict[str, HotspotItem] = {it.id: it for it in regular_sample}
    sampled_set.update(duplicate_url_items)  # duplicate 全量并入
    sampled = list(sampled_set.values())

    gate = URLContentGate(timeout=cfg.url_check_timeout)
    sem = asyncio.Semaphore(cfg.url_check_concurrency)

    verified = mismatch = failed = 0
    mode = "strict" if cfg.mode.value == "strict" else "loose"

    async def _check(item: HotspotItem) -> None:
        nonlocal verified, mismatch, failed
        async with sem:
            result: GateResult = await gate.run_async(item)

        new_status = "verified"
        if not result.passed:
            if "url_mismatch" in (result.flags or []):
                new_status = "mismatch"
                mismatch += 1
            else:
                # 网络/超时失败归类为 unreachable（同步门禁 url_validity
                # 也写同一个状态，前端可按此过滤/隐藏）
                new_status = "unreachable"
                failed += 1
        else:
            verified += 1

        # 回写 url_check_status + quality_score
        try:
            new_score = max(0, item.quality_score - result.score_deduction)
            conn_path = _get_conn_for_item(item.id)
            _update_item_quality(
                item.id,
                url_check_status=new_status,
                quality_score=new_score,
            )
        except Exception as e:
            _quality_logger.warning(
                "update item quality failed",
                extra={"trace_id": "", "item_id": item.id, "error": str(e)},
            )

        log_repo.write_log(item.id, result, mode=mode)

    await asyncio.gather(*[_check(it) for it in sampled], return_exceptions=True)
    _quality_logger.info(
        "url content check done",
        extra={
            "trace_id": "",
            "sampled": len(sampled),
            "verified": verified,
            "mismatch": mismatch,
            "failed": failed,
        },
    )
    return {
        "sampled": len(sampled),
        "verified": verified,
        "mismatch": mismatch,
        "failed": failed,
    }


def run_source_reputation_rebuild() -> int:
    """重算所有 source 评分。返回更新的 source 数。"""
    from backend.repository.quality_repo import SourceReputationRepository

    repo = SourceReputationRepository()
    n = repo.rebuild_all()
    _quality_logger.info(
        "source reputation rebuilt",
        extra={"trace_id": "", "sources": n},
    )
    return n


# ---------------------------------------------------------------------------
# Helpers — 避免 import 循环
# ---------------------------------------------------------------------------
def _get_conn_for_item(item_id: str):  # pragma: no cover — trivial
    from backend.repository.db import get_connection
    return get_connection()


def _update_item_quality(
    item_id: str, *, url_check_status: str, quality_score: int
) -> None:
    from backend.repository.db import get_connection

    conn = get_connection()
    conn.execute(
        "UPDATE hotspots SET url_check_status = ?, quality_score = ? "
        "WHERE id = ?",
        (url_check_status, quality_score, item_id),
    )


__all__ = ["run_url_content_check", "run_source_reputation_rebuild"]
