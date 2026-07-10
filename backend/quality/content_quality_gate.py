"""Content Quality gate — 长度 + spam 词 + 乱码。

- 标题 8-200 字
- 摘要 0-500 字（None 视为通过）
- 20 个 spam 关键词
- 乱码：连续 5+ 个非中文/英文/数字字符
- 每条规则扣 30 分
"""
from __future__ import annotations

import re

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext

# 20 个常见 spam / 低质关键词
_SPAM_KEYWORDS: tuple[str, ...] = (
    "免费赚钱", "一夜暴富", "100% 中奖", "点击链接", "立即领取",
    "限时优惠", "稳赚不赔", "无风险套利", "内幕消息", "涨停股",
    "加微信", "加群", "日赚千元", "躺赚", "包过",
    "代刷", "代练", "破解版", "成人", "博彩",
)

# 乱码：非中文/英文/数字/常见标点的连续 5+ 个字符
_GARBLED_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9\s\.,;:!?()（）【】\-_/]{5,}")

_TITLE_MIN = 8
_TITLE_MAX = 200
_SUMMARY_MAX = 500


class ContentQualityGate(BaseGate):
    """内容质量门禁。"""

    name = "content"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            flags: list[str] = []
            deduction = 0

            title = (item.title or "").strip()
            summary = item.summary

            if len(title) < _TITLE_MIN:
                flags.append("title_too_short")
                deduction += 30
            elif len(title) > _TITLE_MAX:
                flags.append("title_too_long")
                deduction += 30

            if summary is not None and len(summary) > _SUMMARY_MAX:
                flags.append("summary_too_long")
                deduction += 30

            text_blob = title + " " + (summary or "")
            lowered = text_blob.lower()
            for kw in _SPAM_KEYWORDS:
                if kw.lower() in lowered:
                    flags.append("spam_keyword")
                    deduction += 30
                    break

            if _GARBLED_RE.search(text_blob):
                flags.append("garbled_text")
                deduction += 30

            return GateResult(
                gate_name=self.name,
                passed=not flags,
                score_deduction=deduction,
                flags=flags,
                reason="; ".join(flags) if flags else None,
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["ContentQualityGate"]
