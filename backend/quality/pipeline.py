"""QualityGatePipeline — 顺序跑 9 个同步门禁 + 累加扣分。

URL Content gate 不在此处同步跑（由 scheduler job 抽样异步跑）。

模式
----
- ``loose``（默认）：失败打 flag + 扣分，仍入库
- ``strict``：失败打 flag + 扣分；``final_score < min_score`` 时
  ``accepted=False``，调用方应拒绝入库
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from backend.domain.collection import GateResult, PipelineResult
from backend.domain.models import HotspotItem
from backend.exceptions import QualityGateFailed
from backend.logging_config import logger
from backend.quality.author_verification_gate import AuthorVerificationGate
from backend.quality.base import BaseGate, GateContext
from backend.quality.bid_recency_gate import BidRecencyGate
from backend.quality.category_match_gate import CategoryMatchGate
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.content_quality_gate import ContentQualityGate
from backend.quality.duplicate_gate import DuplicateGate
from backend.quality.final_url_gate import FinalUrlGate
from backend.quality.noise_content_gate import NoiseContentGate
from backend.quality.recency_gate import RecencyGate  # Phase 47
from backend.quality.schema_gate import SchemaGate
from backend.quality.ai_quality_gate import AIQualityGate  # v4.4
from backend.quality.scorer import compute_final_score, is_acceptable, merge_flags
from backend.quality.source_reputation_gate import SourceReputationGate
from backend.quality.title_summary_gate import TitleSummaryGate
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.quality_repo import QualityLogRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_context(
    config: QualityConfig,
    *,
    existing_urls: Iterable[str] | None = None,
    existing_titles: Iterable[str] | None = None,
    source_reputation: dict | None = None,
    url_title_pairs: list[dict] | None = None,
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
    # v4.4: LLM 凭据不再从 settings 注入（已移除设置页密钥保存）。
    # LLM 增强检测统一走 AIService（env 凭据 / ollama），门禁不依赖 context。
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
        AIQualityGate,     # v4.4 - AI 生成/低信息密度软文检测 (启发式 + LLM 预留)
        CategoryMatchGate,
        TitleSummaryGate,
        # URLValidityGate 已从同步 pipeline 移除 (P1): 其同步 HEAD 请求 (5s 超时)
        # 经 asyncio.to_thread 逐 item 串行执行, 50 items × 5s 可阻塞采集数分钟。
        # URL 可达性检查由异步 job run_url_content_check 承担 (quality/jobs.py,
        # url_check_concurrency 信号量并发 + 网络失败归类 url_unreachable)。
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
        log_repo: QualityLogRepository | None = None,
        gates: list[BaseGate] | None = None,
    ) -> None:
        self.config = config
        self.mode = config.mode
        self.log_repo = log_repo or QualityLogRepository()
        self.gates: list[BaseGate] = (
            gates if gates is not None else [g() for g in self.DEFAULT_GATES]
        )

    # ------------------------------------------------------------------
    def _check_gate(
        self,
        gate: BaseGate,
        item: HotspotItem,
        context: GateContext,
        mode_str: str,
    ) -> GateResult:
        """执行单个门禁, 异常 fail-closed (P2-5)。

        门禁崩溃不再转 passed=True 免检 — 改为 passed=False + gate_crashed
        flag + 扣 15 分, 让崩溃可见 (strict 模式因此拒绝, loose 模式打标),
        避免"任一 gate 代码缺陷 → 该关全放行"。
        """
        try:
            return gate.check(item, context)
        except Exception as e:
            logger.error(
                f"gate {gate.name} crashed (fail-closed)",
                extra={"trace_id": "", "item_id": item.id, "error": str(e)},
            )
            return GateResult(
                gate_name=gate.name,
                passed=False,
                flags=["gate_crashed"],
                score_deduction=15,
                reason=f"gate crashed: {type(e).__name__}: {str(e)[:200]}",
                error_msg=f"{type(e).__name__}: {str(e)[:200]}",
            )

    def run_all(
        self,
        item: HotspotItem,
        context: GateContext | None = None,
    ) -> PipelineResult:
        """顺序跑全部同步门禁。

        Hard/Soft 分层逻辑 (P2-5 语义对齐):
        1. 先跑所有 Hard gates — **仅 strict 模式失败即拒绝**; loose 模式
           打 flag + 扣分后继续 (与文档 "loose = 失败打 flag + 扣分, 仍入库"
           一致; 此前 hard 失败在 loose 模式也抛 QualityGateFailed → 与文档
           矛盾, 且被 quality_hook 丢弃)。
        2. 全部通过后跑 Soft gates, 累加扣分
        3. strict 模式: final_score < min_score → 拒绝抛异常
           loose 模式: 返回 accepted=False (调用方决定), 不抛
        """
        if context is None:
            context = build_context(self.config)
        mode_str = "strict" if self.mode == QualityMode.STRICT else "loose"
        deductions: list[int] = []
        all_flags: list[str] = []
        gate_results: list[GateResult] = []

        # 1. 先跑 Hard gates
        hard_gates = [g for g in self.gates if g.gate_type == "hard"]
        soft_gates = [g for g in self.gates if g.gate_type == "soft"]

        for gate in hard_gates:
            result = self._check_gate(gate, item, context, mode_str)
            gate_results.append(result)
            if not result.passed:
                deductions.append(result.score_deduction)
            all_flags = merge_flags(all_flags, result.flags)

            # 写 quality_check_logs（失败不阻塞）
            self.log_repo.write_log(
                item.id, result, mode=mode_str, checked_at=_now().isoformat()
            )

            # Hard gate 失败 → P2-5: 仅 strict 模式立即拒绝
            if not result.passed and self.mode == QualityMode.STRICT:
                context.rejected_by = gate.name
                final_score = compute_final_score(100, deductions)
                reason = (
                    f"hard gate '{gate.name}' rejected: "
                    f"{result.reason or 'no reason'}"
                )
                logger.warning(
                    "hard gate rejection",
                    extra={
                        "trace_id": "",
                        "item_id": item.id,
                        "gate": gate.name,
                        "reason": result.reason,
                    },
                )
                raise QualityGateFailed(
                    item_id=item.id,
                    score=final_score,
                    flags=all_flags,
                    message=reason,
                )

        # 2. 全部 Hard gates 通过 → 跑 Soft gates
        for gate in soft_gates:
            result = self._check_gate(gate, item, context, mode_str)
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
        reason: str | None = None
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
