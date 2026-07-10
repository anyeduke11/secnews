"""Bid Recency gate — 标讯时效性门禁 (Phase 20 + Phase 47 精简)。

目的
----
拦截标题里**直接写明历史年份段**的标讯，例如:

- 标题年份段(如 "2022-2023" / "2024 年")中,所有年份均 < ``current_year - 1``
- 例子: 2026 年, "2022-2023年项目" → 命中 "2022" < 2025 → 拒绝
- 例子: 2026 年, "2026-2029年项目" → 不命中 → 通过
- 例子: 2026 年, "2025年项目" → 命中 "2025" == 2025 → 通过(允许 1 年回看)

**Phase 47 变更**: 移除原 ``published_at age > 180d`` 检查, 该检查已被
:class:`backend.quality.recency_gate.RecencyGate` 覆盖 (本周一 00:00 硬门禁
比 180 天还严格: 任何 > 180 天的标讯必然 < 本周一)。保留本门禁专注于
「标题年份段」过滤, 避免双扣分。

行为
----
- 失败 → flag ``historical_bid_year``, 扣 30 分
- 严格模式: 直接拒绝; 宽松模式: 打 flag 入库
- 仅作用于 ``category == 'bid'`` 的 item; 非 bid 类目直接通过
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext


# 标题年份段: "2022-2023年" / "2025年" / "2024 年度" / "2023～2024 年"
# 注意: 这里用 | 兼顾半角/全角年、"年度"、"~"、"-"
_YEAR_SEGMENT_RE = re.compile(
    r"(?<![\d.])"
    r"(20\d{2})"            # 4 位年份
    r"(?:\s*[—\-～~到至]\s*(20\d{2}))?"  # 可选的年份区间
    r"(?:\s*[年年度]?)",     # 后续中文字符
    re.UNICODE,
)


def _extract_years_from_title(title: str) -> list[int]:
    """从标题抽取所有 4 位年份(20XX 形式)。"""
    if not title:
        return []
    return [int(m.group(1)) for m in _YEAR_SEGMENT_RE.finditer(title)]


class BidRecencyGate(BaseGate):
    """标讯时效性门禁 (Phase 47 精简版 — 仅保留标题年份段过滤)。

    仅作用于 ``category == 'bid'`` 的 item; 非 bid 类目直接通过。

    published_at age > 180d 的检查已下放到 :class:`RecencyGate` (本周一
    00:00 Asia/Shanghai 硬门禁, 比 180d 严格), 避免双扣分。
    """

    name = "bid_recency"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            # 非 bid 不参与
            cat_value = (
                item.category.value
                if hasattr(item.category, "value")
                else str(item.category)
            )
            if cat_value != Category.BID.value:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            now = datetime.now(timezone.utc)
            reasons: list[str] = []

            # 仅保留: 标题年份段过滤 (Phase 47: 移除 published_at age 检查)
            current_year = now.year
            years = _extract_years_from_title(item.title or "")
            # 仅看 < current_year - 1 的(允许 1 年回看)
            stale_years = [
                y for y in years
                if y < current_year - 1
            ]
            if years and len(stale_years) == len(years) and years:
                # 所有标题年份都 < current_year - 1
                reasons.append(
                    f"title years {years} all < {current_year - 1}"
                )

            if not reasons:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=30,
                flags=["historical_bid_year"],
                reason="; ".join(reasons),
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["BidRecencyGate", "_extract_years_from_title"]
