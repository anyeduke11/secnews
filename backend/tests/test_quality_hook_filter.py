"""QualityGatesMixin `_run_quality_gates` 拦截逻辑测试 (v4.4 P0-1/P0-2)。

覆盖两个新增的入库决策:
- P0-1: accepted=False (final_score < min_score) → item 不入库
- P0-2: 命中重复 flag → item 不入库 (全量 6 种重复 flag)
- 正常通过 → item 保留并写回 quality 字段

通过 monkeypatch QualityGatePipeline.run_all 返回预构造 PipelineResult，
隔离验证 quality_hook 的过滤决策（不依赖每个 gate 的内部实现）。
"""
import asyncio

from backend.collectors.quality_hook import QualityGatesMixin
from backend.domain.collection import PipelineResult
from backend.domain.models import HotspotItem
from backend.quality.pipeline import QualityGatePipeline


def _item(item_id: str, title: str = "测试标题 AI 大模型") -> HotspotItem:
    return HotspotItem(
        id=item_id,
        title=title,
        summary="summary",
        source="test",
        url=f"https://example.com/{item_id}",
        category="ai",
        published_at="2026-08-20T00:00:00Z",
        fetched_at="2026-08-20T00:00:00Z",
        is_fallback=False,
    )


def _result(score: int, flags: list[str], accepted: bool = True) -> PipelineResult:
    return PipelineResult(
        item_id="any",
        gate_results=[],
        final_score=score,
        final_flags=flags,
        accepted=accepted,
        mode="loose",
        reason=None,
    )


def _make_host(monkeypatch, result: PipelineResult) -> QualityGatesMixin:
    """构造 host，其 pipeline.run_all 返回给定 result。

    注意：_run_quality_gates 通过 asyncio.to_thread 调用 run_all，
    因此 fake 必须是**同步**可调用（to_thread 期望同步函数返回结果）。
    """
    def fake_run_all(self, item, ctx=None):
        return result
    monkeypatch.setattr(QualityGatePipeline, "run_all", fake_run_all)

    class Host(QualityGatesMixin):
        rejects: list[tuple[str, str]] = []
        class _L:
            def info(self, *a, **k): pass
            def warning(self, *a, **k): pass
            def error(self, *a, **k): pass
            def debug(self, *a, **k): pass
        @property
        def logger(self):
            return self._L()
        def _write_quality_rejection(self, item, rejected_by, reason):
            self.rejects.append((rejected_by, reason))

    h = Host()
    h.rejects = []
    return h


def test_accepted_false_is_rejected(monkeypatch):
    """P0-1: accepted=False (分数不足) → 不入库，写 score_below_min 拒绝日志。"""
    host = _make_host(monkeypatch, _result(30, ["title_summary_inconsistent"], accepted=False))
    out = asyncio.run(host._run_quality_gates([_item("i1")]))
    assert out == []
    assert host.rejects and host.rejects[0][0] == "score_below_min"


def test_duplicate_flag_is_rejected(monkeypatch):
    """P0-2: 命中重复 flag → 不入库，写 duplicate 拒绝日志。"""
    host = _make_host(monkeypatch, _result(60, ["url_duplicate_canonical"], accepted=True))
    out = asyncio.run(host._run_quality_gates([_item("i2")]))
    assert out == []
    assert host.rejects and host.rejects[0][0] == "duplicate"


def test_similar_title_duplicate_flag_rejected(monkeypatch):
    """P0-2: simhash 标题重复 flag → 不入库。"""
    host = _make_host(monkeypatch, _result(70, ["simhash_title_duplicate"], accepted=True))
    out = asyncio.run(host._run_quality_gates([_item("i5")]))
    assert out == []


def test_no_flags_passes_through(monkeypatch):
    """正常通过：accepted=True 且无重复 flag → 保留，写回 quality 字段。"""
    host = _make_host(monkeypatch, _result(85, [], accepted=True))
    out = asyncio.run(host._run_quality_gates([_item("i3")]))
    assert len(out) == 1
    assert out[0].quality_score == 85
    assert host.rejects == []


def test_fallback_passthrough(monkeypatch):
    """fallback 数据原样保留，不跑门禁、不入拦截逻辑。"""
    item = _item("i4")
    item.is_fallback = True
    def boom(self, *a, **k):
        raise AssertionError("fallback 不应走 pipeline.run_all")
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    host = _make_host(monkeypatch, _result(0, [], True))
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    out = asyncio.run(host._run_quality_gates([item]))
    assert out == [item]
    assert host.rejects == []


# ---------------------------------------------------------------------------
# v085-review F4 (P0-1): 门禁前 URL 预去重
# ---------------------------------------------------------------------------
def _db_item(url: str) -> HotspotItem:
    """伪造 hotspots 库内已有行 (只用到 url/title 字段)。"""
    return HotspotItem(
        id="db-row",
        title="库里已有的一条",
        summary="s",
        source="test",
        url=url,
        category="ai",
        published_at="2026-08-20T00:00:00Z",
        fetched_at="2026-08-20T00:00:00Z",
        is_fallback=False,
    )


def _stub_db(monkeypatch, urls: list[str]) -> None:
    from backend.repository.hotspot_repo import HotspotRepository

    # 2026-09-27 校对室刷屏根治: known_urls 改由 list_urls_fetched_since
    # (url-only, 真 7d 窗口) 供给; query_in_range 仅剩 title 集合职责。
    monkeypatch.setattr(
        HotspotRepository,
        "list_urls_fetched_since",
        lambda self, since_iso: set(urls),
    )
    monkeypatch.setattr(
        HotspotRepository,
        "query_in_range",
        lambda self, start=None, end=None, limit=None: ([_db_item(u) for u in urls], []),
    )


def test_pregate_url_dup_skips_gate_pipeline(monkeypatch):
    """F4: URL 与库内已有行完全一致 → 门禁 pipeline 不应被调用。"""
    _stub_db(monkeypatch, ["https://example.com/i1"])
    def boom(self, *a, **k):
        raise AssertionError("重复 URL 不应再跑全量门禁")
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    host = _make_host(monkeypatch, _result(0, [], True))
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    out = asyncio.run(host._run_quality_gates([_item("i1")]))
    assert out == []
    assert host.rejects == []  # 预筛不写 rejection 行 (避免每轮写库膨胀)


def test_pregate_canonical_match_skips(monkeypatch):
    """F4: canonical 同判 — query/www 尾斜杠差异也应命中预筛。"""
    _stub_db(monkeypatch, ["https://www.example.com/i1/?utm_source=rss"])
    def boom(self, *a, **k):
        raise AssertionError("canonical 等价 URL 不应再跑全量门禁")
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    host = _make_host(monkeypatch, _result(0, [], True))
    monkeypatch.setattr(QualityGatePipeline, "run_all", boom)
    out = asyncio.run(host._run_quality_gates([_item("i1")]))
    assert out == []


def test_pregate_new_url_passes_through(monkeypatch):
    """F4: 库内没有的新 URL → 照常走门禁并保留。"""
    _stub_db(monkeypatch, ["https://other.example/old"])
    host = _make_host(monkeypatch, _result(85, [], accepted=True))
    out = asyncio.run(host._run_quality_gates([_item("i1")]))
    assert len(out) == 1
    assert out[0].id == "i1"
    assert host.rejects == []