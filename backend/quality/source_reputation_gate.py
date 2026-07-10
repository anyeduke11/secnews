"""Source Reputation gate — 黑名单 + 动态评分。

- 评分 < 30 → 黑名单，扣 50 分
- 评分 30-50 → 警告，扣 15 分
- flag ``blacklisted_source`` / ``low_reputation_source``
"""
from __future__ import annotations

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext


class SourceReputationGate(BaseGate):
    """来源信誉门禁。"""

    name = "source_reputation"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            rep = context.source_reputation.get(item.source)
            if rep is None:
                # 未知 source = 中性 70 分，视为通过
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            if rep.get("blacklist"):
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=50,
                    flags=["blacklisted_source"],
                    reason=f"{item.source} is blacklisted",
                )

            score = int(rep.get("score", 70))
            if score < 30:
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=50,
                    flags=["blacklisted_source"],
                    reason=f"{item.source} score={score} < 30",
                )
            if score < 50:
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=15,
                    flags=["low_reputation_source"],
                    reason=f"{item.source} score={score} < 50",
                )
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=0,
                flags=[],
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["SourceReputationGate"]
