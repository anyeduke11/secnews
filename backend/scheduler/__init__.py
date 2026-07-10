"""Scheduler layer: APScheduler wrappers for periodic collection jobs.

Phase 3 Task 5 introduces:

- :class:`backend.scheduler.scheduler.HotspotScheduler` — APScheduler
  wrapper that owns the lifecycle (``start`` / ``stop`` / ``reschedule``).
- :mod:`backend.scheduler.jobs` — the actual job functions
  (``collect_all_job`` / ``trend_rebuild_job``) that the scheduler runs.

The package is intentionally import-only: ``main.py`` (Phase 3 Task 6)
wires a real :class:`HotspotScheduler` into the FastAPI app.
"""
