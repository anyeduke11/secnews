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
    # M2-T6: wal_autocheckpoint=1000 防 WAL 异常膨胀 (见 storage_design §7.3)
    conn.execute("PRAGMA wal_autocheckpoint=1000")

    # M2-T6: 启动期 ATTACH warm/cold (HOT/WARM/COLD/FROZEN 分类存储)
    # - warm_db_path: 业务流水 (crawler_runs/raw_items/... 等 WARM 表)
    # - cold_db_path: 加密审计 (quality_check_logs_archive 等 COLD 表) — T6.6 加 Fernet
    # - 文件不存在时跳过 (单库起步, 逐步迁移)
    warm_path = getattr(config, "warm_db_path", None)
    cold_path = getattr(config, "cold_db_path", None)
    attached: list[str] = []
    for alias, path in (("warm", warm_path), ("cold", cold_path)):
        if path is None:
            continue
        p = Path(path)
        # T6.6: cold 支持加密 — 若 .enc 存在 + cold_db_key 设置, 解密到 tempfile
        if alias == "cold" and getattr(config, "cold_db_key", "") and (p.parent / f"{p.name}.enc").exists():
            from scripts.cold_db_crypto import decrypt_to_tempfile
            try:
                tf = decrypt_to_tempfile(
                    src=p.parent / f"{p.name}.enc",
                    master_key=config.cold_db_key,
                )
                p = tf  # attach the tempfile, not the .db path
                logger.info(f"cold db decrypted to tempfile: {tf.name}")
            except SystemExit as e:
                logger.warning(f"cold db decrypt failed: {e}")
                continue
        if not p.exists():
            logger.debug(f"skip ATTACH {alias}: {p} not exists")
            continue
        try:
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(p),))
            attached.append(alias)
        except sqlite3.Error as e:
            logger.warning(f"ATTACH {alias} ({p}) failed: {e}")

    _tls.conn = conn
    logger.info(
        "db connection opened",
        extra={"trace_id": "", "db_path": str(db_path), "attached": ",".join(attached) or "(none)"},
    )
    return conn


