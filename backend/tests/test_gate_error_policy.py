"""E13/P0-12 门禁错误策略统一契约。

审计 E13: 同一个"门禁内部代码崩溃", 因异常捕获位置不同结论相反 —
- gate.check() **上抛** → pipeline ``_check_gate`` 兜底 fail-closed
  (passed=False / gate_crashed / -15);
- gate.check() **内部 try/except 调 _wrap_exception** → 旧实现
  passed=True / 零扣分 / 无 flag = 免检放行 (fail-open)。

PRD P0-12 验收: 构造 gate 异常用例, pipeline 与单 gate 断言结论一致
(均非 passed)。本测试锁定两条路径的字段级一致性 + loose/strict 聚合语义,
防止错误策略再次分叉。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal

import pytest

from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import QualityGateFailed
from backend.quality.base import BaseGate, GateContext
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.pipeline import QualityGatePipeline


class _RaisingGate(BaseGate):
    """模拟漏捕异常的 gate — 异常上抛, 由 pipeline 兜底。"""

    name = "crash_gate"
    gate_type: ClassVar[Literal["hard", "soft"]] = "soft"

    def check(self, item, context):
        raise RuntimeError("boom-raising")


class _SelfCatchingGate(BaseGate):
    """模拟现行 11 个 gate 的模式 — 内部 try/except 调 _wrap_exception。"""

    name = "crash_gate"
    gate_type: ClassVar[Literal["hard", "soft"]] = "soft"

    def check(self, item, context):
        try:
            raise RuntimeError("boom-self")
        except Exception as e:
            return self._wrap_exception(item, e)


def _item() -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id="e13-1", title="A perfectly normal title",
        summary="A perfectly normal summary with enough length.",
        source="src_x", url="https://example.com/e13-1",
        category=Category.AI, published_at=now, fetched_at=now,
    )


def _ctx() -> GateContext:
    return GateContext(mode="loose")


class _NoopLogRepo:
    def write_log(self, *a, **k):
        pass


def _pipeline(*, mode: QualityMode, gates: list[BaseGate]) -> QualityGatePipeline:
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = mode == QualityMode.STRICT
    cfg._cache["min_score"] = 30
    return QualityGatePipeline(cfg, log_repo=_NoopLogRepo(), gates=gates)


# ── 1. 单 gate 结论: 两条异常路径必须字段级一致 ─────────────────────

def test_two_exception_paths_produce_identical_results():
    """pipeline 兜底(上抛) 与 gate 自捕(_wrap_exception) 结论必须同形。

    错误类型文本允许不同 (boom-raising vs boom-self), 其余字段逐一相等。
    """
    item, ctx = _item(), _ctx()
    raising = _RaisingGate()
    catching = _SelfCatchingGate()

    p = _pipeline(mode=QualityMode.LOOSE, gates=[raising])
    via_pipeline = p._check_gate(raising, item, ctx, "loose")
    via_self = catching.check(item, ctx)

    assert via_pipeline.passed is False
    assert via_self.passed is False
    assert via_pipeline.gate_name == via_self.gate_name == "crash_gate"
    assert via_pipeline.flags == via_self.flags == ["gate_crashed"]
    assert via_pipeline.score_deduction == via_self.score_deduction == 15
    assert via_pipeline.error_msg and via_self.error_msg
    assert via_pipeline.reason == f"gate crashed: {via_pipeline.error_msg}"
    assert via_self.reason == f"gate crashed: {via_self.error_msg}"


def test_single_gate_crash_is_never_passed():
    """PRD 验收直取: 单 gate 异常结论非 passed。"""
    item, ctx = _item(), _ctx()
    assert _SelfCatchingGate().check(item, ctx).passed is False
    via_pipeline: GateResult = _pipeline(
        mode=QualityMode.LOOSE, gates=[_RaisingGate()]
    )._check_gate(_RaisingGate(), item, ctx, "loose")
    assert via_pipeline.passed is False


# ── 2. loose 聚合: 不抛, 但崩溃可见 (扣分 + flag) ───────────────────

def test_loose_mode_crashes_are_visible_not_silent():
    p = _pipeline(
        mode=QualityMode.LOOSE,
        gates=[_RaisingGate(), _SelfCatchingGate()],
    )
    result = p.run_all(_item(), _ctx())

    assert len(result.gate_results) == 2
    assert all(r.passed is False for r in result.gate_results)
    assert result.final_score == 70  # 100 - 15 - 15
    assert "gate_crashed" in result.final_flags  # merge_flags 去重, 只验存在
    # loose 不拒绝入库, 但 item 带着显式崩溃标记 (失败面板可审计)
    assert result.accepted is True


# ── 3. strict: hard gate 崩溃两条路径都拒绝 ──────────────────────────

class _RaisingHardGate(_RaisingGate):
    gate_type: ClassVar[Literal["hard", "soft"]] = "hard"


class _SelfCatchingHardGate(_SelfCatchingGate):
    gate_type: ClassVar[Literal["hard", "soft"]] = "hard"


@pytest.mark.parametrize("gate_cls", [_RaisingHardGate, _SelfCatchingHardGate])
def test_strict_mode_hard_gate_crash_rejects(gate_cls):
    """hard gate 崩溃无论上抛还是自捕, strict 下结论一致 → QualityGateFailed。"""
    p = _pipeline(mode=QualityMode.STRICT, gates=[gate_cls()])
    with pytest.raises(QualityGateFailed) as ei:
        p.run_all(_item(), _ctx())
    assert "gate_crashed" in ei.value.flags
