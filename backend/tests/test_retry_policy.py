"""Tests for :mod:`backend.services.retry_policy` and the dead-letter repo.

Covers
------
- :func:`with_retry` — success on first try; success on retry; exhaust
  attempts raises the last error; custom sleep avoids real waits.
- :class:`RetryPolicy.handle_failure` — first/second/third failure flow:
  third failure writes a dead letter and increments metrics.
- :class:`KLDeadLetterRepository` — add / get_active / update_attempts /
  list_active_count / list_active / resolve.
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository
from backend.services.retry_policy import RetryPolicy, with_retry


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Override the conftest fixture with a Path object (not str) so
    backend.repository.db.get_connection() can call .parent.mkdir(...).
    """
    test_db = tmp_path / "test_retry_policy.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# with_retry
# ---------------------------------------------------------------------------

class TestWithRetry:
    def test_success_on_first_try(self):
        calls = []

        def fn(x):
            calls.append(x)
            return x * 2

        wrapped = with_retry(fn, max_attempts=3, backoff=(0, 0, 0), sleep=lambda _: None)
        assert wrapped(5) == 10
        assert calls == [5]

    def test_success_on_third_try(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        wrapped = with_retry(fn, max_attempts=3, backoff=(0, 0, 0), sleep=lambda _: None)
        assert wrapped() == "ok"
        assert calls["n"] == 3

    def test_exhaust_raises_last_error(self):
        def fn():
            raise ValueError("always fails")

        wrapped = with_retry(fn, max_attempts=3, backoff=(0, 0, 0), sleep=lambda _: None)
        with pytest.raises(ValueError, match="always fails"):
            wrapped()

    def test_custom_backoff(self):
        sleeps = []
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("again")
            return "ok"

        wrapped = with_retry(
            fn, max_attempts=3, backoff=(7, 11, 13),
            sleep=lambda s: sleeps.append(s),
        )
        wrapped()
        # 1st failure → wait 7s before 2nd attempt
        assert sleeps == [7]
        assert calls["n"] == 2

    def test_preserves_function_metadata(self):
        @with_retry(max_attempts=2, backoff=(0, 0), sleep=lambda _: None)
        def my_special_fn():
            return 42

        assert my_special_fn.__name__ == "my_special_fn"
        assert my_special_fn() == 42


# ---------------------------------------------------------------------------
# RetryPolicy + KLDeadLetterRepository (uses temp_db)
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    def test_first_failure_increments_attempts_no_dlq(self, temp_db):
        repo = KLDeadLetterRepository()
        policy = RetryPolicy(dead_letter_repo=repo, max_attempts=3)

        n = policy.handle_failure("t1", "item-1", RuntimeError("boom"))
        assert n == 1

        active = repo.get_active("t1", "item-1")
        assert active is not None
        assert active.attempts == 1
        assert "RuntimeError" in active.error_msg
        assert active.resolved is False
        assert repo.list_active_count("t1") == 1

    def test_second_failure_still_no_dlq(self, temp_db):
        repo = KLDeadLetterRepository()
        policy = RetryPolicy(dead_letter_repo=repo, max_attempts=3)

        policy.handle_failure("t1", "item-2", RuntimeError("first"))
        policy.handle_failure("t1", "item-2", RuntimeError("second"))

        active = repo.get_active("t1", "item-2")
        assert active is not None
        assert active.attempts == 2
        assert repo.list_active_count("t1") == 1  # not duplicated

    def test_third_failure_writes_dead_letter(self, temp_db):
        repo = KLDeadLetterRepository()
        # Use a stub metrics object that records increments
        class StubMetrics:
            def __init__(self):
                self.counters = {}
            def inc(self, name, n=1):
                self.counters[name] = self.counters.get(name, 0) + n

        metrics = StubMetrics()
        policy = RetryPolicy(
            dead_letter_repo=repo, metrics=metrics, max_attempts=3
        )

        for i in range(3):
            policy.handle_failure("t2", "item-3", ValueError(f"err {i}"))

        # After 3rd failure, a new active row should exist
        active = repo.get_active("t2", "item-3")
        assert active is not None
        assert active.attempts == 3
        # Metrics counter incremented
        assert metrics.counters.get("t2_dead_letter") == 1

    def test_separate_triggers_are_isolated(self, temp_db):
        repo = KLDeadLetterRepository()
        policy = RetryPolicy(dead_letter_repo=repo, max_attempts=3)

        policy.handle_failure("t1", "item-A", RuntimeError("a"))
        policy.handle_failure("t2", "item-A", RuntimeError("b"))

        assert repo.list_active_count("t1") == 1
        assert repo.list_active_count("t2") == 1

    def test_resolve_hides_from_active_list(self, temp_db):
        repo = KLDeadLetterRepository()
        policy = RetryPolicy(dead_letter_repo=repo, max_attempts=3)

        policy.handle_failure("t1", "item-x", RuntimeError("x"))
        entry = repo.get_active("t1", "item-x")
        assert entry is not None
        repo.resolve(entry.id)

        assert repo.get_active("t1", "item-x") is None
        assert repo.list_active_count("t1") == 0

    def test_payload_stored_as_json(self, temp_db):
        repo = KLDeadLetterRepository()
        payload = {"stage": "kl:raw", "retry_count": 2}
        repo.add("t1", "item-p", "boom", attempts=3, payload=payload)
        entry = repo.get_active("t1", "item-p")
        assert entry is not None
        import json
        assert json.loads(entry.payload) == payload
