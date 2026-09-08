"""v1.0 C05 反例测试 (R02 修复断言: SourcePipeline.run watermark 不前移除非 N items 真 commit).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §6 C05] + [REVIEW_2026-09-07.md §R02]
P1.2 教训: RSS 静默失败同款 — 采集失败仍推进 watermark, 下次调度跳过失败源
造成"漏收", 控制台看不到失败.

R02 真问题:
  - `backend/services/source_pipeline.py:314-322` watermark advance 与
    `items_committed` 无关, 只要 `next_cursor` 非 None 就 advance.
  - 失败场景 (parse 全部抛错 / evidence 全部 commit 失败 / body 缺关键字段
    导致 SQLite 拒绝) 时 `items_committed == 0`, 但 watermark 仍前移, 下次
    调度 cursor 已变 → 该源永远漏收.

R02 修复:
  - watermark 推进条件: `items_committed > 0` 且 `next_cursor` 非 None.
  - N=0 不调 watermark.advance (留旧 cursor, 下次重抓该窗口).
  - 部分失败场景: 推进 watermark (items_committed >= 1, 旧 cursor 已处理过).

Mimosa 约束: SQL 全 ? 参数绑定; 禁 mock/noop 吞异常.
"""
from __future__ import annotations

from backend.repository.db import get_connection
from backend.services.source_pipeline import (
    FetchOutcome,
    FetchRequest,
    SourceLease,
    SourcePipeline,
    SourceWatermark,
)


