"""Phase 3.5 异步调度任务。

- :func:`run_url_content_check` 抽样跑 URLContent gate
- :func:`run_source_reputation_rebuild` 重算 source 信誉
"""
from __future__ import annotations

import asyncio

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
    config: QualityConfig | None = None,
) -> dict[str, int]:
    """对所有 fallback items 跑 :class:`URLContentGate`。

    Returns
    -------
    dict with keys ``sampled / verified / mismatch / failed`` for
    scheduler / log inspection.
    """
    cfg = config or QualityConfig()
    hrepo = HotspotRepository()
    log_repo = QualityLogRepository()

    # v4.4: URL 全覆盖 —— 循环翻页拉取最近 7d 全量 item（旧版 limit=200
    # 每轮只检查 200 条，导致大量积压，url_content 覆盖率长期 < 其他 gate）。
    # cursor 分页直到耗尽，再过滤出"未检查 / 需复检"的候选。
    all_items: list[HotspotItem] = []
    cursor: str | None = None
    while True:
        batch, cursor = hrepo.query(
            category=None, time_range=TimeRange.D7, cursor=cursor, limit=1000
        )
        all_items.extend(batch)
        if not cursor or not batch:
            break
        if len(all_items) > 20000:  # 防御上限, 避免异常下无限循环
            break

    # 过滤 fallback + 已有 verified/mismatch 的
    # P2-4: unreachable 加入复检候选 — 此前仅 None/pending/skipped,
    # 瞬时网络失败被标 unreachable 后永不复检 → 一条资讯永久隐藏。
    candidates = [
        it for it in all_items
        if not it.is_fallback
        and (it.url_check_status in (None, "pending", "skipped", "unreachable"))
    ]

    if not candidates:
        return {"sampled": 0, "verified": 0, "mismatch": 0, "failed": 0}

    # 全部 candidates 都跑 URL 检查
    sampled = list(candidates)

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
            # conn_path 占位 — 预留给 Phase 后续按 item.id 分库场景
            _conn_path = _get_conn_for_item(item.id)
            del _conn_path  # noqa: F841
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


__all__ = ["run_source_reputation_rebuild", "run_url_content_check"]
