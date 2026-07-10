"""Duplicate gate — URL hash 命中 + 标题 jaccard 相似度 ≥ 0.8。

- URL 已存在 → flag ``url_duplicate``，扣 50 分
- 标题相似度 ≥ 80% (jaccard) → flag ``similar_title_duplicate``，扣 30 分

Phase 8 Addendum (需求 8.3)：同 URL 不同 title 歧义识别
- ``context.url_title_pairs`` 中如果当前 URL 出现 ≥ 2 次，且至少
  有 1 个其他 source 的 title 不同 → 按优先级选 winner item。
- 优先级（Phase 9 增强 + Phase 45 修复）:
    1. ``url_check_status=verified`` 最优先 (详情页 ``<title>`` 验过)
    2. ``is_fallback=False`` 优先
    3. ``source_reputation[source].score`` 高优先
    4. ``fetched_at`` 较新优先
    5. ``id`` 字典序(兜底)
- 胜出 item：``passed=True``，flag ``duplicate_link_real_title``
- 其他 item：``passed=False``，扣 60，flags 加 ``title_replaced``

Phase 45 修复: **移除 title_len 排序 key** — 长 title 不等于真 title,
曾导致同 URL 重复入库时错把 list 页抓到的长 title 摘要当 winner。
"""
from __future__ import annotations

from datetime import datetime

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.title_summary_gate import _tokenize


# url_check_status 优先级: verified=0 (winner, key 最小), pending=2 (loser)
# 用 min 选 winner (Python sorted 升序 → key 最小者胜)
_URL_CHECK_RANK = {"verified": 0, "mismatch": 1, "skipped": 1, "pending": 2, None: 2}


def _winner_sort_key(
    pair: dict,
    source_reputation: dict,
) -> tuple:
    """同 URL 多条候选时，winner 选择排序 key (key 最小者胜)。

    Phase 45 修复: 不用 title_len (错指标); 改用 url_check_status verified 优先。
    Phase 45 修复: 用 min 选 winner, 所有 "越大越好" 字段取反 (高 rep → -rep 小)。
    """
    src = pair.get("source", "") or ""
    is_fallback = bool(pair.get("is_fallback", False))
    rep_dict = (source_reputation or {}).get(src, {}) or {}
    try:
        rep_score = float(rep_dict.get("score", 0))
    except (TypeError, ValueError):
        rep_score = 0.0
    # fetched_at 可能是 ISO 字符串
    fetched_at = pair.get("fetched_at")
    if isinstance(fetched_at, datetime):
        ts = int(fetched_at.timestamp())
    else:
        ts = 0
    url_check_rank = _URL_CHECK_RANK.get(pair.get("url_check_status"), 2)
    return (
        url_check_rank,            # 0=verified(winner), 2=pending(loser)
        0 if is_fallback else 1,   # 1=not_fallback(winner, key 小)
        -rep_score,                 # 高 reputation → -rep 小 → 排前
        -ts,                        # 新 ts → -ts 小 → 排前
        pair.get("id", "") or "",  # id 字典序小者胜
    )


def _pick_winner(
    same_url_items: list[dict],
    source_reputation: dict,
) -> dict:
    """从同 URL 的多条候选中选 1 个 winner。

    Phase 9 修复：之前返回 source string（导致同 source 时全部判 winner）；
    改为返回完整 pair dict（_pick_winner_pair_id 之后取 id）。
    """
    if not same_url_items:
        return {}
    # Phase 45: 用 min 选 winner (key 最小者胜), id 字典序小者胜.
    return min(same_url_items, key=lambda p: _winner_sort_key(p, source_reputation))


def _winner_pair_id(winner_pair: dict) -> str:
    return str(winner_pair.get("id", "") or "")


class DuplicateGate(BaseGate):
    """跨源去重门禁（同步）。"""

    name = "duplicate"

    def __init__(self, jaccard_threshold: float = 0.80):
        self.jaccard_threshold = jaccard_threshold

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            url = str(item.url)

            # ------------------------------------------------------------------
            # Phase 8 Addendum + Phase 9 修复: 同 URL 不同 title 歧义识别
            # ------------------------------------------------------------------
            url_title_pairs = getattr(context, "url_title_pairs", None) or []
            same_url_items = [
                p for p in url_title_pairs if p.get("url") == url
            ]
            if len(same_url_items) >= 2:
                titles = {p.get("title", "") for p in same_url_items}
                if len(titles) >= 2:
                    # 存在 title 歧义 → 按多级优先级选 winner item
                    rep_map = context.source_reputation or {}
                    winner_pair = _pick_winner(same_url_items, rep_map)
                    winner_id = _winner_pair_id(winner_pair)
                    if str(item.id) == winner_id:
                        return GateResult(
                            gate_name=self.name,
                            passed=True,
                            score_deduction=0,
                            flags=["duplicate_link_real_title"],
                            reason=(
                                f"same URL appears in {len(same_url_items)} items, "
                                f"this is the winner (highest quality/title/source)"
                            ),
                        )
                    return GateResult(
                        gate_name=self.name,
                        passed=False,
                        score_deduction=60,
                        flags=["duplicate_link_real_title", "title_replaced"],
                        reason=(
                            f"same URL with different title, "
                            f"winner id={winner_id}, "
                            f"this item replaced by winner"
                        ),
                    )

            # ------------------------------------------------------------------
            # 原有逻辑：URL 已存在 / 标题 jaccard 相似
            # ------------------------------------------------------------------
            if url in context.existing_urls:
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=50,
                    flags=["url_duplicate"],
                    reason=f"URL {url[:80]} already in DB",
                )

            new_tokens = _tokenize(item.title)
            if new_tokens and context.existing_titles:
                for prev in context.existing_titles:
                    prev_tokens = _tokenize(prev)
                    if not prev_tokens:
                        continue
                    intersection = new_tokens & prev_tokens
                    union = new_tokens | prev_tokens
                    jaccard = len(intersection) / max(1, len(union))
                    if jaccard >= self.jaccard_threshold:
                        return GateResult(
                            gate_name=self.name,
                            passed=False,
                            score_deduction=30,
                            flags=["similar_title_duplicate"],
                            reason=(
                                f"jaccard={jaccard:.2%} >= "
                                f"{self.jaccard_threshold:.0%} with prior title"
                            ),
                        )

            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=0,
                flags=[],
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["DuplicateGate"]
