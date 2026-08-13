"""Phase 9 资讯作者核实门禁

业务背景
--------
用户反馈：KrebsOnSecurity 的 RSS feed 里抓到了 ``CVE-2026-50507``，但
实际文章 URL 指向 ``msrc.microsoft.com``，原作者应该是 ``MSRC``，不是
``KrebsOnSecurity``（Krebs 只是转载）。

逻辑
----
``AuthorVerificationGate`` 调用 :func:`resolve_publisher` 反推真实发布者，
对每个 ``HotspotItem`` 做 3 类判定：

- **match**: claimed == canonical（大小写/别名归一后）→ 奖励 +2 分
- **mismatch**: 反推出不同 canonical → 纠正 source + 扣分 + flag
- **unknown**: URL 域名不在注册表 → 仅打 flag，轻扣分

修正策略（直接改 item）
-----------------------
1. ``item.source`` 改为 ``canonical``
2. 写 ``author_corrected_to=MSRC`` 到 quality_flags
3. ``item.url_check_status = "mismatch"`` 提醒前端
4. 后续 ``_run_quality_gates`` 用 ``item.model_copy(update={quality_score,
   quality_flags, ...})`` 只覆盖 quality 字段，**不覆盖 source**——
   所以这里的修改被保留。

聚合站豁免 (2026-08-05)
------------------------
聚合源 (如 ``TopHub GitHub 热榜``) 抓的 content URL 指向真实第三方站点
(如 ``github.com/owner/repo``) 是正常业务 — 聚合站本身不是发布者。
原逻辑会把 ``TopHub GitHub 热榜`` 判为 mismatch、改写为 ``GitHub``、
设 ``url_check_status='mismatch'`` → count_by_category / query 双重
``NOT IN ('mismatch')`` 过滤 → 全员"消失"。

修复: 加 :data:`_AGGREGATOR_SOURCES` 白名单。聚合站 mismatch 时:
- 仍扣分 (PENALTY_MISMATCH) + 打 flag ``author_via_aggregator`` + 记录
  ``original_publisher=<canonical>`` (审计可追溯真实发布者)
- **不** 改 ``item.source`` (保留 "TopHub GitHub 热榜" 数据来源标记)
- **不** 设 ``url_check_status='mismatch'`` (允许 API 层正常返回)
- category 纠正 (GitHub 强制归类) 仍生效
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.collection import GateResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.publisher_registry import resolve_publisher


# 配置：扣分 + 奖励
REWARD_MATCH = 2       # 完美匹配奖励
PENALTY_MISMATCH = 10  # 域名已知但 author 不一致
PENALTY_UNKNOWN = 3    # 域名不在注册表

# canonical publisher name → 当出现这些 canonical 时,除了改 source,还要
# 把 item.category 强制纠正到对应 Category。避免 "Show HN: Wrapper" 这类
# GitHub 项目被抓到 AI 类别后,前端显示 category=AI / source=GitHub 的错乱。
# 其它 canonical (MSRC / Wikipedia / ...) 不属于"项目仓库"语义,category
# 应当保留 collector 原判断,不在此处改写。
_GITHUB_CANONICAL_NAME = "GitHub"

# 聚合站白名单 (2026-08-05): 这些 source 是"数据来源"而非"原始发布者",
# 其抓取的 content URL 指向第三方真实站点是预期行为。AuthorVerificationGate
# 对这些源 mismatch 时不再改写 source / 不设 url_check_status='mismatch',
# 避免被 API 层 url_check_status NOT IN ('mismatch') 过滤全员消失。
# 新增聚合源时: 把 source name 加到这里即可,无需改其它逻辑。
_AGGREGATOR_SOURCES: frozenset[str] = frozenset({
    "TopHub GitHub 热榜",          # tophub.today GitHub 分类聚合站
    # 未来扩展: 36氪 / 虎嗅 / 投资界 等聚合源 (Phase 19+)
})


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AuthorVerificationGate(BaseGate):
    """Per-item 门禁：验证 ``item.source`` 与 URL 域名是否一致。"""

    name: str = "AuthorVerification"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        canonical, is_match, reason = resolve_publisher(
            str(item.url), item.source
        )
        flags: list[str] = []
        score_deduction = 0
        reason_text = reason

        if is_match:
            # 完美匹配 → 奖励（用负 deduction 表示加分）
            score_deduction = -REWARD_MATCH
            reason_text = f"author_verified: {reason}"
        elif canonical is not None:
            # mismatch：纠正 + 扣分
            score_deduction = PENALTY_MISMATCH
            is_aggregator = item.source in _AGGREGATOR_SOURCES

            if is_aggregator:
                # 聚合站豁免 (2026-08-05): 保留 source = 聚合站名 (不改成
                # canonical), 不设 mismatch (避免被 API 过滤)。审计信息
                # 通过 quality_flags 保留: 真实发布者 / 聚合来源。
                flags.append("author_via_aggregator")
                flags.append(f"original_publisher={canonical}")
                reason_text = (
                    f"author_via_aggregator: claimed='{item.source}' "
                    f"is aggregator, original_publisher='{canonical}': {reason}"
                )
                # 仍可触发 category 纠正 (GitHub 项目归类到 github)
                if canonical == _GITHUB_CANONICAL_NAME:
                    if item.category != Category.GITHUB:
                        flags.append(
                            f"category_corrected_to={Category.GITHUB.value}"
                        )
                        item.category = Category.GITHUB
                # 不改 item.source, 不设 url_check_status='mismatch'
            else:
                # 常规 mismatch：纠正 source + 扣分 + flag
                flags.append("author_mismatch")
                flags.append(f"author_corrected_to={canonical}")
                reason_text = f"author_mismatch: {reason}"

                # 直接修改 item（model_copy 只覆盖 quality 字段，保留 source）
                item.source = canonical
                item.url_check_status = "mismatch"

                # 特殊：GitHub 项目被误归到 AI/SECURITY 等类别时,强制纠正 category
                # (见 _GITHUB_CANONICAL_NAME 注释)。其它 canonical 保持原 category。
                if canonical == _GITHUB_CANONICAL_NAME:
                    if item.category != Category.GITHUB:
                        flags.append(
                            f"category_corrected_to={Category.GITHUB.value}"
                        )
                        item.category = Category.GITHUB
        else:
            # unknown：仅记录 + 轻扣分
            score_deduction = PENALTY_UNKNOWN
            flags.append("author_unknown")
            reason_text = f"author_unknown: {reason}"

        return GateResult(
            gate_name=self.name,
            passed=is_match,
            score_deduction=score_deduction,
            flags=flags,
            reason=reason_text,
        )


__all__ = [
    "AuthorVerificationGate",
    "REWARD_MATCH",
    "PENALTY_MISMATCH",
    "PENALTY_UNKNOWN",
    "_AGGREGATOR_SOURCES",
]
