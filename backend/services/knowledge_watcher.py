"""Knowledge watchdog — watches knowledge/*.md files and syncs to SQLite.

Watches:
- ``knowledge/items/``      → :func:`full_sync_items_to_db`
- ``knowledge/concepts/``   → :func:`full_sync_concepts_to_db`
- ``knowledge/learning/``   → conflict detection + publish task status sync

Publish task status sync (spec 6.4):
- When ``knowledge/learning/tasks/done/task-{id}.md`` is created, the watcher
  parses ``published_url`` from frontmatter and calls
  :func:`content_service.update_publish_status` with status="done".
- When ``knowledge/learning/tasks/failed/task-{id}.md`` is created, the
  watcher calls ``update_publish_status`` with status="failed".

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
import re
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.services import content_service as _content_service
from backend.services.knowledge_sync import (
    KNOWLEDGE_DIR,
    sync_concept_to_db,
    sync_draft_to_db,
    sync_item_to_db,
)
from backend.services.map_updater import update_map as _update_map

log = logging.getLogger("hotspot.knowledge_watcher")

# Subdirectories of KNOWLEDGE_DIR to watch.
_WATCH_DIRS = ("items", "concepts", "learning", "content/drafts")
# P1-4: 单文件增量同步函数 — 单文件变更只同步该文件, 不再触发全目录重扫
# (此前 4,143 文件全量扫描 + 孤儿删除, 单文件改动即全目录 IO, 且目录扫描
# 期间文件暂时缺失会误删 DB 行)。孤儿清理留给 startup/维护期的全量 sync。
_SYNC_FILE_FUNCS = {
    "items": sync_item_to_db,
    "concepts": sync_concept_to_db,
    "content/drafts": sync_draft_to_db,
}

CONFLICTS_DIR = KNOWLEDGE_DIR / ".conflicts"
_CONFLICT_WINDOW_SECONDS = 5.0  # 从 2s 延长到 5s，减少批量写入误报
_DEBOUNCE_SECONDS = 1.0
# 冷却期: 同一文件连续冲突后，N秒内不再重复报
_COOLDOWN_SECONDS = 180.0  # 3 分钟冷却


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
        # path -> cooldown_until_ts (冷却期内不再记录冲突)
        self._cooldown: dict[str, float] = {}
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
        # 冷却期内不新建独立冲突文件 (避免文件爆炸),
        # 但被覆盖内容仍追加到 per-file rollup — 不再静默丢弃真实冲突
        if path in self._cooldown and now < self._cooldown[path]:
            self._append_conflict_rollup(path, old_ts, old_content, now)
            return
        self._record_conflict(path, old_ts, old_content, now)
        # 进入冷却期
        self._cooldown[path] = now + _COOLDOWN_SECONDS

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

    def _append_conflict_rollup(
        self,
        path: str,
        old_ts: float,
        old_content: str,
        new_ts: float,
    ) -> None:
        """冷却期内的冲突: 追加到单一 rollup 文件 (每文件一个).

        与 ``_record_conflict`` 的区别: 不新建独立快照文件,
        而是把被覆盖的旧内容逐段追加, 避免高频冲突刷爆 .conflicts/
        同时保证冷却期内的真实冲突不丢数据。
        """
        CONFLICTS_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(path).stem
        rollup_path = CONFLICTS_DIR / f"{stem}.conflict-rollup.md"
        meta = (
            "\n---\n"
            f'source_file: "{path}"\n'
            "conflict: true\n"
            "rollup: true\n"
            f'old_mtime: "{time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(old_ts))}"\n'
            f'new_mtime: "{time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(new_ts))}"\n'
            f"window_seconds: {_CONFLICT_WINDOW_SECONDS}\n"
            "---\n\n"
        )
        try:
            with open(rollup_path, "a", encoding="utf-8") as f:
                f.write(meta + old_content)
            log.warning(
                "conflict during cooldown for %s: previous version appended to %s",
                path,
                rollup_path,
            )
        except Exception as e:
            log.error("failed to append conflict rollup for %s: %s", path, e)

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
        sync_file_func = _SYNC_FILE_FUNCS.get(self._subdir)
        if sync_file_func is None:
            # learning/ subdir: check for publish task status files (spec 6.4)
            # and compile done files for _MAP.md update (spec 6.3)
            if self._subdir == "learning":
                _maybe_sync_publish_status(path)
                _maybe_update_map(path)
            else:
                log.debug("watchdog: change in %s/ (no DB sync): %s", self._subdir, path)
            return
        try:
            # P1-4: 单文件增量同步 (此前为全目录 full_sync_items_to_db 等)
            item_id = sync_file_func(path)
            log.info(
                "watchdog synced %s (triggered by %s): %s",
                self._subdir,
                path,
                item_id,
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
        self._observer: Observer | None = None
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
_watcher_instance: _Watcher | None = None


# ── Publish task status sync (spec 6.4) ────────────────────────

_TASK_FILE_RE = re.compile(r"task-(\d+)\.md$")


def _maybe_sync_publish_status(path: str) -> None:
    """Check if *path* is a publish task status file and sync draft status.

    Triggered when files under ``learning/tasks/done/`` or
    ``learning/tasks/failed/`` are created/modified. Parses the task id
    from the filename and ``published_url`` (for done) from frontmatter,
    then calls :func:`content_service.update_publish_status`.
    """
    match = _TASK_FILE_RE.search(path)
    if match is None:
        return
    task_id = int(match.group(1))

    # Determine status from parent directory name.
    normalized = path.replace("\\", "/")
    if "/tasks/done/" in normalized:
        status = "done"
    elif "/tasks/failed/" in normalized:
        status = "failed"
    else:
        # pending/ or processing/ — no status update needed.
        return

    published_url: str | None = None
    error: str | None = None

    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        log.warning("watchdog: failed to read task file %s: %s", path, e)
        return

    if text.startswith("---"):
        parts = text.split("---", 2)
        frontmatter = parts[1] if len(parts) >= 3 else ""
        if status == "done":
            url_match = re.search(
                r'published_url:\s*"?([^\n"]+)"?', frontmatter
            )
            if url_match:
                published_url = url_match.group(1).strip()
        elif status == "failed":
            err_match = re.search(
                r'error:\s*"?(.+?)"?\s*$', frontmatter, re.MULTILINE
            )
            if err_match:
                error = err_match.group(1).strip().strip('"').strip("'")

    # Update publish status
    try:
        _content_service.update_publish_status(
            task_id=task_id,
            status=status,
            published_url=published_url,
            error=error,
        )
        log.info(
            "watchdog synced publish status: task %d → %s (published_url=%s)",
            task_id, status, published_url,
        )
    except Exception as e:
        log.error(
            "watchdog: failed to sync publish status for task %d: %s",
            task_id, e,
        )


def _maybe_update_map(path: str) -> None:
    """Check if *path* is a compile-done task file and update _MAP.md.

    Triggered when files under ``learning/tasks/done/`` are created.
    Detects ``task-{id}.md`` pattern and calls ``map_updater.update_map()``.
    Also triggers SOUL.md regeneration (Phase 1j Task 10.3: design §7.2 Step 5).
    """
    match = _TASK_FILE_RE.search(path)
    if match is None:
        return

    normalized = path.replace("\\", "/")
    if "/tasks/done/" not in normalized:
        return

    # Check task_type is "compile" by reading frontmatter
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        log.warning("watchdog: failed to read task file %s: %s", path, e)
        return

    if text.startswith("---"):
        parts = text.split("---", 2)
        frontmatter = parts[1] if len(parts) >= 3 else ""
        if re.search(r'task_type:\s*"?compile"?', frontmatter):
            try:
                _update_map()
                log.info("watchdog updated _MAP.md after compile task done: %s", path)
            except Exception as e:
                log.error("watchdog: failed to update _MAP.md: %s", e)
            # Phase 1j Task 10.3: trigger SOUL.md regeneration after compile
            _maybe_regenerate_soul()


# ── SOUL.md regeneration (Phase 1j Task 10.3) ──────────────────

_SOUL_DEBOUNCE_SECONDS = 5.0
_last_soul_trigger: float = 0.0


def _maybe_regenerate_soul() -> None:
    """Regenerate SOUL.md after compile task completion (design §7.2 Step 5).

    Debounced by ``_SOUL_DEBOUNCE_SECONDS`` (5s) to avoid repeated
    triggers when multiple compile tasks finish in quick succession.
    """
    global _last_soul_trigger
    now = time.time()
    if (now - _last_soul_trigger) < _SOUL_DEBOUNCE_SECONDS:
        log.debug("watchdog: SOUL regeneration debounced (last trigger %.1fs ago)", now - _last_soul_trigger)
        return
    _last_soul_trigger = now

    try:
        # Phase 1j Task 10.3: create_soul_task() drops a task .md into
        # tasks/pending/ for the agent loop to pick up (soul_service has
        # no direct regenerate function; create_soul_task is the entry).
        from backend.services.soul_service import create_soul_task
        create_soul_task()
        log.info("watchdog triggered SOUL.md regeneration task after compile task done")
    except Exception as e:
        log.error("watchdog: failed to trigger SOUL.md regeneration: %s", e)


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
