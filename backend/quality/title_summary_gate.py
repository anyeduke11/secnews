"""Title-Summary Consistency gate — 关键词重叠度 ≥ 10%。

- 失败 → flag ``title_summary_inconsistent``，扣 15 分
"""
from __future__ import annotations

import re

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext

# 简单停用词表（中文 + 英文常见虚词）
_STOPWORDS: frozenset[str] = frozenset({
    "的", "了", "和", "是", "在", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "那", "里", "为",
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "of", "for", "with", "by", "from", "as",
    "this", "that", "it", "be", "been", "has", "have", "had", "do",
    "does", "did", "not", "no", "so", "if", "than", "then",
})

# Token 切分：中文按 1~2 字，英文按单词
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[A-Za-z]+")

_OVERLAP_THRESHOLD = 0.10


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    tokens: set[str] = set()
    for m in _CJK_RE.findall(text):
        if len(m) == 1:
            tokens.add(m)
        else:
            for i in range(len(m) - 1):
                tokens.add(m[i : i + 2])
    for m in _ASCII_RE.findall(text):
        if len(m) >= 2:
            tokens.add(m.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 0}


class TitleSummaryGate(BaseGate):
    """标题-摘要一致性门禁。"""

    name = "title_summary"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            if not item.summary:
                # 摘要为空视为通过
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            title_tokens = _tokenize(item.title)
            summary_tokens = _tokenize(item.summary)
            if not title_tokens or not summary_tokens:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            intersection = title_tokens & summary_tokens
            union = title_tokens | summary_tokens
            overlap = len(intersection) / max(1, len(union))

            if overlap >= _OVERLAP_THRESHOLD:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                )

            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=15,
                flags=["title_summary_inconsistent"],
                reason=(
                    f"overlap={overlap:.2%} < {_OVERLAP_THRESHOLD:.0%}"
                ),
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["TitleSummaryGate"]
