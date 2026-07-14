"""Noise Content gate — 检测备案号 / 版权 / 活动公告 / 招聘等噪音标题与 URL。

设计动机
--------
Bug 2 (fix-bug-github-category-dedup Task 3)：抓取器会把以下噪音当成"热点"
入库到 DB，导致 UI 出现沪 ICP 备号、版权声明、技术沙龙报名页等无效条目。

- 标题噪音：备案号、版权、隐私协议、活动公告、招聘、证券举报、广告
- URL 噪音：工信部备案查询页、javascript: / void(0) / tel: / mailto: / # 锚点

行为约定
--------
- 命中即 passed=False, deduction=100, 给出 ``noise_title`` 或 ``noise_url`` flag
- 与 ContentQualityGate 的 spam_keyword 不冲突：本 gate 是"标题整体就是噪音"
  而非 spam 营销词
- 与 DuplicateGate 独立：不去重，仅拒绝噪音
- deduction=100 ⇒ final_score=0 ⇒ strict 模式自动拒绝；loose 模式仅打 flag
  让运营/UI 层过滤
"""
from __future__ import annotations

import re

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.config import NOISE_TITLE_PATTERNS, NOISE_URL_PATTERNS

# 标题噪音命中 → deduction=100 (实质拒绝，与 schema gate 同等)
_TITLE_DEDUCTION = 100
# URL 噪音命中 → deduction=100
_URL_DEDUCTION = 100

# 预编译正则，启动期冻结
_TITLE_PATTERNS_RE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in NOISE_TITLE_PATTERNS
)
_URL_PATTERNS_RE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in NOISE_URL_PATTERNS
)


def _match_any(
    text: str, patterns: tuple[re.Pattern[str], ...]
) -> str | None:
    """返回首个命中的 pattern 字符串；未命中返回 None。"""
    for pat in patterns:
        if pat.search(text):
            return pat.pattern
    return None


class NoiseContentGate(BaseGate):
    """噪音内容门禁：检测标题/URL 是否为备案/版权/活动等噪音。"""

    name = "noise"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            flags: list[str] = []
            deduction = 0
            reasons: list[str] = []

            title = (item.title or "").strip()
            url = str(item.url or "")

            hit = _match_any(title, _TITLE_PATTERNS_RE)
            if hit:
                flags.append("noise_title")
                deduction += _TITLE_DEDUCTION
                reasons.append(f"title matched noise pattern: /{hit}/")

            hit = _match_any(url, _URL_PATTERNS_RE)
            if hit:
                flags.append("noise_url")
                deduction += _URL_DEDUCTION
                reasons.append(f"url matched noise pattern: /{hit}/")

            return GateResult(
                gate_name=self.name,
                passed=not flags,
                score_deduction=deduction,
                flags=flags,
                reason="; ".join(reasons) if reasons else None,
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["NoiseContentGate"]
