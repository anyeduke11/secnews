"""KL trigger retry + dead-letter policy.

Phase 10 — backs the T1/T2 triggers (and reserves the pattern for T3–T5
in Phase 12). Provides two layers:

1. :func:`with_retry` — pure-Python decorator that retries a synchronous
   callable with exponential backoff. Last failure is re-raised so the
   caller can decide what to do.
2. :class:`RetryPolicy` — business layer that combines ``with_retry``
   semantics with persistent dead-letter bookkeeping. After ``max_attempts``
   (default 3) failures for a given (trigger, item), the entry is moved
   to the ``kl_dead_letters`` table for manual review.

Why two layers
--------------
- :func:`with_retry` is sufficient for transient I/O (network blips,
  short lock contention). It keeps the failure visible to the caller.
- :class:`RetryPolicy` is the long-term record — once a dead letter is
  written, the trigger should NOT keep retrying the same item forever.
  The ``kl_dead_letter_retry_job`` (scheduler job 33) is responsible
  for periodic re-attempts of long-stale dead letters.
"""
from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository

logger = logging.getLogger("hotspot.retry")

# Default backoff schedule (seconds). 3 attempts: 1s, 5s, 30s.
DEFAULT_BACKOFF: Tuple[int, ...] = (1, 5, 30)
DEFAULT_MAX_ATTEMPTS: int = 3


# ---------------------------------------------------------------------------
# Function-level retry decorator
# ---------------------------------------------------------------------------

@dataclass
class RetryResult:
    """Outcome of a :func:`with_retry`-wrapped call."""
    success: bool
    value: Any = None
    error: Optional[BaseException] = None
    attempts: int = 0


def with_retry(
    fn: Optional[Callable[..., Any]] = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff: Tuple[int, ...] = DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call ``fn`` with up to ``max_attempts`` retries and exponential backoff.

    The function is invoked synchronously. If the last attempt fails,
    the underlying exception is re-raised. Tests can pass a custom
    ``sleep`` to avoid real waits.

    Supports both call styles:

    .. code-block:: python

        # As a function call:
        wrapped = with_retry(my_fn, max_attempts=3)
        wrapped(...)

        # As a decorator with defaults:
        @with_retry
        def my_fn(): ...

        # As a decorator with kwargs:
        @with_retry(max_attempts=2, backoff=(0, 0), sleep=lambda _: None)
        def my_fn(): ...
    """
    def _decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return target(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt >= max_attempts:
                        logger.error(
                            f"with_retry: {target.__name__} exhausted after "
                            f"{attempt} attempts: {exc}"
                        )
                        raise
                    wait_s = backoff[min(attempt - 1, len(backoff) - 1)]
                    logger.warning(
                        f"with_retry: {target.__name__} attempt "
                        f"{attempt}/{max_attempts} failed ({exc!r}); "
                        f"retrying in {wait_s}s"
                    )
                    sleep(wait_s)
            # Defensive — loop above always returns or raises.
            raise last_exc  # pragma: no cover
        return wrapper

    if fn is None:
        # Called with kwargs only: @with_retry(max_attempts=2, ...)
        return _decorate
    return _decorate(fn)


# ---------------------------------------------------------------------------
# Business retry policy with persistent dead letter
# ---------------------------------------------------------------------------

class RetryPolicy:
    """Tracks per-(trigger, item) failure count and writes dead letters.

    Usage
    -----
    .. code-block:: python

        policy = RetryPolicy()
        try:
            do_work(item)
        except Exception as e:
            policy.handle_failure("t1", item["id"], e)

    Semantics
    ---------
    - First / second failure: ``attempts`` is incremented on the active
      row. The item is NOT considered dead yet.
    - Third (and later) failure: a new active row is written (any prior
      active row is resolved). Metrics counter
      ``<trigger>_dead_letter`` is incremented.
    """

    def __init__(
        self,
        dead_letter_repo: Optional[KLDeadLetterRepository] = None,
        metrics: Any = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        self.dlq = dead_letter_repo or KLDeadLetterRepository()
        self.metrics = metrics  # Optional[KLMetrics]
        self.max_attempts = max_attempts

    def handle_failure(
        self,
        trigger_name: str,
        item_id: str,
        error: BaseException,
        payload: Optional[dict] = None,
    ) -> int:
        """Record a failure. Returns the new attempts count.

        On the ``max_attempts``-th failure (default 3) the row is written
        to the dead letter queue.
        """
        existing = self.dlq.get_active(trigger_name, item_id)
        attempts = (existing.attempts if existing else 0) + 1
        error_msg = f"{type(error).__name__}: {error}"[:500]
        if attempts >= self.max_attempts:
            self.dlq.add(
                trigger_name=trigger_name,
                item_id=item_id,
                error_msg=error_msg,
                attempts=attempts,
                payload=payload,
            )
            if self.metrics is not None:
                try:
                    self.metrics.inc(f"{trigger_name}_dead_letter")
                except Exception:  # pragma: no cover - metrics is optional
                    pass
            logger.error(
                f"dead letter: trigger={trigger_name} item={item_id} "
                f"attempts={attempts} err={error_msg}"
            )
        else:
            self.dlq.update_attempts(
                trigger_name=trigger_name,
                item_id=item_id,
                error_msg=error_msg,
                attempts=attempts,
            )
            logger.warning(
                f"retry scheduled: trigger={trigger_name} item={item_id} "
                f"attempts={attempts} err={error_msg}"
            )
        return attempts


__all__ = [
    "DEFAULT_BACKOFF",
    "DEFAULT_MAX_ATTEMPTS",
    "RetryResult",
    "with_retry",
    "RetryPolicy",
]