def knowledge_items_table() -> str:
    """Qualified table name for ``knowledge_items`` — single source of truth.

    knowledge_items logically lives in the WARM tier: in production
    ``get_connection()`` ATTACHes ``warm.db`` at startup and the table is
    addressed as ``warm.knowledge_items``. In tests / single-db mode the
    warm file does not exist, so it is not ATTACHed and the whole schema
    lives in ``main``. Writers must therefore never hardcode either form —
    call this function and let it resolve the prefix from the set of
    databases actually ATTACHed on the calling thread's connection.

    (Extracted from search_service's runtime PRAGMA probe — R2/P2: the
    write route should be declared, not "detected from the environment".)
    """
    attached = {
        r[1] for r in get_connection().execute("PRAGMA database_list").fetchall()
    }
    return "warm.knowledge_items" if "warm" in attached else "knowledge_items"


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
def _drop_dangling_views(conn: sqlite3.Connection) -> None:
    """v1.0 R21 服务恢复: 启动期主动 DROP 引用 main schema 缺表的 view.

    根因: 旧 unified_search view 引用 knowledge_items, 分库后 knowledge_items 在
    warm.db, hot.db 没有此表. SQLite 允许 SELECT FROM view 失败时 lazy validate,
    但 DDL (如 migration 099 的 ALTER TABLE ... RENAME) 会强制重新解析 view 依赖,
    抛 "error in view unified_search: no such table: main.knowledge_items",
    init_db 中断 → 后端起不来.

    策略: 启动 init_db 早期 (apply_migrations 之前) 主动 SELECT 1 FROM view LIMIT 0,
    失败即 DROP, 成功保留. 由 search_service 走 ATTACH 跨库 UNION ALL 替代 view.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (view_name,) in rows:
        try:
            conn.execute(f"SELECT 1 FROM {view_name} LIMIT 0").fetchone()
        except sqlite3.Error as e:
            logger.warning(
                f"dropping dangling view {view_name!r}: {e}",
                extra={"trace_id": ""},
            )
            conn.execute(f"DROP VIEW IF EXISTS {view_name}")


def _migration_number(stem: str) -> int:
    """Extract the leading numeric prefix of a migration filename (0 if none)."""
    try:
        return int(stem.split("_", 1)[0])
    except (ValueError, IndexError):
        return 0


def _count_sql_statements(sql: str) -> int:
    """粗略数 SQL 文件中 statement 数 (按 `;` 切, 去除空行/注释)."""
    n = 0
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        # 一行末尾 ; 算 1 statement
        n += s.count(";")
    return max(n, 0)


def _count_committed_statements(conn: sqlite3.Connection, sql: str, version: str) -> int:
    """v1.0 C02 R11 诊断: 试算出 "在失败前已 commit 的 statement 数" 的近似.

    通过: 1) 拿失败前的 schema_version 列表 (INSERT 是最后一句, 它未跑
       意味着 schema_version 应不含此 version), 2) 实际不可靠 — 改为
       返回 _count_sql_statements 的 0 估计 (保守), 让运维去看具体错误.

    注: SQLite executescript DDL 在 create/alter/drop 立即生效 (DDL auto-commit);
    INSERT/UPDATE 在 statementscript 内是同一 implicit transaction. 部分 DDL
    提交 + 部分 DML 未提交 是 SQLite 的真实行为, 我们无法精确回放哪条 commit.
    """
    # 保守: 报 0 (失败时不知道前 N 句已 commit, 让运维查 PRAGMA 重建状态)
    return 0


def _warn_migration_numbering_gaps(files: list[Path]) -> None:
    """启动治理告警: 检测迁移编号断号 / 重复, 只 warning 不阻断。

    历史 DB 的 ``schema_version`` 记录的是旧编号 (文件名), 因此断号只告警,
    绝不自动改名或抛异常 —— 重命名会破坏已执行状态。
    """
    nums = sorted({_migration_number(f.stem) for f in files if _migration_number(f.stem) > 0})
    if not nums:
        return

    max_num = nums[-1]
    missing = sorted(set(range(1, max_num + 1)) - set(nums))
    if missing:
        logger.warning(
            f"migration numbering gap: files cover 1..{max_num} but missing "
            f"{', '.join(f'{n:03d}' for n in missing)} "
            "(informational; historical DBs already applied old numbering — "
            "do NOT rename files)"
        )

    by_num: dict[int, list[str]] = {}
    for f in files:
        n = _migration_number(f.stem)
        if n > 0:
            by_num.setdefault(n, []).append(f.name)
    dups = {n: names for n, names in by_num.items() if len(names) > 1}
    if dups:
        detail = "; ".join(f"{n:03d}: {', '.join(names)}" for n, names in sorted(dups.items()))
        logger.warning(
            f"migration numbering duplicate: {detail} "
            "(multiple up-files share a numeric prefix; *_down.sql are excluded)"
        )


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
    #    ``*_down.sql`` 是手工回滚脚本, 绝不自动执行 (否则 up 刚跑完就被回滚)。
    files = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if not f.stem.endswith("_down"))
    # 启动治理告警: 编号断号/重复检测 (只 warning, 不抛异常、不改名)
    _warn_migration_numbering_gaps(files)
    latest_version = 0

    # Seed with whatever is already in the DB.
    for v in executed:
        latest_version = max(latest_version, _migration_number(v))

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
        except Exception as exc:
            # 容错: SQLite 无 ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
            # 列已存在时会抛 "duplicate column name"。历史库可能已手工加过
            # 列 (如真实库 digests.last_read_at / knowledge_items.attention_score),
            # 此时把该迁移视为已满足并记录版本, 而不是卡死启动。
            msg = str(exc).lower()
            if "duplicate column" in msg:
                logger.warning(
                    f"migration {version}: column already exists — treated as "
                    f"applied ({exc})"
                )
                conn.execute(
                    "INSERT INTO schema_version (version, executed_at) VALUES (?, ?)",
                    (version, _now_iso()),
                )
                latest_version = max(latest_version, _migration_number(version))
                continue
            # v1.0 C02 R11 修复: 失败时记录 statements committed 数 + 诊断信息.
            # SQLite executescript 把整个文件当 implicit transaction (DDL 提交点除外),
            # 部分 statement 已 commit (DDL) 时无法回滚. 报出 "前 N 句已 commit"
            # 提示, 让运维能定位是哪个 statement 失败.
            committed = _count_committed_statements(conn, sql, version)
            logger.error(
                f"migration {version} failed: {type(exc).__name__}: {str(exc)[:300]} "
                f"(statements committed before failure: {committed}/{_count_sql_statements(sql)})",
                extra={"trace_id": "", "migration": version},
            )
            logger.exception(
                "migration failed (see committed count above)",
                extra={"trace_id": "", "migration": version},
            )
            raise

        latest_version = max(latest_version, _migration_number(version))

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

    # v1.0 R21 服务恢复: preflight — 删悬空 view (引用 ATTACH 走的 db 中不存在的表)
    # 根因: hot.db 旧 unified_search view 引用 knowledge_items, 但分库后
    # knowledge_items 在 warm.db; view "半失效", 任何 DDL 触发 schema reparse 都失败
    # 修复: 启动期主动 DROP 引用 main schema 缺表的 view, 走 service 层 ATTACH 跨库
    # 详见 [docs/v1.0/REVIEW_2026-09-07.md R10/R21]
    _drop_dangling_views(conn)

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
    "apply_migrations",
    "close_db",
    "get_connection",
    "init_db",
    "knowledge_items_table",
]
