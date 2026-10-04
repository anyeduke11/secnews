"""T4 trigger — advance ``kl:structure`` items to ``kl:publish``.

Phase 12 — fourth hop in the KL state machine.

What T4 does
------------
1. Find ``knowledge_items`` whose ``lifecycle`` is ``kl:structure``
   (ordered by ``ingested_at`` ASC, up to :data:`BATCH_SIZE`).
2. Score gate (P1-2b 真门): query the latest ``ai_scores.score``; must
   be ≥ :data:`MIN_SCORE` (8.0).  Items with no score row count as 0.0
   (诚实未评分) and are skipped — 发布必须有真实 LLM 评分, 无评分不放行
   (P0-6 精神: 系统不替模型宣称成功)。无分条目在候选队列中殿后,
   不阻塞有分条目的发布窗口 (防 kl:structure 饿死)。
3. Stability window: ``updated_at`` must be at least
   :data:`STABLE_WINDOW_HOURS` (24) in the past — prevents publishing
   content that was just structured.
4. .md write: call ``knowledge_sync.write_item_to_md()`` to persist
   the item as ``llm-wiki-2.0/items/{id}.md`` (wiki 单根, DEV-0191 起).
5. Update ``lifecycle = 'kl:publish'`` and bump ``updated_at``.

Failure handling
----------------
Any exception during per-item work is funnelled through the
:class:`RetryPolicy` injected at construction time, which writes a
``kl_dead_letters`` row after 3 attempts and increments the
``t4_dead_letter`` counter.

Metrics
-------
Emits the following counter names on the shared :data:`kl_metrics`
singleton:

- ``t4_triggered`` (once per :meth:`run_once`)
- ``t4_succeeded`` (per item advanced)
- ``t4_failed`` (per item that raised)
- ``t4_dead_letter`` (via RetryPolicy on 3rd failure)

And one histogram sample:

- ``t4_latency_ms`` (total wall time of :meth:`run_once`)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection, knowledge_items_table
from backend.services.kl_state_machine import (
    LIFECYCLE_PUBLISH,
    LIFECYCLE_STRUCTURE,
    can_transition,
)
from backend.services.retry_policy import RetryPolicy
from backend.services.triggers.events import log_stage_transition

logger = logging.getLogger("hotspot.trigger.t4")

# Public tunables
BATCH_SIZE = 50
TRIGGER_NAME = "t4"
FROM_STAGE = LIFECYCLE_STRUCTURE
TO_STAGE = LIFECYCLE_PUBLISH
STABLE_WINDOW_HOURS = 24
MIN_SCORE = 8.0
# P1-2b 真门 (DEV-0269): 无评分行 = 0.0 (诚实未评分) < MIN_SCORE → 跳过。
# 历史: P1-2 前无 DEFAULT_SCORE(5.0) 恒跳过 → LLM 未配置时 kl:publish 死锁;
# 修复期引入 SCORE_FALLBACK (无行=通过) 作临时逃生口, 与 P0-6 "诚实 0.0"
# 双语义并存 (DEV_LOG parked)。DEV-0268 评分链复活 (ai_scores>0) 达成真门
# 前置后, fallback 双语义按 parked 裁决统一移除 — 发布必须有真实 LLM 评分,
# 系统不替模型宣称成功。


class T4Trigger:
    """Advance ``kl:structure`` items to ``kl:publish`` with score + stability gates.

    Parameters
    ----------
    metrics:
        Counter / gauge / histogram store.  Defaults to the shared
        :data:`backend.metrics.kl_metrics.kl_metrics` singleton.
    retry_policy:
        Business-layer retry + dead-letter writer.  Defaults to a
        :class:`RetryPolicy` that targets the
        :class:`KLDeadLetterRepository` singleton.
    """

    def __init__(
        self,
        metrics: Any = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.metrics = metrics if metrics is not None else kl_metrics
        self.retry = retry_policy or RetryPolicy(metrics=self.metrics)

    # ── Public entry point ────────────────────────────────────────

    def run_once(self) -> dict[str, int]:
        """Run one T4 cycle. Returns a stats dict.

        Returns
        -------
        dict
            Mapping with keys ``candidates``, ``advanced``,
            ``skipped_low_score``, ``skipped_unstable``, ``failed``.
        """
        t0 = time.monotonic()
        self.metrics.inc("t4_triggered")

        candidates = self._fetch_candidates()

        advanced = 0
        skipped_low_score = 0
        skipped_unstable = 0
        failed = 0

        for item in candidates:
            item_id = item["id"]
            try:
                score = self._get_latest_score(item_id)
                if score < MIN_SCORE:
                    skipped_low_score += 1
                    continue

                if not self._is_stable(item):
                    skipped_unstable += 1
                    continue

                # Validate transition; raises on stale / illegal data.
                can_transition(item["lifecycle"], LIFECYCLE_PUBLISH)
                # 治理 T4: md 真源必须落终态 — write 先于 DB update, item 行
                # 携带的是 kl:structure, 不修正则 md frontmatter 滞后一拍。
                item["lifecycle"] = LIFECYCLE_PUBLISH
                self._write_to_md(item)
                self._update_lifecycle(item_id, LIFECYCLE_PUBLISH)
                advanced += 1
                self.metrics.inc("t4_succeeded")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.metrics.inc("t4_failed")
                self.retry.handle_failure(TRIGGER_NAME, item_id, exc)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.metrics.observe("t4_latency_ms", elapsed_ms)

        report = {
            "candidates": len(candidates),
            "advanced": advanced,
            "skipped_low_score": skipped_low_score,
            "skipped_unstable": skipped_unstable,
            "failed": failed,
        }
        logger.info(f"T4 cycle: {report} elapsed_ms={elapsed_ms:.1f}")
        return report

    # ── Read helpers ──────────────────────────────────────────────

    def _fetch_candidates(self) -> list[dict[str, Any]]:
        """Return ``kl:structure`` items, scored ones first.

        P1-2: 原 SELECT 含 ``content`` 列 — knowledge_items 无此列
        (正文在 .md 文件), 每轮必抛 OperationalError → kl:publish 恒 0。
        修复为仅查存在的列。

        P1-2b 真门: ORDER BY 有分行优先 (EXISTS ai_scores DESC), 无分殿后 —
        无分条目真门下恒 skip 且不入死信, 若按裸 ingested_at ASC 排队,
        老无分条目最终占满 BATCH_SIZE 窗口 → 有分条目饿死 (生产滞留池
        271 条中 143 无分的实测隐患)。殿后保序 (各有分/无分段内仍按
        ingested_at ASC), 无分积压经由 candidates/skipped_low_score 可观测。
        """
        sql = (
            "SELECT id, title, lifecycle, ingested_at, updated_at "
            f"FROM {knowledge_items_table()} k "
            "WHERE k.lifecycle = ? "
            "ORDER BY (EXISTS ("
            "  SELECT 1 FROM ai_scores s WHERE s.hotspot_id = k.id"
            ")) DESC, k.ingested_at ASC "
            "LIMIT ?"
        )
        conn = get_connection()
        rows = conn.execute(sql, (LIFECYCLE_STRUCTURE, BATCH_SIZE)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _get_latest_score(item_id: str) -> float:
        """Read the most recent ``ai_scores.score`` for the item.

        P1-2b 真门: 无评分行 / score 坏值 → 0.0 (诚实未评分) < MIN_SCORE
        跳过 — 发布必须有真实 LLM 评分, 无 fallback (SCORE_FALLBACK 双语义
        已按 DEV_LOG parked 裁决随 P1-2b 移除)。
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT score FROM ai_scores "
            "WHERE hotspot_id = ? "
            "ORDER BY scored_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if row is None:
            return 0.0
        try:
            return float(row["score"])
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _is_stable(item: dict[str, Any]) -> bool:
        """Return True if the item has been stable for the full window.

        Parses ``item["updated_at"]`` as an ISO-8601 datetime and checks
        that it is at least :data:`STABLE_WINDOW_HOURS` in the past.
        """
        raw = item.get("updated_at")
        if not raw:
            return False
        try:
            updated = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            logger.warning(f"unparseable updated_at for item {item.get('id')}: {raw!r}")
            return False
        # If the datetime is naive, assume UTC.
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STABLE_WINDOW_HOURS)
        return updated < cutoff

    # ── Write helpers ─────────────────────────────────────────────

    @staticmethod
    def _write_to_md(item: dict[str, Any]) -> None:
        """Write the item to ``knowledge/items/{id}.md`` (via ai_write_back)."""
        from backend.services import ai_write_back

        ai_write_back.write_item(item, agent="trigger:t4")

    @staticmethod
    def _update_lifecycle(item_id: str, new_stage: str) -> None:
        """Write ``new_stage`` into ``knowledge_items.lifecycle``."""
        conn = get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            f"UPDATE {knowledge_items_table()} "
            "SET lifecycle = ?, updated_at = ? "
            "WHERE id = ?",
            (new_stage, now_iso, item_id),
        )
        # 治理 T4 review fix: 复活链补写 kl_transition (与 kl_queue drain 同语义,
        # payload.stage=到达阶段) — 否则吞吐/停摆判定对生产链恒 0。
        log_stage_transition(TRIGGER_NAME, item_id, new_stage)


__all__ = [
    "BATCH_SIZE",
    "FROM_STAGE",
    "MIN_SCORE",
    "STABLE_WINDOW_HOURS",
    "TO_STAGE",
    "TRIGGER_NAME",
    "T4Trigger",
]