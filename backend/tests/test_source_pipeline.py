"""v1.0 T06 源级管道测试 (FetchRequest + Lease + Watermark + 5 失败注入点).

覆盖 (对应 EXECUTION_GUIDE §4 T06 通过证据):
  1. FetchRequest 不可变 (frozen dataclass) + submission_key 稳定
  2. SourceLease acquire / extend / release / TTL 过期
  3. 同源并发 acquire 抛 LeaseHeldError
  4. SourceWatermark advance 接受新值, 倒退抛 WatermarkRegressedError
  5. Pipeline.run 正常路径: SUCCESS → parse → evidence commit
  6. Pipeline.run NOT_MODIFIED / RATE_LIMITED / TIMEOUT / BAD_BODY: 跳过 parse
  7. Pipeline.run parse 异常: items_failed++, 仍 commit 其余
  8. Pipeline.run evidence IdempotentReplay: items_idempotent++ (不重复 commit)
  9. Pipeline.run 二次同源触发 LeaseHeldError → outcome=SKIP
"""
from __future__ import annotations

import dataclasses
import threading
from datetime import datetime, timezone

import pytest

from backend.repository.db import get_connection
from backend.services.source_pipeline import (
    FetchOutcome,
    FetchRequest,
    LeaseHeldError,
    PipelineResult,
    SourceLease,
    SourcePipeline,
    SourceWatermark,
    WatermarkRegressedError,
)
from backend.services.v1_evidence_service import (
    IdempotentReplay,
    IntentExistsError,
    V1EvidenceService,
)


