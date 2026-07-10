"""Phase 47: Recency gate — 资讯/标讯时效硬门禁 (适用于所有 category)。

目的
----
用户 2026-07-10 反馈: 嘶吼 (4hou.com) 源抓到的资讯混入了「历史资讯」
(2025 年甚至更早的资讯), 因为:

1. 4hou.com 没有 RSS, 走 HTML 抓取 (``_parse_html``)
2. ``_extract_published_at`` 偶尔从 HTML / URL 提取不到发布时间
3. 旧 ``_build_items`` 第 818 行 ``published_at = raw.get("published_at") or now``
   会 fallback 到 fetch time → 历史资讯被当作"当周新资讯"入库

这条门禁专门拦截两类问题:

1. **published_at 为空**:
   - 无法验证时效性 → flag ``no_published_at``, 扣 80 分 (基本 drop)
   - 例: 嘶吼首页某条 entry 旁边没有时间标签, URL 也没有日期 slug
   - 修复: collector 不再 fallback 到 now, 直接拒收

2. **published_at 早于本周一 00:00:00**:
   - 「本周一」按用户业务时区 Asia/Shanghai 计算 (与 Phase 42/46 一致)
   - 例子: 2026-07-10 (Fri) → week_start = 2026-07-06 00:00:00+08:00
   - 例子: 2026-07-06 (Mon) → week_start = 2026-07-06 00:00:00+08:00
   - 例子: 2026-07-05 (Sun) → week_start = 2026-06-29 00:00:00+08:00 (上周一)
   - ``published_at < week_start`` → flag ``historical_published``, 扣 100 分

与 :class:`BidRecencyGate` 的区别
---------------------------------
- ``BidRecencyGate`` (Phase 20) **仅作用于 bid category**, 用 180 天阈值
  + 标题年份段过滤; 已被本门禁覆盖的 180 天部分会在 Phase 47 重构中
  移除 (避免双扣分), 仅保留「标题年份段 < current_year - 1」专项过滤。
- 本门禁作用于 **所有 category** (security / bid / ai / tech / finance /
  startup / github), 是「资讯/标讯都不能早于本周一」的硬约束。

行为
----
- 失败 → flag + 扣分; 严格模式下 ``final_score < min_score`` 拒绝入库。
- 与其他门禁协同: ``ScoreBasedGate`` (Phase 19) 会用 ``historical_published``
  扣分叠加。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.domain.collection import GateResult
from backend.utils.business_days import current_week_start


class RecencyGate(BaseGate):
    """Phase 47: 资讯/标讯时效硬门禁 (所有 category)。

    判定规则:
    1. ``published_at is None`` → ``no_published_at`` flag, 扣 80 分
    2. ``published_at < current_week_start()`` → ``historical_published``
       flag, 扣 100 分
    3. 否则通过
    """

    name = "recency"

    #: 缺失 published_at 扣分
    MISSING_DEDUCTION = 80

    #: 历史资讯 (published_at < 本周一 00:00 Shanghai) 扣分
    HISTORICAL_DEDUCTION = 100

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            pub = item.published_at

            # 1) 缺失 published_at → 拒绝
            if pub is None:
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=self.MISSING_DEDUCTION,
                    flags=["no_published_at"],
                    reason="published_at is None, cannot verify recency",
                )

            # 2) published_at 早于本周一 00:00 Shanghai → 拒绝
            week_start = current_week_start()
            # 确保 pub 是 tz-aware (model validator 已强约束, 这里再兜底)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)

            if pub < week_start:
                # 计算「早多少」便于诊断
                delta = week_start - pub
                days = delta.days
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=self.HISTORICAL_DEDUCTION,
                    flags=["historical_published"],
                    reason=(
                        f"published_at {pub.isoformat()} < week_start "
                        f"{week_start.isoformat()} (by {days}d)"
                    ),
                )

            # 3) 通过
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=0,
                flags=[],
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["RecencyGate"]
