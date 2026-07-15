"""Knowledge watchdog — watches knowledge/*.md files and syncs to SQLite.

Watches:
- ``knowledge/items/``      → :func:`full_sync_items_to_db`
- ``knowledge/concepts/``   → :func:`full_sync_concepts_to_db`
- ``knowledge/learning/``   → watched for conflict detection only (no DB sync)

Conflict detection (simplified):
- If the same .md file is modified within ``_CONFLICT_WINDOW_SECONDS`` (2s) of
  its last modification, the previous version is copied to
  ``knowledge/.conflicts/`` with a metadata header before the new sync runs.
- Genuine rapid edits (e.g. Agent + user writing the same file) are recorded;
  duplicate watchdog events with identical content are ignored to avoid noise.

Debounce:
- Multiple events for the same file within ``_DEBOUNCE_SECONDS`` (1s) trigger
  a single full-sync call.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.services.knowledge_sync import (
    KNOWLEDGE_DIR,
    full_sync_concepts_to_db,
    full_sync_items_to_db,
)

log = logging.getLogger("hotspot.knowledge_watcher")

# Subdirectories of KNOWLEDGE_DIR to watch.
_WATCH_DIRS = ("items", "concepts", "learning")
# Subdirectories that have a DB full-sync function. ``learning/`` is watched
# for conflict detection only (task .md files are not mirrored to SQLite).
_SYNC_FUNCS = {
    "items": full_sync_items_to_db,
    "concepts": full_sync_concepts_to_db,
}

CONFLICTS_DIR = KNOWLEDGE_DIR / ".conflicts"
_CONFLICT_WINDOW_SECONDS = 2.0
_DEBOUNCE_SECONDS = 1.0


class _KnowledgeEventHandler(FileSystemEventHandler):
    """Handle .md changes for one watched subdirectory.

    Each instance is responsible for a single subdir (items/concepts/learning)
    so it knows which sync function (if any) to invoke after the debounce
    window elapses.
    """

    def __init__(self, subdir: str) -> None:
        self._subdir = subdir
        self._timers: dict[str, threading.Timer] = {}
        # path -> (last_event_ts, last_content_snapshot)
        self._last_mod: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    # watchdog callbacks -------------------------------------------------

    def on_modified(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._handle(event.src_path)

    def on_created(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._handle(event.src_path)

    # internal -----------------------------------------------------------

    def _handle(self, path: str) -> None:
        if not path.endswith(".md"):
            return
        now = time.time()
        try:
            current_content = Path(path).read_text(encoding="utf-8")
        except Exception:
            # File may have been deleted between event and read; skip.
            return
        with self._lock:
            self._detect_conflict(path, now, current_content)
            self._last_mod[path] = (now, current_content)
            self._schedule_sync(path)

    def _detect_conflict(
        self, path: str, now: float, current_content: str
    ) -> None:
        prev = self._last_mod.get(path)
        if prev is None:
            return
        old_ts, old_content = prev
        if (now - old_ts) >= _CONFLICT_WINDOW_SECONDS:
            return
        # Duplicate watchdog event with identical content — not a real conflict.
        if old_content == current_content:
            return
        self._record_conflict(path, old_ts, old_content, now)

    def _record_conflict(
        self,
        path: str,
        old_ts: float,
        old_content: str,
        new_ts: float,
    ) -> None:
        CONFLICTS_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(path).stem
        ts_str = time.strftime("%Y%m%d-%H%M%S", time.localtime(old_ts))
        conflict_path = CONFLICTS_DIR / f"{stem}.conflict-{ts_str}.md"
        meta = (
            "---\n"
            f'source_file: "{path}"\n'
            "conflict: true\n"
            f'old_mtime: "{time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(old_ts))}"\n'
            f'new_mtime: "{time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(new_ts))}"\n'
            f"window_seconds: {_CONFLICT_WINDOW_SECONDS}\n"
            "---\n\n"
        )
        try:
            conflict_path.write_text(meta + old_content, encoding="utf-8")
            log.warning(
                "conflict detected for %s: previous version saved to %s",
                path,
                conflict_path,
            )
        except Exception as e:
            log.error("failed to record conflict for %s: %s", path, e)

    def _schedule_sync(self, path: str) -> None:
        old_timer = self._timers.pop(path, None)
        if old_timer is not None:
            old_timer.cancel()
        timer = threading.Timer(_DEBOUNCE_SECONDS, self._sync, args=(path,))
        timer.daemon = True
        self._timers[path] = timer
        timer.start()

    def _sync(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        sync_func = _SYNC_FUNCS.get(self._subdir)
        if sync_func is None:
            log.debug("watchdog: change in %s/ (no DB sync): %s", self._subdir, path)
            return
        try:
            count = sync_func()
            log.info(
                "watchdog synced %s (triggered by %s): %d records",
                self._subdir,
                path,
                count,
            )
        except Exception as e:
            log.error(
                "watchdog sync failed for %s (triggered by %s): %s",
                self._subdir,
                path,
                e,
            )

    def cancel_pending(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


class _Watcher:
    """Owns one Observer and its per-subdir handlers."""

    def __init__(self) -> None:
        self._observer: Optional[Observer] = None
        self._handlers: list[_KnowledgeEventHandler] = []
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self._observer is not None:
                return False
            observer = Observer()
            scheduled = 0
            for subdir in _WATCH_DIRS:
                watch_path = KNOWLEDGE_DIR / subdir
                if not watch_path.exists():
                    log.warning("watchdog: skip missing dir %s", watch_path)
                    continue
                handler = _KnowledgeEventHandler(subdir)
                observer.schedule(handler, str(watch_path), recursive=True)
                self._handlers.append(handler)
                scheduled += 1
            if scheduled == 0:
                log.warning("watchdog: no watchable directories found, not starting")
                self._handlers.clear()
                return False
            try:
                observer.start()
            except Exception as e:
                log.error("watchdog observer.start() failed: %s", e)
                self._handlers.clear()
                return False
            self._observer = observer
            log.info(
                "watchdog started: watching %d dirs under %s", scheduled, KNOWLEDGE_DIR
            )
            return True

    def stop(self) -> bool:
        with self._lock:
            if self._observer is None:
                return False
            for handler in self._handlers:
                handler.cancel_pending()
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception as e:
                log.warning("watchdog stop error: %s", e)
            self._observer = None
            self._handlers.clear()
            log.info("watchdog stopped")
            return True

    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()


# Module-level singleton (per task spec).
_watcher_instance: Optional[_Watcher] = None


def start_watcher() -> bool:
    """Start the knowledge watchdog. Returns False if already running."""
    global _watcher_instance
    if _watcher_instance is not None and _watcher_instance.is_running():
        return False
    watcher = _Watcher()
    if not watcher.start():
        return False
    _watcher_instance = watcher
    return True


def stop_watcher() -> bool:
    """Stop the knowledge watchdog. Returns False if it was not running."""
    global _watcher_instance
    if _watcher_instance is None:
        return False
    result = _watcher_instance.stop()
    _watcher_instance = None
    return result


def is_running() -> bool:
    """Return whether the knowledge watchdog is currently running."""
    return _watcher_instance is not None and _watcher_instance.is_running()
