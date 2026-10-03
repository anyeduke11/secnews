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
- **Destructive migrations**: any migration that DROPs (or bulk-DELETEs
  from) a referenced parent table MUST wrap its statements in an
  explicit ``PRAGMA foreign_keys=OFF;`` ... ``PRAGMA foreign_keys=ON;``
  pair inside the script (precedent: 112_remove_bid_data.sql). With the
  connection-level ``foreign_keys=ON`` default, dropping a parent table
  fires child-side ``ON DELETE CASCADE`` — migration 124
  (2026-09-26 22:29) lost thousands of hotspot_tags rows this way; see
  the incident note in 124_paper_category.sql and the rule anchor
  126_foreign_keys_off_note.sql.
"""
from __future__ import annotations

import os
import re
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
def secure_db_file(path: Path | str) -> None:
    """库文件权限收紧 0600 — v0.8.6 P0-9 / 审计 F0-12b (R6)。

    hotspot.db 含 llm_secrets 密文与全量 wiki 正文投影, 默认 0644 等于
    同机任意进程可读。SQLite 的 -wal/-shm 边车同样承载活数据, 一并
    best-effort 收紧; 不存在/失败仅 debug 留痕 (权限收紧不阻断连接路径)。
    """
    p = Path(path)
    for target in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm")):
        try:
            if target.exists():
                os.chmod(target, 0o600)
        except OSError as exc:
            logger.debug(f"chmod 0600 failed for {target}: {exc}")


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
    # v0.8.6 P0-9 (F0-12b): 库文件权限收紧 — 每线程首连时执行 (幂等,
    # 已 0600 的 chmod 是 no-op); warm/cold 未 ATTACH 时目标不存在即跳过。
    for _p in (db_path, warm_path, cold_path):
        if _p is not None:
            secure_db_file(_p)
    logger.debug(  # P0-10: 每线程首连的例行事件 → DEBUG
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


def warm_table(name: str, conn: sqlite3.Connection | None = None) -> str:
    """Qualified table name for a WARM-tier table — v0.8.6 P0-7 / 审计 E15。

    与 ``knowledge_items_table`` 同一 accessor 哲学 (写路由应当被**声明**,
    而非依赖 SQLite 裸名解析的环境探测): main 命中 → 裸名 (单库模式,
    migration 在 main 建表); main 无而 warm 已 ATTACH → ``warm.<name>``
    (migrate_temp_layers 迁移后的生产位置); warm 未 ATTACH → 裸名。

    供 quality_check_logs / content_fingerprints 等跨 main/warm 两种落位
    的表统一读写路由, 消除 "裸名 INSERT 到底落到哪个库" 的歧义 (E15
    两处写库失败的修复配套)。conn 参数允许调用方注入已知连接 (如
    collection_dedup 的测试 mock 场景), 避免与注入连接分叉。
    """
    c = conn or get_connection()
    attached = {r[1] for r in c.execute("PRAGMA database_list").fetchall()}
    if "warm" not in attached:
        return name
    in_main = c.execute(
        "SELECT 1 FROM main.sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return name if in_main else f"warm.{name}"


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


# v0.8.6 P0-4 (审计 S2): 迁移逐语句重放时, 视为 "该条已满足" 的错误标记。
# - "duplicate column"  : ALTER ADD COLUMN 目标列已存在 (历史库手工加过)
# - "already exists"    : 重放时 executescript 已 auto-commit 的非幂等 DDL
#                         (无 IF NOT EXISTS 的 CREATE TABLE/INDEX/TRIGGER)
_ALREADY_SATISFIED_MARKERS = ("duplicate column", "already exists")


def _split_sql_statements(sql: str) -> list[str]:
    """把迁移 SQL 切成单条语句 (trigger 安全) — v0.8.6 P0-4 / 审计 S2。

    用 ``sqlite3.complete_statement`` 逐行累积切分: 它理解 CREATE TRIGGER
    的 ``BEGIN ... END`` 体 (体内 ``;`` 不会提前切断); 简单 ``split(';')``
    会把 trigger 体撕碎 (migrations 里有 20+ 处 CREATE TRIGGER)。纯注释/
    空白片段丢弃 (``conn.execute`` 不接受空查询)。
    """
    statements: list[str] = []
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            statements.append(buf)
            buf = ""
    if buf.strip():
        statements.append(buf)

    def _is_noise(s: str) -> bool:
        return all(
            not ln.strip() or ln.strip().startswith("--")
            for ln in s.splitlines()
        )

    return [s for s in statements if not _is_noise(s)]


def _replay_migration_tolerant(conn: sqlite3.Connection, sql: str, version: str) -> None:
    """duplicate column 迁移的逐语句容忍重放 — v0.8.6 P0-4 / 审计 S2。

    旧行为 (S2 缺陷): executescript 遇 duplicate column 整文件中止, 直接
    记版本 + continue — 同文件**后续语句被静默丢弃且永久标记完成**。

    新行为: 从头逐条重放 (此前 DDL 已 auto-commit 的部分靠幂等性 no-op):
    - "duplicate column" / "already exists" → 该条视为已满足, warning 跳过
    - 其余异常照常向上抛 (走既有失败路径, **不冒充完成**)
    重放全部走完后, 由调用方记录版本。
    """
    statements = _split_sql_statements(sql)
    skipped = 0
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if any(marker in msg for marker in _ALREADY_SATISFIED_MARKERS):
                skipped += 1
                logger.warning(
                    f"migration {version}: statement already satisfied — "
                    f"skipped ({str(exc)[:160]}; stmt: {stmt.strip()[:160]})"
                )
                continue
            raise
    logger.warning(
        f"migration {version}: duplicate-column tolerant replay done — "
        f"{len(statements)} statements, {skipped} skipped as already-satisfied"
    )


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

    v0.8.6 P0-4 (审计 S2): a "duplicate column" failure no longer marks
    the whole file as applied — the runner replays the file statement by
    statement (trigger-safe splitting), skipping only the already-
    satisfied statements so that **subsequent statements still apply**;
    any other error during replay propagates (never fakes completion).

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
            # 列 (如真实库 digests.last_read_at / knowledge_items.attention_score)。
            # v0.8.6 P0-4 (审计 S2): 旧行为 "记版本 + continue" 会把同文件
            # 后续语句静默丢弃且永久标记完成 (半应用) — 改为逐语句容忍重放:
            # duplicate column / already exists 的单条跳过, 后续语句必须生效;
            # 重放中其他错误照常向上抛 (不冒充完成)。
            msg = str(exc).lower()
            if "duplicate column" in msg:
                _replay_migration_tolerant(conn, sql, version)
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
def _ensure_warm_indexes(conn: sqlite3.Connection) -> None:
    """warm 投影热路径索引自愈 — v0.8.6 P0-2 / 审计 E19 (2026-10-02)。

    根因: migration 063 的三个裸名 ``CREATE INDEX`` 恒解析到 main 库 — 而
    生产 ``knowledge_items`` 实际在 warm (4,348 行), main 上只有 119 自愈
    留下的空壳表 → 索引全部建在 0 行表上, 生产每个管线 tick 对 warm 全表
    扫描 (EXPLAIN QUERY PLAN 实测 SCAN + TEMP B-TREE)。main 上的同名索引
    **保留不删**: 单库模式 (测试/无 warm 环境) 下 main.knowledge_items 是
    真实表, 索引有效。

    与 063 同 SQL, 加 warm 限定名 + IF NOT EXISTS 幂等; warm 未 ATTACH /
    表缺失 → no-op; 失败 warning 不阻断 (与 _ensure_warm_knowledge_items
    同 best-effort 契约)。
    """
    attached = {r[1] for r in conn.execute("PRAGMA database_list").fetchall()}
    if "warm" not in attached:
        return
    has_table = conn.execute(
        "SELECT COUNT(*) FROM warm.sqlite_master "
        "WHERE type = 'table' AND name = 'knowledge_items'"
    ).fetchone()[0]
    if not has_table:
        return
    # SQLite 语法: schema 限定在**索引名**上 (`warm.idx ON knowledge_items`),
    # 表名用裸名在 schema 内解析 — ON warm.table 反而 near "." 语法错。
    for ddl in (
        "CREATE INDEX IF NOT EXISTS warm.idx_ki_ingested"
        " ON knowledge_items(ingested_at DESC)",
        "CREATE INDEX IF NOT EXISTS warm.idx_ki_lifecycle"
        " ON knowledge_items(lifecycle)",
        "CREATE INDEX IF NOT EXISTS warm.idx_ki_domain"
        " ON knowledge_items(domain)",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.Error as exc:
            logger.warning(
                f"warm index self-heal failed: {exc}",
                extra={"trace_id": ""},
            )


def _ensure_warm_knowledge_items(conn: sqlite3.Connection) -> None:
    """warm 知识投影自愈 — 治理 T4 入口断供根因修复 (2026-09-26)。

    根因链 (诊断证据链见 docs/superpowers/plans/2026-09-26-kl-pipeline-revival.md):
    warm.db 于 2026-09-18 遗失 (仅剩 0 字节空文件, migration 119 注释已留痕),
    重建后其他 warm 表随启动迁移恢复, 唯 ``knowledge_items`` 投影表
    缺失 → 生产 ``knowledge_items_table()`` 解析为 ``warm.knowledge_items``,
    此后 knowledge_repo.upsert_item 与 T1-T4 全部 SELECT 逐轮抛
    ``no such table`` (各调用点 try/except 吞掉, 静默) → 知识入管断供 13 天
    (wiki_events: agent_write / kl_transition 自 09-13 双双归零, 而采集侧
    hotspots 每日数百条照常入账)。

    迁移 SQL 只能用裸名建表 (018_knowledge.sql → 落 main, 即 main 里那张
    0 行空壳的来历), 无法按 ATTACH 状态条件指向 warm — 故在 init_db 尾部
    以代码级条件自愈: warm 已 ATTACH 且缺表时, 从 main.sqlite_master 拷贝
    权威 DDL (历次迁移已在其上跑全, 含 body/entities 等后加列) 在 warm 重建。
    幂等: 表已在 / warm 未 ATTACH / main 无 DDL 可拷 → no-op 或 warning。
    DDL 执行失败 → warning 留痕后继续 (best-effort 自愈, 不改 init_db 的
    fail-fast 语义; warm 缺表有服务层容错链 + md 回退兜底), 不裸抛
    sqlite3.Error — 遵守本模块 docstring 错误契约。
    """
    attached = {r[1] for r in conn.execute("PRAGMA database_list").fetchall()}
    if "warm" not in attached:
        return
    has_table = conn.execute(
        "SELECT COUNT(*) FROM warm.sqlite_master "
        "WHERE type = 'table' AND name = 'knowledge_items'"
    ).fetchone()[0]
    if has_table:
        return
    row = conn.execute(
        "SELECT sql FROM main.sqlite_master "
        "WHERE type = 'table' AND name = 'knowledge_items'"
    ).fetchone()
    if row is None or not row[0]:
        logger.warning(
            "warm.knowledge_items missing but main has no DDL to rebuild from",
            extra={"trace_id": ""},
        )
        return
    # 裸名 DDL 无法执行到 warm (SQLite 裸名恒解析 main, 会撞 main 已有表),
    # 改写为 warm 限定名; 归一掉 IF NOT EXISTS (上文已确认 warm 无此表)。
    ddl = re.sub(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
        "CREATE TABLE warm.",
        row[0],
        count=1,
        flags=re.IGNORECASE,
    )
    try:
        conn.execute(ddl)
    except sqlite3.Error as exc:
        logger.error(
            f"warm.knowledge_items self-heal failed ({type(exc).__name__}: "
            f"{exc}) — 知识入管将继续静默断供, 请人工重建 warm 投影",
            extra={"trace_id": ""},
        )
        return
    # 终审 Important 修复 (2026-09-26): 建表 ≠ 建索引 — 063 的 3 个索引
    # (ingested_at/lifecycle/domain) 不随 CREATE TABLE 拷贝, 缺失则 T1-T4
    # 触发器与知识仪表盘热路径在 ~4k 行投影上退化为全表扫描。从
    # main.sqlite_master 同拷全部具名索引 (跳过 sql IS NULL 的 sqlite 自动
    # 索引), 归一 IF NOT EXISTS 保持幂等; 单个失败 warning 留痕继续
    # (best-effort 同建表)。
    idx_rows = conn.execute(
        "SELECT sql FROM main.sqlite_master "
        "WHERE type = 'index' AND tbl_name = 'knowledge_items' "
        "AND sql IS NOT NULL"
    ).fetchall()
    for idx_row in idx_rows:
        idx_ddl = re.sub(
            r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?",
            "CREATE INDEX IF NOT EXISTS warm.",
            idx_row[0],
            count=1,
            flags=re.IGNORECASE,
        )
        try:
            conn.execute(idx_ddl)
        except sqlite3.Error as exc:
            logger.warning(
                f"warm.knowledge_items index self-heal failed ({exc}) "
                f"— ddl: {idx_ddl[:120]}",
                extra={"trace_id": ""},
            )
    logger.warning(
        "warm.knowledge_items was missing — rebuilt from main schema "
        "(knowledge ingest had been silently failing; see governance T4)",
        extra={"trace_id": ""},
    )


# v0.8.6 P0-7 (审计 E15): 列级 REFERENCES 子句剥离正则 — warm 表的 FK
# 指向 main 侧表 (跨库 FK SQLite 无法满足) 时整段移除, 覆盖
# ``REFERENCES hotspots(id) [ON DELETE CASCADE]`` 等全部列级形态。
_FK_COLUMN_RE = re.compile(
    r"\s+REFERENCES\s+\"?\w+\"?\s*\([^)]*\)"
    r"(?:\s+ON\s+(?:DELETE|UPDATE)\s+"
    r"(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION))*",
    re.IGNORECASE,
)


def _fix_warm_dangling_fks(conn: sqlite3.Connection) -> None:
    """warm 表悬空 FK 自愈 — v0.8.6 P0-7 / 审计 E15 (2026-10-02)。

    根因: ``scripts/migrate_temp_layers.py`` 把 WARM 表 DDL **原样**拷入
    warm.db, 列级 ``REFERENCES hotspots(id) ON DELETE CASCADE`` 这类指向
    main 侧表的 FK 一并带入。SQLite 的 FK 只在子表所在 schema 内解析父表
    (跨库 FK 不支持), 连接级 ``PRAGMA foreign_keys=ON`` 下父表缺失 →
    每次 INSERT 抛 ``no such table: warm.hotspots`` (生产 439 次, 指纹
    补写全军覆没, 跨轮去重静默失效)。该 FK 在 warm 内**永远不可能生效**
    (ON DELETE CASCADE 同样无法跨库触发), 剥离无语义损失。

    自愈动作 (每张命中表, 参照 112/126 迁移的 foreign_keys OFF 包裹惯例):
    取出行 + 列 + 具名索引 DDL → DROP → 以剥离 REFERENCES 后的 DDL 重建 →
    回灌数据 → 重建索引 → 校验 FK 清零。幂等: 无悬空 FK 即 no-op;
    best-effort 契约同 ``_ensure_warm_knowledge_items`` (单表失败留痕继续,
    不裸抛、不阻断 init_db)。
    """
    attached = {r[1] for r in conn.execute("PRAGMA database_list").fetchall()}
    if "warm" not in attached:
        return
    warm_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM warm.sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    for table in sorted(warm_tables):
        try:
            fks = conn.execute(
                f'PRAGMA warm.foreign_key_list("{table}")'
            ).fetchall()
        except sqlite3.Error:
            continue
        if not fks:
            continue
        missing = sorted({fk[2] for fk in fks if fk[2] not in warm_tables})
        if not missing:
            continue  # 父表都在 warm 内 — 正常 FK, 不动

        row_ddl = conn.execute(
            "SELECT sql FROM warm.sqlite_master "
            "WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if row_ddl is None or not row_ddl[0]:
            continue
        stripped = _FK_COLUMN_RE.sub("", row_ddl[0])
        if "REFERENCES" in stripped.upper():
            logger.warning(
                f"warm.{table}: dangling FK -> {missing} but DDL carries an "
                "unstrippable REFERENCES form — skip rebuild (P0-7/E15)",
                extra={"trace_id": ""},
            )
            continue

        # DROP 后 sqlite_master 即失 — 行/列/索引 DDL 先取
        cols = [
            r[1] for r in conn.execute(
                f'PRAGMA warm.table_info("{table}")'
            ).fetchall()
        ]
        rows = conn.execute(f'SELECT * FROM warm."{table}"').fetchall()
        idx_ddls = [
            r[0] for r in conn.execute(
                "SELECT sql FROM warm.sqlite_master "
                "WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
                (table,),
            ).fetchall()
        ]

        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            # 前缀改写 (与 _ensure_warm_knowledge_items 同法): 正则只吞
            # "CREATE TABLE [IF NOT EXISTS]", 原表名保留在后 → warm.<name>
            new_ddl = re.sub(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
                "CREATE TABLE warm.",
                stripped,
                count=1,
                flags=re.IGNORECASE,
            )
            conn.execute(f'DROP TABLE warm."{table}"')
            conn.execute(new_ddl)
            if rows and cols:
                col_csv = ",".join(f'"{c}"' for c in cols)
                placeholders = ",".join("?" for _ in cols)
                conn.executemany(
                    f'INSERT INTO warm."{table}" ({col_csv}) '
                    f"VALUES ({placeholders})",
                    rows,
                )
            # 索引随 DROP 而去: 同名重建 (warm 限定索引名, 表名裸名在
            # schema 内解析 — 同 _ensure_warm_indexes 的已验证写法)
            for idx_ddl in idx_ddls:
                conn.execute(
                    re.sub(
                        r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?",
                        "CREATE INDEX IF NOT EXISTS warm.",
                        idx_ddl,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                )
        except sqlite3.Error as exc:
            logger.error(
                f"warm.{table} dangling-FK rebuild failed "
                f"({type(exc).__name__}: {exc}) — 表已重建但数据/索引可能"
                f"不完整, 请人工核查 (原 FK 指向 {missing})",
                extra={"trace_id": ""},
            )
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

        leftover = conn.execute(
            f'PRAGMA warm.foreign_key_list("{table}")'
        ).fetchall()
        if leftover:
            logger.error(
                f"warm.{table} still has {len(leftover)} FK(s) after "
                "P0-7 rebuild — unexpected, please inspect",
                extra={"trace_id": ""},
            )
        else:
            logger.warning(
                f"warm.{table}: rebuilt without cross-db-unenforceable FK "
                f"(was -> {missing}; rows restored: {len(rows)}; "
                "see audit E15 / P0-7)",
                extra={"trace_id": ""},
            )


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

    # 治理 T4: warm 知识投影自愈 (必须在 apply_migrations 之后 — 迁移先
    # 把 main 的 knowledge_items 结构推到最新, 自愈拷贝的才是权威 DDL)。
    _ensure_warm_knowledge_items(conn)
    # v0.8.6 P0-2 (E19): warm 投影索引自愈 (表自愈之后 — 空表上建索引无意义)。
    _ensure_warm_indexes(conn)
    # v0.8.6 P0-7 (E15): warm 悬空 FK 自愈 (migrate_temp_layers 原样拷贝
    # DDL 遗留的跨库 FK 使 warm 侧 INSERT 全数失败 — 指纹补写 439 次)。
    _fix_warm_dangling_fks(conn)

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
    "secure_db_file",
    "warm_table",
]
