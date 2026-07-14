"""QualityGatePipeline 单元测试。

覆盖：
- 7 个同步门禁注册 + 顺序执行
- loose 模式：失败仍 accept
- strict 模式：低于阈值抛 QualityGateFailed
- fallback / QualityLogRepository 集成
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.domain.collection import GateResult, PipelineResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import QualityGateFailed
from backend.quality.base import BaseGate, GateContext
from backend.quality.category_match_gate import CategoryMatchGate
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.content_quality_gate import ContentQualityGate
from backend.quality.duplicate_gate import DuplicateGate
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.schema_gate import SchemaGate
from backend.quality.source_reputation_gate import SourceReputationGate
from backend.quality.title_summary_gate import TitleSummaryGate
from backend.quality.url_validity_gate import URLValidityGate


def _item(
    *,
    id_: str = "p1",
    title: str = "OpenAI releases new GPT agent",
    summary: str = "OpenAI new model launch with capabilities",
    source: str = "src_x",
    category: Category = Category.AI,
    url: str = "https://example.com/p1",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        summary=summary,
        source=source,
        url=url,
        category=category,
        published_at=now,
        fetched_at=now,
    )


def _ctx(
    *,
    existing_urls=None,
    existing_titles=None,
    source_reputation=None,
):
    return GateContext(
        mode="loose",
        category_keywords={
            "ai": ["AI", "OpenAI", "GPT", "agent", "model"],
            "security": ["漏洞", "hack"],
            "finance": ["股票", "Fed"],
            "startup": ["融资", "startup"],
            "bid": ["招标", "bid"],
        },
        source_reputation=source_reputation or {},
        existing_urls=set(existing_urls or []),
        existing_titles=list(existing_titles or []),
    )


class _NoopLogRepo:
    """取代 QualityLogRepository 的 stub，避免 DB 依赖。"""

    def __init__(self):
        self.written: list[tuple[str, GateResult]] = []

    def write_log(self, item_id, result, mode="loose", checked_at=None):
        self.written.append((item_id, result))


def _make_pipeline(
    *, mode: QualityMode, log: _NoopLogRepo | None = None
) -> QualityGatePipeline:
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = mode == QualityMode.STRICT
    cfg._cache["min_score"] = 30
    return QualityGatePipeline(
        cfg,
        log_repo=log or _NoopLogRepo(),
        gates=[
            SchemaGate(),
            ContentQualityGate(),
            CategoryMatchGate(),
            TitleSummaryGate(),
            SourceReputationGate(),
            DuplicateGate(),
        ],
    )


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def test_pipeline_default_gates_9():
    """默认注册的同步门禁应有 12 个(不含 url_content)。Phase 20 BidRecency + Phase 47 Recency + fix-bug-github-category-dedup Task 3 NoiseContent."""
    cfg = QualityConfig()
    p = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())
    assert len(p.gates) == 12
    names = {g.name for g in p.gates}
    assert names == {
        "schema", "recency", "content", "noise", "category_match", "title_summary",
        "url_validity", "source_reputation", "AuthorVerification", "FinalUrl", "duplicate", "bid_recency",
    }


# ---------------------------------------------------------------------------
# loose 模式：失败打 flag + 扣分，但仍 accept
# ---------------------------------------------------------------------------
def test_loose_mode_keeps_low_score_item():
    p = _make_pipeline(mode=QualityMode.LOOSE)
    item = _item(
        title="hi",  # 太短，content gate 扣 30
        summary="",
        url="https://example.com/loose1",
    )
    ctx = _ctx()
    result = p.run_all(item, ctx)
    assert isinstance(result, PipelineResult)
    # score < 100 但 accepted
    assert result.final_score < 100
    assert result.accepted is True
    assert "title_too_short" in result.final_flags


# ---------------------------------------------------------------------------
# strict 模式：score < 30 抛 QualityGateFailed
# ---------------------------------------------------------------------------
def test_strict_mode_raises_on_low_score():
    p = _make_pipeline(mode=QualityMode.STRICT)
    item = _item(
        title="hi",  # content gate 扣 30 → score 70 (still > 30)
        summary="",
        url="https://example.com/strict1",
    )
    # 多个假门禁一起扣 80 → score 20 < 30
    p.gates = [
        _AlwaysFailGate(),  # -50
        _AlwaysFailGate(),  # -50 (only counted once since dedup is 80)
    ]
    # Note: merge_flags would dedup "always_fail", but score_deduction
    # is summed; use two distinct gates instead.
    p.gates = [
        _FailGate("fail_a", 40),
        _FailGate("fail_b", 40),  # -80 total → score 20
    ]
    with pytest.raises(QualityGateFailed) as exc_info:
        p.run_all(item, _ctx())
    assert exc_info.value.score < 30
    assert exc_info.value.item_id == item.id


# ---------------------------------------------------------------------------
# 严格模式但 score ≥ 30 → 不抛
# ---------------------------------------------------------------------------
def test_strict_mode_passes_high_score():
    p = _make_pipeline(mode=QualityMode.STRICT)
    item = _item()
    # 所有门禁都通过 → score=100
    ctx = _ctx()
    # 跳过 url_validity（避免真实网络）
    p.gates = [
        SchemaGate(),
        ContentQualityGate(),
        CategoryMatchGate(),
        TitleSummaryGate(),
        SourceReputationGate(),
        DuplicateGate(),
    ]
    result = p.run_all(item, ctx)
    assert result.accepted is True
    assert result.final_score == 100


# ---------------------------------------------------------------------------
# 写 quality_check_logs
# ---------------------------------------------------------------------------
def test_pipeline_writes_logs_for_each_gate():
    log = _NoopLogRepo()
    p = _make_pipeline(mode=QualityMode.LOOSE, log=log)
    item = _item()
    p.gates = [
        SchemaGate(),
        ContentQualityGate(),
        CategoryMatchGate(),
    ]
    p.run_all(item, _ctx())
    # 每个 gate 应写 1 条 log
    assert len(log.written) == 3
    names = [r[1].gate_name for r in log.written]
    assert names == ["schema", "content", "category_match"]


# ---------------------------------------------------------------------------
# gate 异常隔离
# ---------------------------------------------------------------------------
def test_pipeline_isolates_gate_crash():
    p = _make_pipeline(mode=QualityMode.LOOSE)
    p.gates = [
        SchemaGate(),
        _CrashGate(),
        ContentQualityGate(),
    ]
    item = _item()
    result = p.run_all(item, _ctx())
    # crash gate 不影响后续
    assert result.accepted is True


# ---------------------------------------------------------------------------
# 端到端：5 个 item 混合
# ---------------------------------------------------------------------------
def test_e2e_mixed_items():
    """构造 5 个 item：1 正常 / 1 短标题 / 1 spam / 1 重复 / 1 黑名单。"""
    p = _make_pipeline(mode=QualityMode.LOOSE)
    p.gates = [
        SchemaGate(),
        ContentQualityGate(),
        CategoryMatchGate(),
        TitleSummaryGate(),
        SourceReputationGate(),
        DuplicateGate(),
    ]
    rep = {"blacklisted": {"score": 20, "blacklist": 1, "pass_count": 0, "fail_count": 5}}
    ctx = _ctx(source_reputation=rep, existing_urls=["https://example.com/dup"])

    items = [
        _item(id_="n1", title="OpenAI releases new GPT agent framework"),
        _item(id_="n2", title="hi"),  # 短标题
        _item(id_="n3", title="限时优惠点击链接"),  # spam
        _item(id_="n4", title="Normal title", url="https://example.com/dup"),
        _item(id_="n5", source="blacklisted"),
    ]

    results = [p.run_all(it, ctx) for it in items]
    assert all(isinstance(r, PipelineResult) for r in results)
    # n1 完美 → score=100
    assert results[0].final_score >= 90
    # n2 短标题 → 扣 30
    assert "title_too_short" in results[1].final_flags
    # n3 spam → 扣 30
    assert "spam_keyword" in results[2].final_flags
    # n4 重复 → 扣 50
    assert "url_duplicate" in results[3].final_flags
    # n5 黑名单 → 扣 50
    assert "blacklisted_source" in results[4].final_flags


# ---------------------------------------------------------------------------
# helpers — 假门禁
# ---------------------------------------------------------------------------
class _AlwaysFailGate(BaseGate):
    name = "always_fail"

    def check(self, item, context):
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=50,
            flags=["always_fail"],
        )


class _FailGate(BaseGate):
    def __init__(self, name: str, deduction: int):
        self.name = name
        self._deduction = deduction

    def check(self, item, context):
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=self._deduction,
            flags=[f"flag_{self.name}"],
        )


class _CrashGate(BaseGate):
    name = "crash"

    def check(self, item, context):
        raise RuntimeError("synthetic crash")
