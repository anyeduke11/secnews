"""AI 生成内容 / 营销软文检测门禁 (v4.4).

第一性原理目标
--------------
情报质量的核心风险之一：AI 批量生成的低信息密度内容 / 营销软文涌入资讯流，
稀释真实情报价值。本门禁从「信息密度」与「内容形态」两个维度检测。

分层实现
--------
1. **启发式（默认，零调用）**：纯文本信号打分 —— 标题空洞 / 关键词密集
   堆砌 / 复读句式 / 无实质信息等。离线可用，不产生任何网络请求。
2. **LLM 增强（可选）**：委托集中式 ``ai_service.gate_detect()`` 判断是否为
   AI 批量生成/软文，返回 0..1 概率。限频 / 凭据 / 缓存统一由
   ``AIService`` 管理（避免采集热路径打爆商汤配额）。

软门禁：失败打 flag + 扣分，仍可入库（strict + min_score 阈值拦截兜底）。
"""
from __future__ import annotations

from typing import ClassVar, Literal

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext

# 中文营销/低信息密度信号词（命中标题或摘要即触发）
_TITLE_SPAM_MARKERS = (
    "震惊", "速看", "必看", "全攻略", "重磅揭秘", "惊了", "曝光", "别错过",
    "震惊！", "万万没想到", "赶紧收藏", "赶紧看", "手慢无", "爆款",
    "免费获取", "点击领取", "限时", "秒杀", "就现在", "最后一天",
)

# 极短标题/摘要阈值（启发式判定"低努力"）
_TITLE_MIN = 4      # 标题 < 4 字符
_SUMMARY_MIN = 20   # 摘要 < 20 字符


class AIQualityGate(BaseGate):
    """AI 生成内容 / 低信息密度内容门禁（软门禁）。"""

    name = "ai_quality"
    gate_type: ClassVar[Literal["hard", "soft"]] = "soft"

    # 各信号扣分
    EMPTY_TITLE_DED = 25
    EMPTY_SUMMARY_DED = 20
    SPAM_TITLE_DED = 15
    KEYWORD_DENSE_DED = 20
    LOW_EFFORT_DED = 20

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            title = (item.title or "").strip()
            summary = (item.summary or "").strip()
            flags: list[str] = []
            total_ded = 0

            # ── 1. 空标题 / 空摘要 ──
            if not title:
                flags.append("empty_title")
                total_ded += self.EMPTY_TITLE_DED
            if not summary:
                flags.append("empty_summary")
                total_ded += self.EMPTY_SUMMARY_DED

            # ── 2. 标题营销/低质词 ──
            if title and any(m in title for m in _TITLE_SPAM_MARKERS):
                flags.append("title_spam_words")
                total_ded += self.SPAM_TITLE_DED

            # ── 3. 低努力信号（标题 & 摘要都过短 → 疑似 AI 敷衍）──
            if title and summary and len(title) < _TITLE_MIN and len(summary) < _SUMMARY_MIN:
                flags.append("heuristic_aigc_low_effort")
                total_ded += self.LOW_EFFORT_DED

            # ── 4. LLM 增强（委托集中式 AIService，限频+凭据统一管理）──
            llm_score = self._llm_detect(title, summary, context)
            if llm_score is not None and llm_score >= 0.8:
                flags.append("llm_ai_generated")
                total_ded += 30

            passed = not flags
            return GateResult(
                gate_name=self.name,
                passed=passed,
                score_deduction=total_ded,
                flags=flags,
                reason=f"ai_quality: {flags or 'pass'}" if flags else None,
            )
        except Exception as e:
            return self._wrap_exception(item, e)

    def _llm_detect(
        self, title: str, summary: str, context: GateContext,
    ) -> float | None:
        """LLM 增强检测：委托 AIService.gate_detect()。

        - 仅当 AIService 可用（env 有商汤 key，或本地 ollama）才调用。
        - 超限/失败返回 None（fail-open，不误伤正常资讯）。
        """
        from backend.services.ai_service import ai_service

        if not ai_service.available():
            return None
        return ai_service.gate_detect(title, summary)


__all__ = ["AIQualityGate"]