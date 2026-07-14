"""QualityGatePipeline — 顺序跑 9 个同步门禁 + 累加扣分。

URL Content gate 不在此处同步跑（由 scheduler job 抽样异步跑）。

模式
----
- ``loose``（默认）：失败打 flag + 扣分，仍入库
- ``strict``：失败打 flag + 扣分；``final_score < min_score`` 时
  ``accepted=False``，调用方应拒绝入库
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from backend.domain.collection import GateResult, PipelineResult
from backend.domain.models import HotspotItem
from backend.exceptions import QualityGateFailed
from backend.logging_config import logger
from backend.quality.base import BaseGate, GateContext
from backend.quality.author_verification_gate import AuthorVerificationGate
from backend.quality.bid_recency_gate import BidRecencyGate
from backend.quality.category_match_gate import CategoryMatchGate
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.content_quality_gate import ContentQualityGate
from backend.quality.duplicate_gate import DuplicateGate
from backend.quality.final_url_gate import FinalUrlGate
from backend.quality.noise_content_gate import NoiseContentGate
from backend.quality.recency_gate import RecencyGate  # Phase 47
from backend.quality.schema_gate import SchemaGate
from backend.quality.scorer import compute_final_score, is_acceptable, merge_flags
from backend.quality.source_reputation_gate import SourceReputationGate
from backend.quality.title_summary_gate import TitleSummaryGate
from backend.quality.url_validity_gate import URLValidityGate
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.quality_repo import QualityLogRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_context(
    config: QualityConfig,
    *,
    existing_urls: Optional[Iterable[str]] = None,
    existing_titles: Optional[Iterable[str]] = None,
    source_reputation: Optional[dict] = None,
    url_title_pairs: Optional[list[dict]] = None,
) -> GateContext:
    """从 ``QualityConfig`` + 必要预查询构建 :class:`GateContext`.

    Parameters
    ----------
    url_title_pairs:
        Phase 8 Addendum：本批次所有 item 的 ``[{"url", "title", "source"}]``
        三元组，由调用方在跑 quality pipeline 前注入。DuplicateGate 用来
        检测"同 URL 不同 title"歧义并按 reputation 选 winner。注入到
        ``context.__dict__`` 绕过 Pydantic 严格模式（不修改 schema）。
    """
    from backend.repository.quality_repo import SourceReputationRepository

    rep = source_reputation
    if rep is None:
        repo = SourceReputationRepository()
        try:
            from backend.domain.enums import TimeRange
            hrepo = HotspotRepository()
            # 取最近 7d 出现的 source
            items, _ = hrepo.query(category=None, time_range=TimeRange.D7, limit=200)
            seen_sources = {it.source for it in items}
        except Exception:
            seen_sources = set()
        rep = repo.get_many(list(seen_sources)) if seen_sources else {}

    ctx = GateContext(
        mode=("strict" if config.mode == QualityMode.STRICT else "loose"),
        category_keywords=config.category_keywords,
        source_reputation=rep or {},
        existing_urls=set(existing_urls or []),
        existing_titles=list(existing_titles or []),
    )
    # Phase 8: 注入 url_title_pairs 到 __dict__ 绕过 Pydantic v2 严格 setattr
    # 不修改 GateContext schema，保持向后兼容
    ctx.__dict__["url_title_pairs"] = list(url_title_pairs or [])
    return ctx


class QualityGatePipeline:
    """编排 9 个同步门禁的流水线。"""

    DEFAULT_GATES: tuple[type[BaseGate], ...] = (
        SchemaGate,
        RecencyGate,  # Phase 47 新增 - 资讯/标讯时效硬门禁 (本周一 00:00+08:00)
        ContentQualityGate,
        NoiseContentGate,  # fix-bug-github-category-dedup Task 3 - 备案/版权/活动等噪音
        CategoryMatchGate,
        TitleSummaryGate,
        URLValidityGate,
        SourceReputationGate,
        AuthorVerificationGate,
        FinalUrlGate,  # Phase 9.2 新增 - 下钻 tag/landing 页到真实文章 URL
        DuplicateGate,
        BidRecencyGate,  # Phase 20 新增 - 标讯时效性门禁 (标题年份段)
    )

    def __init__(
        self,
        config: QualityConfig,
        *,
        log_repo: Optional[QualityLogRepository] = None,
        gates: Optional[list[BaseGate]] = None,
    ) -> None:
        self.config = config
        self.mode = config.mode
        self.log_repo = log_repo or QualityLogRepository()
        self.gates: list[BaseGate] = (
            gates if gates is not None else [g() for g in self.DEFAULT_GATES]
        )

    # ------------------------------------------------------------------
    def run_all(
        self,
        item: HotspotItem,
        context: Optional[GateContext] = None,
    ) -> PipelineResult:
        """顺序跑全部 9 个同步门禁。"""
        if context is None:
            context = build_context(self.config)
        mode_str = "strict" if self.mode == QualityMode.STRICT else "loose"
        deductions: list[int] = []
        all_flags: list[str] = []
        gate_results: list[GateResult] = []

        for gate in self.gates:
            try:
                result = gate.check(item, context)
            except Exception as e:
                # 门禁抛出 = 隔离到 _wrap_exception
                logger.error(
                    f"gate {gate.name} crashed",
                    extra={"trace_id": "", "item_id": item.id, "error": str(e)},
                )
                result = GateResult(
                    gate_name=gate.name,
                    passed=True,
                    error_msg=f"{type(e).__name__}: {str(e)[:200]}",
                )

            gate_results.append(result)
            if not result.passed:
                deductions.append(result.score_deduction)
            all_flags = merge_flags(all_flags, result.flags)

            # 写 quality_check_logs（失败不阻塞）
            self.log_repo.write_log(
                item.id, result, mode=mode_str, checked_at=_now().isoformat()
            )

        final_score = compute_final_score(100, deductions)
        accepted = is_acceptable(final_score, self.config.min_score)
        reason: Optional[str] = None
        if self.mode == QualityMode.STRICT and not accepted:
            reason = (
                f"strict mode: score {final_score} < {self.config.min_score}"
            )

        result = PipelineResult(
            item_id=item.id,
            gate_results=gate_results,
            final_score=final_score,
            final_flags=all_flags,
            accepted=accepted,
            mode=mode_str,
            reason=reason,
        )

        # 严格模式 + 拒绝 → 抛异常
        if self.mode == QualityMode.STRICT and not accepted:
            logger.warning(
                "strict mode rejection",
                extra={
                    "trace_id": "",
                    "item_id": item.id,
                    "score": final_score,
                    "flags": all_flags,
                },
            )
            raise QualityGateFailed(
                item_id=item.id, score=final_score, flags=all_flags
            )

        return result


__all__ = ["QualityGatePipeline", "build_context"]
