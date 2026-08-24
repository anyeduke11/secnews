"""KLPipeline — five-stage knowledge lifecycle engine.

Stages: kl:raw → kl:refine → kl:link → kl:structure → kl:publish

Each stage is a callable that takes (item_id, wiki_fs, llm_client) and
returns a dict of stage results. The engine handles queue management,
error tracking, and stage advancement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.kl_pipeline.queue import KLQueue, STAGES
from backend.logging_config import logger

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
        from backend.kl_pipeline.stages.refine import run_refine
        from backend.kl_pipeline.stages.link import run_link
        from backend.kl_pipeline.stages.structure import run_structure
        from backend.kl_pipeline.stages.publish import run_publish
        return {
            "kl:refine": run_refine,
            "kl:link": run_link,
            "kl:structure": run_structure,
            "kl:publish": run_publish,
        }

    def kickoff(self, item_id: str) -> None:
        """Enqueue a new item for kl:refine with a short delay."""
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
                done += 1
            except Exception as exc:
                logger.error(
                    "kl_pipeline stage failed",
                    extra={"item_id": item_id, "stage": stage, "error": str(exc)},
                )
                self.queue.mark_error(qid, str(exc)[:500])
                failed += 1
        return {"done": done, "failed": failed}

    def advance(self, item_id: str) -> str:
        """Manually advance an item to its next stage. Returns new stage name."""
        doc = self.wiki_fs.read_item(item_id)
        if doc is None:
            raise ValueError(f"item not found: {item_id}")
        current = doc["fm"].get("kl_stage", "kl:raw")
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
            stage = doc["fm"].get("kl_stage", "kl:raw")
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
