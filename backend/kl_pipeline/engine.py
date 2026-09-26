"""KLPipeline — five-stage knowledge lifecycle engine.

Stages: kl:raw → kl:refine → kl:link → kl:structure → kl:publish

Each stage is a callable that takes (item_id, wiki_fs, llm_client) and
returns a dict of stage results. The engine handles queue management,
error tracking, and stage advancement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from backend.kl_pipeline.queue import STAGES, KLQueue
from backend.logging_config import logger
from backend.wiki_fs.contract import get_lifecycle

# Delay before first refine (let the raw item settle).
_KICKOFF_DELAY_SECONDS = 45


def _stage_index(stage: str) -> int:
    """Return the index of a stage in the STAGES tuple (-1 if not found)."""
    try:
        return STAGES.index(stage)
    except ValueError:
        return -1


def _next_stage(stage: str) -> str | None:
    """Return the next stage name, or None if already at terminal."""
    idx = _stage_index(stage)
    if idx < 0 or idx >= len(STAGES) - 1:
        return None
    return STAGES[idx + 1]


class KLPipeline:
    """Orchestrates knowledge item lifecycle through five stages."""

    def __init__(
        self,
        wiki_fs: Any,
        db_session: Any = None,
        llm_client: Any = None,
    ) -> None:
        self.wiki_fs = wiki_fs
        self.llm_client = llm_client
        self.queue = KLQueue(db_session)
        self._stages = self._load_stages()

    @staticmethod
    def _load_stages() -> dict[str, Any]:
        """Lazy-import stage handlers to avoid circular imports."""
        from backend.kl_pipeline.stages.link import run_link
        from backend.kl_pipeline.stages.publish import run_publish
        from backend.kl_pipeline.stages.refine import run_refine
        from backend.kl_pipeline.stages.structure import run_structure
        return {
            "kl:refine": run_refine,
            "kl:link": run_link,
            "kl:structure": run_structure,
            "kl:publish": run_publish,
        }

    def kickoff(self, item_id: str) -> None:
        """Enqueue a new item for kl:refine with a short delay.

        入口存在性校验 (ghost-item 治理 T1): wiki_events 里
        ``item not found: ghost-item`` ×138 的根因链 = 不存在的 item 反复入队
        → drain 报 ValueError → 退避重试每轮再写一条 kl_error 事件。对读不出的
        item 直接拒之门外, 队列只认 wiki 里真实存在的条目。
        """
        if self.wiki_fs is not None and self.wiki_fs.read_item(item_id) is None:
            logger.warning(
                "kl_pipeline kickoff skipped (item not found)",
                extra={"item_id": item_id},
            )
            return
        next_run = datetime.now(timezone.utc) + timedelta(seconds=_KICKOFF_DELAY_SECONDS)
        added = self.queue.enqueue_unique(item_id, "kl:refine", next_run)
        if added:
            logger.info("kl_pipeline kickoff", extra={"item_id": item_id})

    def drain_due(self, limit: int = 20) -> dict:
        """Consume due tasks, return {"done": int, "failed": int}."""
        tasks = self.queue.due(limit)
        done = 0
        failed = 0
        for task in tasks:
            qid = task["id"]
            stage = task["stage"]
            item_id = task["item_id"]
            self.queue.mark_run(qid)
            try:
                handler = self._stages.get(stage)
                if handler is None:
                    raise ValueError(f"no handler for stage {stage}")
                handler(item_id, self.wiki_fs, self.llm_client)
                # Advance to next stage or complete.
                nxt = _next_stage(stage)
                if nxt is not None:
                    next_run = datetime.now(timezone.utc) + timedelta(seconds=10)
                    self.queue.mark_done(qid)
                    self.queue.enqueue_unique(item_id, nxt, next_run)
                else:
                    self.queue.mark_done(qid)
                self._log_event("kl_transition", item_id, qid,
                                {"stage": stage, "next": nxt})
                done += 1
            except Exception as exc:
                logger.error(
                    "kl_pipeline stage failed",
                    extra={"item_id": item_id, "stage": stage, "error": str(exc)},
                )
                outcome = self.queue.mark_error(qid, str(exc)[:500])
                if outcome == "terminal":
                    self._to_dead_letter(item_id, stage, exc)
                self._log_event("kl_error", item_id, qid,
                                {"stage": stage, "error": str(exc)[:200]})
                failed += 1
        return {"done": done, "failed": failed}

    # 死信归属触发器 (kl_dead_letters.trigger_name CHECK 约束只认 t1-t5);
    # 阶段本身留在 payload 里精确归因。kl_dead_letter_retry_job / trigger_health
    # 均按 trigger_name 归组, 映射到管线触发器与其统计口径一致。
    _STAGE_TO_TRIGGER: ClassVar[dict[str, str]] = {
        "kl:refine": "t1",
        "kl:link": "t2",
        "kl:structure": "t3",
        "kl:publish": "t4",
    }

    @classmethod
    def _to_dead_letter(cls, item_id: str, stage: str, exc: BaseException) -> None:
        """重试耗尽 → 落死信, 给人工处理留出口。失败不阻塞主循环。

        历史 bug: trigger_name 曾写 ``kl_pipeline:<stage>``, 被 044 迁移的
        CHECK 约束拒收 → 死信从未真正落库 (只留下一行 warning)。
        """
        try:
            from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository

            KLDeadLetterRepository().add(
                trigger_name=cls._STAGE_TO_TRIGGER.get(stage, "t1"),
                item_id=item_id,
                error_msg=f"{type(exc).__name__}: {exc}"[:500],
                attempts=0,
                payload={"stage": stage},
            )
        except Exception as dlq_exc:  # pragma: no cover - defensive
            logger.warning(
                f"kl_pipeline dead letter write failed for {item_id}: {dlq_exc}"
            )

    @staticmethod
    def _log_event(kind: str, item_id: str, queue_id: int, payload: dict) -> None:
        """wiki_events 留痕 (DB=运营/事件管理层)。失败不阻塞管线。"""
        try:
            from backend.repository.wiki_event_repo import wiki_event_repo
            wiki_event_repo.log(
                kind=kind,
                wiki_path=f"items/{item_id}.md",
                db_table="kl_queue",
                db_row_id=str(queue_id),
                agent="kl_pipeline",
                payload=payload,
            )
        except Exception as exc:
            logger.warning(f"kl_pipeline wiki_events log failed: {exc}")

    def advance(self, item_id: str) -> str:
        """Manually advance an item to its next stage. Returns new stage name."""
        doc = self.wiki_fs.read_item(item_id)
        if doc is None:
            raise ValueError(f"item not found: {item_id}")
        current = get_lifecycle(doc["fm"])
        nxt = _next_stage(current)
        if nxt is None:
            return current  # already terminal
        next_run = datetime.now(timezone.utc)
        self.queue.enqueue_unique(item_id, nxt, next_run)
        return nxt

    def sweep(self) -> int:
        """Re-enqueue items stuck in non-terminal stages. Returns enqueue count."""
        if self.wiki_fs is None:
            return 0
        count = 0
        for item_id in self.wiki_fs.list_ids():
            doc = self.wiki_fs.read_item(item_id)
            if doc is None:
                continue
            stage = get_lifecycle(doc["fm"])
            if stage == "kl:publish":
                continue
            nxt = _next_stage(stage)
            if nxt is None:
                continue
            next_run = datetime.now(timezone.utc)
            added = self.queue.enqueue_unique(item_id, nxt, next_run)
            if added:
                count += 1
        return count

    def retry_errors(self, wiki_id: str | None = None) -> int:
        """Reset error tasks to pending. Returns count reset."""
        return self.queue.reset_errors(wiki_id)
