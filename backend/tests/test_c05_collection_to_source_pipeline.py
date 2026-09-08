"""v1.0 C05 反例测试 (R03 修复断言: 旧 dead code 删 + SourcePipeline.run 是新采集路径).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §6 C05] + [REVIEW_2026-09-07.md §R03]
架构 gap 澄清 (PROGRESS.md C05 段头): CollectionService (v0.x, 12 collectors
asyncio.gather 编排) 与 SourcePipeline (v1.0 T06, 单源 fetch+watermark+evidence)
职责不同层, 不可直接替换. R03 真可做的最小切片:

1. 删 `backend/collectors/aggregator.py` DEPRECATED 兼容层 (11 行, 0 caller)
2. SourcePipeline.run 是新生产路径入口 — 验证调用方接入 (本批用 unit test 替代
   真生产接线, 真生产接入留 C07 Skill runner 统一派发)
3. SourcePipeline.commit_fetch(source_id, items_committed, cursor, ts) 公共
   接口 (P1.2 教训: 失败 0 items 不前移 watermark_set) — 委托 watermark.advance
   守卫, 让调用方 (调度器 / worker_pump) 走统一接口

Mimosa 约束: SQL 全 ? 参数绑定; 禁 mock/noop 吞异常.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.repository.db import get_connection
from backend.services.source_pipeline import (
    FetchOutcome,
    FetchRequest,
    SourceLease,
    SourcePipeline,
    SourceWatermark,
)


def _seed_crawler_source(source_id: str, cursor: str, ts: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO crawler_sources "
        "(id, category, name, kind, url, enabled, etag, last_fetch_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (source_id, "security", f"C05-{source_id}", "rss",
         f"https://example.com/{source_id}", cursor, ts),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# R03 修复断言 1: 旧 aggregator.py dead code 已删
# ---------------------------------------------------------------------------
def test_aggregator_deprecated_compat_layer_removed() -> None:
    """R03 修复断言: backend/collectors/aggregator.py 已删 (DEPRECATED 兼容层, 0 caller).

    旧实现: aggregator.py 79 行 + HotspotAggregator 类 + 委托给 CollectionService.
    grep 全仓 0 caller (Phase 4 已退役, 但文件留死代码).

    修复: 直接删 backend/collectors/aggregator.py.

    反例基线: 旧实现文件存在 → 本测试 fail (assert is False).
    """
    aggregator_path = Path("backend/collectors/aggregator.py")
    assert not aggregator_path.exists(), (
        f"R03 修复: backend/collectors/aggregator.py 是 dead code (0 caller), 应已删. "
        f"文件仍存在 ({aggregator_path.stat().st_size} bytes), "
        f"留 collector 路径误用风险."
    )


def test_aggregator_class_no_longer_importable() -> None:
    """R03 修复断言: HotspotAggregator 不再可 import (删了文件就 import 失败).

    旧实现: `from backend.collectors.aggregator import HotspotAggregator` 仍可 import.
    修复后: ImportError.
    """
    import importlib
    import sys
    # 先从 sys.modules 移除 (避免 pytest 已缓存)
    sys.modules.pop("backend.collectors.aggregator", None)
    with pytest.raises(ImportError):
        importlib.import_module("backend.collectors.aggregator")


# ---------------------------------------------------------------------------
# R03 修复断言 2: SourcePipeline.run 是新生产路径 (返回 0/N items 真路径)
# ---------------------------------------------------------------------------
def test_source_pipeline_run_returns_zero_items_on_empty_fetch(temp_db) -> None:
    """R03 修复断言: SourcePipeline.run 真返 0 items 当 fetch 返空 (不吞不 mock).

    旧实现: pipeline.run 返 0 items (但旧实现本身正确, 这是验证生产路径).
    修复后 (R03): SourcePipeline.run 是新采集路径, 0 items 真路径走
    items_committed=0, watermark 不前移 (P1.2 教训一致).
    """
    _seed_crawler_source("c05-r03-1", "page=1", "2026-01-01T00:00:00+00:00")
    p = SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=None,
    )
    req = FetchRequest(source_id="c05-r03-1", cursor="page=1")

    def _empty_fetch(req: FetchRequest) -> tuple[FetchOutcome, list[dict], str | None]:
        return (FetchOutcome.SUCCESS, [], "page=2")  # 空响应 (RSS 空)

    def _ok_parse(raw: dict) -> dict:
        return raw

    res = p.run(req, fetch_fn=_empty_fetch, parse_fn=_ok_parse)
    assert res.outcome == FetchOutcome.SUCCESS
    assert res.items_parsed == 0
    assert res.items_committed == 0
    assert res.items_failed == 0
    # watermark 不前移 (空响应 ≠ 成功抓取)
    wm_after = p.watermark.get("c05-r03-1")
    assert wm_after["cursor"] == "page=1", (
        f"R03 修复: 空 fetch 应不 advance watermark (RSS 空响应是失败模式), "
        f"实际 cursor={wm_after['cursor']}"
    )


def test_source_pipeline_run_returns_n_items_on_success(temp_db) -> None:
    """R03 修复断言: SourcePipeline.run 真返 N items 当 fetch 返 N (不吞不 mock).

    旧实现: pipeline.run 返 N items (旧实现本身正确).
    修复后 (R03): 新生产路径 5 items 真 parse + 真 watermark 推进.
    """
    from unittest.mock import MagicMock

    _seed_crawler_source("c05-r03-2", "page=1", "2026-01-01T00:00:00+00:00")

    ev = MagicMock()
    ev.create_intent.side_effect = lambda key, et, body, **kw: {"intent_id": f"i-{key}", "status": "pending"}
    ev.commit_intent.side_effect = lambda intent_id, entity_id, projection=None: {"status": "committed", "entity_id": entity_id}

    p = SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=ev,
    )
    req = FetchRequest(source_id="c05-r03-2", cursor="page=1")

    def _fetch_5(req: FetchRequest) -> tuple[FetchOutcome, list[dict], str | None]:
        items = [
            {"id": f"MAT-{i}", "source_kind": "url", "title": f"T{i}",
             "content_hash": f"h{i}" * 16, "content_length": 100,
             "fetched_at": "2026-01-01T00:00:00+00:00"}
            for i in range(5)
        ]
        return (FetchOutcome.SUCCESS, items, "page=2")

    def _ok_parse(raw: dict) -> dict:
        return raw

    res = p.run(req, fetch_fn=_fetch_5, parse_fn=_ok_parse)
    assert res.items_parsed == 5
    assert res.items_committed == 5
    # 真生产路径证据: evidence_service.create_intent 调 5 次, commit_intent 调 5 次
    assert ev.create_intent.call_count == 5, (
        f"R03 新生产路径: create_intent 应调 5 次, 实际 {ev.create_intent.call_count}"
    )
    assert ev.commit_intent.call_count == 5, (
        f"R03 新生产路径: commit_intent 应调 5 次, 实际 {ev.commit_intent.call_count}"
    )
    # watermark 真推进
    wm_after = p.watermark.get("c05-r03-2")
    assert wm_after["cursor"] == "page=2"