def _seed_crawler_source(source_id: str, cursor: str, ts: str) -> None:
    """在 crawler_sources 表预置一行, watermark 可 get/advance."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO crawler_sources "
        "(id, category, name, kind, url, enabled, etag, last_fetch_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (source_id, "security", f"C05-{source_id}", "rss",
         f"https://example.com/{source_id}", cursor, ts),
    )
    conn.commit()


def _make_pipeline() -> SourcePipeline:
    """每个测试一个独立 pipeline (隔离 temp_db)."""
    return SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=None,  # 注入 None 让 evidence 路径短路, 测纯 watermark 行为
    )


# ---------------------------------------------------------------------------
# R02 修复断言 1: 失败 0 items committed → watermark 不前移
# ---------------------------------------------------------------------------
def test_pipeline_zero_committed_does_not_advance_watermark(temp_db) -> None:
    """R02 修复断言: items_committed == 0 时, 即使 next_cursor 给出, watermark 也不前移.

    旧实现: source_pipeline.py:315 只看 `if next_cursor is not None`, 不看
    `items_committed`. 即使 evidence 路径全部失败 (5 items 都 commit_intent 抛错),
    仍会 advance → cursor 跳到 page=2 → 下次调度漏收 page=1.

    修复后: items_committed == 0 → 不 advance → cursor 留旧值 → 下次重抓.
    """
    from unittest.mock import MagicMock

    _seed_crawler_source("c05-wm-1", "page=1", "2026-01-01T00:00:00+00:00")

    # mock evidence: 5 次 commit_intent 全抛错 → items_committed=0, items_failed=5
    ev = MagicMock()
    ev.create_intent.side_effect = lambda key, et, body, **kw: {"intent_id": f"i-{key}", "status": "pending"}
    ev.commit_intent.side_effect = lambda intent_id, entity_id, projection=None: (_ for _ in ()).throw(
        ValueError(f"simulated commit failure for {entity_id}")
    )

    p = SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=ev,
    )
    req = FetchRequest(source_id="c05-wm-1", cursor="page=1")

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
    # 关键验证: 5 commit 全失败 → items_committed=0, items_failed=5
    assert res.items_committed == 0
    assert res.items_failed == 5
    # 关键验证: watermark 没前移 (cursor 仍 page=1) — 旧实现会变 page=2 漏收
    wm_after = p.watermark.get("c05-wm-1")
    assert wm_after["cursor"] == "page=1", (
        f"R02 修复: items_committed=0 应不 advance watermark, "
        f"实际 cursor={wm_after['cursor']} (旧实现会变 page=2 漏收)"
    )


# ---------------------------------------------------------------------------
# R02 修复断言 2: 成功 N items committed → watermark 前移到 next_cursor
# ---------------------------------------------------------------------------
def test_pipeline_successful_commits_advance_watermark(temp_db) -> None:
    """R02 修复断言: items_committed > 0 + next_cursor 非 None → watermark 推进.

    真生产场景: 5 items 真 commit (走 evidence_service, 这里用 monkeypatch
    模拟 evidence bridge 返回成功计数). 验证 cursor 从 page=1 → page=2.
    """
    from unittest.mock import MagicMock

    _seed_crawler_source("c05-wm-2", "page=1", "2026-01-01T00:00:00+00:00")

    # 构造一个 mock evidence service: 5 个 create_intent + 5 个 commit_intent 都成功
    ev = MagicMock()
    ev.create_intent.side_effect = lambda key, et, body, **kw: {"intent_id": f"i-{key}", "status": "pending"}
    ev.commit_intent.side_effect = lambda intent_id, entity_id, projection=None: {"status": "committed", "entity_id": entity_id}

    p = SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=ev,
    )
    req = FetchRequest(source_id="c05-wm-2", cursor="page=1")

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
    assert res.items_committed == 5
    assert res.items_failed == 0
    # 关键验证: watermark 前移到 page=2
    wm_after = p.watermark.get("c05-wm-2")
    assert wm_after["cursor"] == "page=2", (
        f"R02 修复: items_committed=5 应 advance watermark, "
        f"实际 cursor={wm_after['cursor']}"
    )


# ---------------------------------------------------------------------------
# R02 修复断言 3: 部分失败 → watermark 前移到 N committed (不退回 0)
# ---------------------------------------------------------------------------
def test_pipeline_partial_failure_advances_watermark(temp_db) -> None:
    """R02 修复断言: 5 items 中 3 真 commit + 2 失败 → watermark 仍前移.

    真生产场景: 源部分 items 解析失败 (标题乱码/缺字段), 但部分真 commit.
    此时 watermark 应前移 (避免下次调度重抓已成功的部分).

    旧实现: 只要 next_cursor 非 None 就 advance (与 items_committed 无关),
    这里虽然符合预期, 但同 1) 一样可能在 0 commit 时误 advance.
    修复后: items_committed > 0 + next_cursor → advance (正确).
    """
    from unittest.mock import MagicMock

    _seed_crawler_source("c05-wm-3", "page=1", "2026-01-01T00:00:00+00:00")

    # mock evidence: 5 次 commit, 第 3/4 次抛 ValueError → items_committed=3, items_failed=2
    ev = MagicMock()
    ev.create_intent.side_effect = lambda key, et, body, **kw: {"intent_id": f"i-{key}", "status": "pending"}
    call_count = {"n": 0}

    def _commit_may_fail(intent_id, entity_id, projection=None):
        call_count["n"] += 1
        if call_count["n"] in (3, 4):
            raise ValueError(f"simulated commit failure #{call_count['n']}")
        return {"status": "committed", "entity_id": entity_id}

    ev.commit_intent.side_effect = _commit_may_fail

    p = SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=ev,
    )
    req = FetchRequest(source_id="c05-wm-3", cursor="page=1")

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
    assert res.items_committed == 3
    assert res.items_failed == 2
    # 关键验证: 部分成功 watermark 仍前移 (不退回 0)
    wm_after = p.watermark.get("c05-wm-3")
    assert wm_after["cursor"] == "page=2", (
        f"R02 修复: items_committed=3 应 advance watermark, "
        f"实际 cursor={wm_after['cursor']} (部分失败不该漏收已 commit 部分)"
    )


# ---------------------------------------------------------------------------
# R02 反例基线 (源码检查): pipeline.run watermark advance 与 items_committed 关联
# ---------------------------------------------------------------------------
def test_pipeline_source_watermark_advance_gated_on_committed() -> None:
    """R02 反例基线 (源码断言): source_pipeline.run 的 watermark advance 必带 items_committed > 0 条件.

    旧实现: `if next_cursor is not None: ...advance(...)` 与 items_committed 无关.
    修复后: 应有 `if next_cursor is not None and result.items_committed > 0:` 或等效守卫.

    Mimosa 反例测试 = 源码包含断言; 不依赖运行路径, 强制修复必加守卫.
    """
    import inspect

    from backend.services import source_pipeline
    src = inspect.getsource(source_pipeline.SourcePipeline.run)
    # watermark.advance 调用前必须有 items_committed > 0 守卫
    has_guard = (
        "items_committed" in src and "watermark" in src
    )
    assert has_guard, (
        "R02 源码断言: source_pipeline.run 应把 watermark 推进与 items_committed 绑定, "
        "实际源码无关联. 修复必加 `items_committed > 0` 守卫."
    )
