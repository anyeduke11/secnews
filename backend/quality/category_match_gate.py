"""Category Match gate — 关键词匹配（标题/摘要必须命中分类关键词 ≥ 1 个）。

- 失败 → flag ``category_mismatch``，扣 20 分
- 严格模式：直接拒绝；宽松模式：打 flag 入库（pipeline 决定）
"""
from __future__ import annotations

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext


class CategoryMatchGate(BaseGate):
    """分类匹配门禁。"""

    name = "category_match"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            keywords = context.category_keywords.get(item.category.value, [])
            if not keywords:
                # 没有关键词 = 兜底通过
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            text = f"{item.title} {item.summary or ''}"
            hit = any(kw in text for kw in keywords)
            if hit:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=20,
                flags=["category_mismatch"],
                reason=(
                    f"no keyword from {item.category.value} "
                    f"({len(keywords)} kws) matched"
                ),
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["CategoryMatchGate"]
