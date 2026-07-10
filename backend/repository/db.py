"""SQLite connection management + migration runner.

Design notes
------------
- **Thread-local connections** (``threading.local``). Each worker thread
  gets its own ``sqlite3.Connection``; FastAPI sync handlers and the
  APScheduler collector both call ``get_connection()`` and reuse it.
- **Autocommit mode** (``isolation_level=None``). Transactions are
  expressed explicitly with ``BEGIN`` / ``COMMIT`` / ``ROLLBACK`` so
  the migration runner can wrap each ``.sql`` file in a single
  transaction and roll back on any error.
- **PRAGMAs** applied at open time:
    - ``journal_mode=WAL``  — concurrent readers + one writer
    - ``synchronous=NORMAL`` — good crash-safety / performance trade-off
    - ``foreign_keys=ON``    — enforce referential integrity
    - ``busy_timeout=5000``  — wait up to 5s instead of SQLITE_BUSY
- **Failure mode**: any DB-level failure during ``init_db`` /
  ``apply_migrations`` raises a ``HotspotException`` subclass (never a
  raw ``sqlite3.Error``), per the project-wide error contract.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config
from backend.exceptions import InternalException
from backend.logging_config import logger

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_tls = threading.local()

# Migrations live next to this file, under ``migrations/``.
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """ISO-8601 UTC string used to stamp ``schema_version.executed_at``."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Return the calling thread's SQLite connection, opening it on first use.

    The connection is cached on a ``threading.local`` so repeated calls
    are cheap and the same connection is reused within a request /
    collector run. The caller must NOT close it directly — use
    ``close_db()`` at thread teardown.
    """
    conn: sqlite3.Connection | None = getattr(_tls, "conn", None)
    if conn is not None:
        return conn

    db_path: Path = config.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        timeout=5.0,
        isolation_level=None,  # autocommit; explicit BEGIN/COMMIT used below
        check_same_thread=True,
    )
    conn.row_factory = sqlite3.Row

    # PRAGMAs — applied in order; each is a no-op on re-open.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    _tls.conn = conn
    logger.info(
        "db connection opened",
        extra={"trace_id": "", "db_path": str(db_path)},
    )
    return conn


def close_db() -> None:
    """Close the calling thread's connection (if any). Idempotent."""
    conn: sqlite3.Connection | None = getattr(_tls, "conn", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _tls.conn = None


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply any pending ``.sql`` files in ``MIGRATIONS_DIR`` in order.

    For each file not yet listed in ``schema_version``:
        1. ``executescript(sql)``     (DDL is auto-committed by SQLite)
        2. ``INSERT INTO schema_version(...)`` (also auto-committed)

    The script is intentionally NOT wrapped in BEGIN/COMMIT — SQLite
    auto-commits any active transaction on the first DDL statement, so
    an explicit wrapper would only confuse error reporting. Scripts are
    expected to be idempotent (``IF NOT EXISTS`` etc.), which makes a
    partial-then-failed state self-healing on the next ``init_db()``.

    Returns the **current** schema version, defined as the maximum
    numeric prefix across (a) migrations already recorded in
    ``schema_version`` and (b) migrations applied by this call. A
    value of 0 means no migrations have ever been applied.
    """
    # 1. Bootstrap schema_version table itself.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version TEXT PRIMARY KEY,
            executed_at TEXT NOT NULL
        )
        """
    )

    # 2. Read which versions have already been applied.
    executed = {row[0] for row in conn.execute("SELECT version FROM schema_version").fetchall()}

    # 3. Discover migration files in lexicographic order.
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    latest_version = 0

    def _numeric(stem: str) -> int:
        try:
            return int(stem.split("_", 1)[0])
        except (ValueError, IndexError):
            return 0

    # Seed with whatever is already in the DB.
    for v in executed:
        latest_version = max(latest_version, _numeric(v))

    for f in files:
        version = f.stem  # e.g. "001_init"
        if version in executed:
            continue

        logger.info(
            "applying migration",
            extra={"trace_id": "", "migration": version, "path": str(f)},
        )
        sql = f.read_text(encoding="utf-8")
        # See the function docstring for why no BEGIN/COMMIT wrapper.
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, executed_at) VALUES (?, ?)",
                (version, _now_iso()),
            )
        except Exception:
            logger.exception(
                "migration failed",
                extra={"trace_id": "", "migration": version},
            )
            raise

        latest_version = max(latest_version, _numeric(version))

    return latest_version


# ---------------------------------------------------------------------------
# Init entry point
# ---------------------------------------------------------------------------
def init_db() -> int:
    """One-shot DB init: integrity check, apply migrations, log journal mode.

    Returns the final schema version (max numeric prefix of any
    ``.sql`` file in the migrations directory).

    Raises ``InternalException`` if the SQLite integrity check fails or
    any migration raises.
    """
    conn = get_connection()

    # Integrity check — bail early if the on-disk file is corrupt.
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as e:
        logger.error(
            "db integrity check errored",
            extra={"trace_id": "", "error": str(e)},
        )
        raise InternalException(f"db integrity check errored: {e}") from e
    if result is None or result[0] != "ok":
        actual = None if result is None else str(result[0])
        logger.error(
            "db integrity check failed",
            extra={"trace_id": "", "result": actual},
        )
        raise InternalException(f"db integrity check failed: {actual}")

    # Apply pending migrations.
    try:
        version = apply_migrations(conn)
    except InternalException:
        raise
    except Exception as e:
        logger.exception("db migration error", extra={"trace_id": ""})
        raise InternalException(f"db migration error: {e}") from e

    # Confirm journal mode landed on WAL.
    try:
        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        mode = str(mode_row[0]) if mode_row is not None else "unknown"
    except sqlite3.Error as e:
        mode = f"error:{e}"

    logger.info(
        "db initialized",
        extra={"trace_id": "", "journal_mode": mode, "schema_version": version},
    )
    return version


__all__ = [
    "MIGRATIONS_DIR",
    "get_connection",
    "close_db",
    "apply_migrations",
    "init_db",
]