# ---------------------------------------------------------------------------
# 1. FetchRequest 不可变 + submission_key 稳定
# ---------------------------------------------------------------------------
def test_fetch_request_is_frozen() -> None:
    req = FetchRequest(source_id="src1", cursor="page=1", max_items=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.cursor = "page=2"  # type: ignore[misc]


def test_fetch_request_submission_key_stable() -> None:
    req = FetchRequest(source_id="src1", cursor="page=1", max_items=10, attempt=0)
    k1 = req.submission_key()
    k2 = req.submission_key()
    assert k1 == k2
    assert k1.startswith("v1-fetch-src1-")
    # 不同 attempt → 不同 key
    req2 = dataclasses.replace(req, attempt=1)
    assert req2.submission_key() != k1


# ---------------------------------------------------------------------------
# 2. SourceLease acquire / extend / release / TTL
# ---------------------------------------------------------------------------
def test_lease_acquire_release_extend() -> None:
    lease = SourceLease(ttl_sec=60)
    lease.acquire("src1")
    assert lease.is_held("src1")
    lease.extend("src1", ttl_sec=120)
    lease.release("src1")
    assert not lease.is_held("src1")


def test_lease_ttl_expiry() -> None:
    lease = SourceLease(ttl_sec=0)  # 立即过期
    lease.acquire("src1")
    import time
    time.sleep(0.05)
    # 0 秒 TTL → 任何时间查询均会 purge
    assert not lease.is_held("src1")


def test_lease_concurrent_acquire_raises() -> None:
    """同源二次 acquire → LeaseHeldError (并入 SUCCESS 路径的 9 号)."""
    lease = SourceLease(ttl_sec=60)
    lease.acquire("src1")
    with pytest.raises(LeaseHeldError):
        lease.acquire("src1")


# ---------------------------------------------------------------------------
# 4. Watermark 单调
# ---------------------------------------------------------------------------
def test_watermark_get_returns_none_for_unknown(temp_db) -> None:
    wm = SourceWatermark()
    assert wm.get("nonexistent") is None


def test_watermark_advance_and_regress(temp_db) -> None:
    """watermark 接受新值, 倒退抛 WatermarkRegressedError."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO crawler_sources (id, category, name, kind, url, enabled, etag, last_fetch_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        ("src-wm", "security", "WM Test", "rss", "https://example.com/feed", "page=1", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    wm = SourceWatermark()
    wm.advance("src-wm", "page=2", "2026-01-02T00:00:00+00:00")
    assert wm.get("src-wm")["cursor"] == "page=2"
    # 倒退 → 拒绝
    with pytest.raises(WatermarkRegressedError):
        wm.advance("src-wm", "page=0", "2026-01-01T12:00:00+00:00")


# ---------------------------------------------------------------------------
# 5-8. Pipeline.run (成功 / 失败 / 幂等 / 并发)
# ---------------------------------------------------------------------------
def _make_pipeline() -> SourcePipeline:
    """每个测试一个独立 pipeline + 独立 evidence service (隔离 temp_db)."""
    return SourcePipeline(
        lease=SourceLease(ttl_sec=60),
        watermark=SourceWatermark(),
        evidence_service=V1EvidenceService(projection_dir=None),
    )


def _ok_fetch(req: FetchRequest) -> tuple[FetchOutcome, list[dict], str | None]:
    return (
        FetchOutcome.SUCCESS,
        [
            {"id": "MAT-A", "source_kind": "url", "title": "A", "content_hash": "a" * 64, "content_length": 10, "fetched_at": "2026-01-01T00:00:00+00:00"},
            {"id": "MAT-B", "source_kind": "url", "title": "B", "content_hash": "b" * 64, "content_length": 10, "fetched_at": "2026-01-01T00:00:00+00:00"},
        ],
        "page=2",
    )


def _ok_parse(raw: dict) -> dict:
    return raw


def test_pipeline_success_commits_two_materials(temp_db) -> None:
    p = _make_pipeline()
    req = FetchRequest(source_id="src-ok", cursor="page=1")
    res = p.run(req, fetch_fn=_ok_fetch, parse_fn=_ok_parse)
    assert res.outcome == FetchOutcome.SUCCESS
    assert res.items_parsed == 2
    assert res.items_committed == 2
    assert res.items_idempotent == 0
    assert res.items_failed == 0
    assert res.duration_ms >= 0  # 真快路径可能 0ms, 仅需为 int
    assert res.next_cursor == "page=2"


@pytest.mark.parametrize(
    "outcome,raw,next_cur",
    [
        (FetchOutcome.NOT_MODIFIED, [], None),
        (FetchOutcome.RATE_LIMITED, [], None),
        (FetchOutcome.TIMEOUT, [], None),
        (FetchOutcome.BAD_BODY, [], None),
        (FetchOutcome.ERROR, [], None),
    ],
)
def test_pipeline_non_success_outcomes_skip_parse(temp_db, outcome, raw, next_cur) -> None:
    """304/429/超时/200 错页/5xx 状态机: 不解析, 不 commit."""
    p = _make_pipeline()
    req = FetchRequest(source_id=f"src-{outcome.value}", cursor="page=1")
    res = p.run(req, fetch_fn=lambda r: (outcome, raw, next_cur), parse_fn=_ok_parse)
    assert res.outcome == outcome
    assert res.items_parsed == 0
    assert res.items_committed == 0


def test_pipeline_parse_exception_increments_failed(temp_db) -> None:
    """parse 异常 → items_failed++, 仍 commit 成功的."""
    p = _make_pipeline()
    req = FetchRequest(source_id="src-parse-fail", cursor="page=1")

    def parse_one(raw: dict) -> dict:
        if raw["id"] == "MAT-A":
            raise ValueError("simulated parse crash")
        return raw

    res = p.run(req, fetch_fn=_ok_fetch, parse_fn=parse_one)
    assert res.outcome == FetchOutcome.SUCCESS
    assert res.items_parsed == 1  # B 解析成功
    assert res.items_committed == 1
    assert res.items_failed == 1


def test_pipeline_idempotent_replay(temp_db) -> None:
    """同 FetchRequest 二次 run → evidence IdempotentReplay 全部命中."""
    p = _make_pipeline()
    req = FetchRequest(source_id="src-idem", cursor="page=1")
    res1 = p.run(req, fetch_fn=_ok_fetch, parse_fn=_ok_parse)
    assert res1.items_committed == 2
    # 二次: cursor 仍 page=1, evidence 命中首次 commit → idempotent
    res2 = p.run(req, fetch_fn=_ok_fetch, parse_fn=_ok_parse)
    assert res2.items_committed == 0
    assert res2.items_idempotent == 2


def test_pipeline_concurrent_same_source_returns_skip(temp_db) -> None:
    """同源并发第二次 acquire → outcome=SKIP (不会重复 commit)."""
    p = _make_pipeline()
    req = FetchRequest(source_id="src-conc", cursor="page=1")
    # 预先持有租约, 再 run → SKIP
    p.lease.acquire("src-conc")
    res = p.run(req, fetch_fn=_ok_fetch, parse_fn=_ok_parse)
    assert res.outcome == FetchOutcome.SKIP
    assert "held by another worker" in (res.error or "")
    assert res.items_committed == 0


def test_pipeline_no_evidence_service_skips_bridge(temp_db) -> None:
    """evidence_service=None → 不报错, items_committed=0 (上游调用方负责持久化)."""
    p = SourcePipeline(lease=SourceLease(), watermark=SourceWatermark(), evidence_service=None)
    req = FetchRequest(source_id="src-no-ev", cursor="page=1")
    res = p.run(req, fetch_fn=_ok_fetch, parse_fn=_ok_parse)
    assert res.outcome == FetchOutcome.SUCCESS
    assert res.items_parsed == 2
    assert res.items_committed == 0
