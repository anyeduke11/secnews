"""采集域四表仓储 — collection_runs / crawler_runs / raw_items /
content_fingerprints (migration 001/041/043/055 schema).

R2 收缩批 (2026-09-13): 覆盖 collection_pipeline / collection_dedup /
scheduler/jobs/collect.py 对这四张表的全部写语句 (裸 SQL 归零; 读语句
不动, 留在各宿主), service/job 层只保留业务编排 (值计算 / 逐条异常隔离 /
日志), SQL 逐字搬入。

  - **事务归调用方**: 本 repo 的写方法**不** commit — 生产连接经
    ``backend.repository.db.get_connection`` (thread-local, autocommit
    ``isolation_level=None``), 语句即时落库 (insert_running_row 后
    catchup_watchdog 跨进程可读的语义保持不变); ``write_fingerprints``
    原有的 ``conn.commit()`` 保留在宿主函数原位置。连接由调用方注入
    (单测 ``:memory:``) 或回退 ``get_connection()`` 二选一, 同线程内
    是同一连接。
  - **同步约定**: 全部方法为同步 sqlite3 实现 — 宿主的写函数在
    ``asyncio.to_thread`` 工作线程内调用 (collection_pipeline 的
    线程亲和约定), repo 不引入新的执行模型。
  - **rowcount 语义**: ``insert_fingerprint`` 返回 ``cur.rowcount``
    (INSERT OR IGNORE 冲突时为 0, 宿主累加实际写入数);
    ``mark_run_failed_watchdog`` 返回 rowcount (条件 UPDATE 含
    ``finished_at IS NULL`` 守卫); 其余写方法返回 None / lastrowid。
  - **OperationalError 不吞**: 表缺失 (migration 未跑) 时原样上抛,
    "尽力而为不阻塞采集" 的降级语义留在宿主 try/except。
"""
from __future__ import annotations

import sqlite3

from backend.repository.db import get_connection


class CollectionRepository:
    """采集域四表仓储 (run 审计 + 每源遥测 + 原始条目 + 去重指纹).

    所有方法在 ``self._conn or get_connection()`` 上执行, 不 commit —
    事务边界归调用方 (生产连接为 autocommit, 即时落库)。
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    # ------------------------------------------------------------------
    # collection_runs — 分类 run 审计 (Phase 8: running → 终态)
    # ------------------------------------------------------------------
    def insert_running_run(self, category: str, started_at_iso: str) -> int:
        """插入 status='running' 起始行, 供 catchup_watchdog 检测孤儿.

        item_count / fallback_count 字面量 0; 返回新行 id。
        原 collection_pipeline.insert_running_row 内 INSERT。
        """
        cur = self._c().execute(
            """
            INSERT INTO collection_runs
                (category, started_at, status, item_count, fallback_count)
            VALUES (?, ?, 'running', 0, 0)
            """,
            (category, started_at_iso),
        )
        return int(cur.lastrowid)

    def update_run_finished(
        self,
        run_id: int,
        finished_at_iso: str | None,
        status: str,
        item_count: int,
        fallback_count: int,
        error_msg: str | None,
    ) -> None:
        """起始 'running' 行 → 终态 (Phase 8 主路径).

        原 collection_pipeline.write_collection_run run_id 分支内 UPDATE。
        """
        self._c().execute(
            """
            UPDATE collection_runs SET
                finished_at = ?,
                status = ?,
                item_count = ?,
                fallback_count = ?,
                error_msg = ?
            WHERE id = ?
            """,
            (
                finished_at_iso,
                status,
                item_count,
                fallback_count,
                error_msg,
                int(run_id),
            ),
        )

    def insert_run(
        self,
        category: str,
        started_at_iso: str,
        finished_at_iso: str | None,
        status: str,
        item_count: int,
        fallback_count: int,
        error_msg: str | None,
    ) -> int:
        """老路径一次性整行 INSERT (起始行 INSERT 失败时的 fallback).

        原 collection_pipeline.write_collection_run else 分支内 INSERT。
        """
        cur = self._c().execute(
            """INSERT INTO collection_runs
            (category, started_at, finished_at, status, item_count, fallback_count, error_msg)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                category,
                started_at_iso,
                finished_at_iso,
                status,
                item_count,
                fallback_count,
                error_msg,
            ),
        )
        return int(cur.lastrowid)

    def mark_run_failed_watchdog(self, run_id: int, finished_at_iso: str) -> int:
        """孤儿 run (started_at > 600s 未 finished) 标 failed.

        条件 UPDATE 含 ``AND finished_at IS NULL`` 守卫 (跑完后被
        watchdog 二次扫到时不再覆写终态); 返回 rowcount。
        原 scheduler/jobs/collect.py catchup_watchdog_job 内 UPDATE。
        """
        cur = self._c().execute(
            """
            UPDATE collection_runs
            SET finished_at = ?,
                status = 'failed',
                error_msg = 'watchdog: timeout after 600s'
            WHERE id = ? AND finished_at IS NULL
            """,
            (finished_at_iso, run_id),
        )
        return cur.rowcount

    # ------------------------------------------------------------------
    # crawler_runs — 每源每轮抓取遥测 (Phase 0 Crawler v2 旁路写入)
    # ------------------------------------------------------------------
    def insert_crawler_run(
        self,
        source_id: str,
        category: str,
        started_at: str,
        finished_at: str,
        status: str,
        fetched_count: int,
        accepted_count: int,
        error_msg: str,
        duration_ms: int,
    ) -> None:
        """写入一行每源抓取统计 (write_crawler_runs / _for_source 两处同语句).

        原 collection_pipeline.write_crawler_runs / write_crawler_runs_for_source
        内 INSERT。
        """
        self._c().execute(
            """
            INSERT INTO crawler_runs
                (source_id, category, started_at, finished_at, status,
                 fetched_count, accepted_count, error_msg, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_id, category, started_at, finished_at, status,
             fetched_count, accepted_count, error_msg, duration_ms),
        )

    # ------------------------------------------------------------------
    # raw_items — 原始条目旁路写入 (fetched_at 由 DB default now)
    # ------------------------------------------------------------------
    def insert_raw_item(
        self,
        item_id: str,
        source_id: str,
        title: str,
        url: str,
        summary: str,
        content_hash: str,
        published_at: str,
    ) -> None:
        """写入一行 raw_items (content_hash 16 位截断, fetched_at=datetime('now')).

        原 collection_pipeline.write_raw_items 循环内 INSERT。
        """
        self._c().execute(
            """
            INSERT INTO raw_items
                (item_id, source_id, title, url, summary,
                 content_hash, published_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (item_id, source_id, title, url, summary,
             content_hash, published_at),
        )

    # ------------------------------------------------------------------
    # content_fingerprints — simhash 去重指纹 (入库成功后补写, P0-5)
    # ------------------------------------------------------------------
    def insert_fingerprint(
        self,
        hotspot_id: str,
        simhash_signed: int,
        url_canonical: str,
        title_norm: str,
    ) -> int:
        """补写一条指纹 (UNIQUE(hotspot_id) 冲突时 OR IGNORE 忽略).

        返回 rowcount — 0 表示该 hotspot 指纹已存在 (幂等命中)。
        原 collection_dedup.write_fingerprints 循环内 INSERT OR IGNORE。
        """
        cur = self._c().execute(
            """INSERT OR IGNORE INTO content_fingerprints
               (hotspot_id, simhash, url_canonical, title_norm)
               VALUES (?, ?, ?, ?)""",
            (hotspot_id, simhash_signed, url_canonical, title_norm),
        )
        return cur.rowcount
