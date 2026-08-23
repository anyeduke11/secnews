"""wiki_events 表仓储层 (v0.5 §18)。

llm-wiki-2.0 (.md 文件) 与 SQLite 运营层之间的事件对应表 —
两世界的唯一桥梁。知识同步/agent 写回/外部 CLI 调用在此留痕。
表结构见 migration 065_wiki_events.sql。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WikiEventRepo:
    """wiki_events 表 CRUD。"""

    def log(
        self,
        kind: str,
        wiki_path: str = "",
        db_table: str = "",
        db_row_id: str = "",
        agent: str = "",
        payload: dict | None = None,
    ) -> int:
        """记录一条事件, 返回事件 id。

        Args:
            kind: 事件类型 (sync_item / sync_concept / agent_write /
                  cli_agent_run ...)
            wiki_path: 相对 knowledge/ 的路径, 如 items/a1b2c3.md
            db_table + db_row_id: 关联的运营层行
            agent: 产生者标识, 如 collector:bid / agent:dsh
            payload: JSON 扩展字段
        """
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO wiki_events (ts, kind, wiki_path, db_table, db_row_id, agent, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso(),
                kind,
                wiki_path,
                db_table,
                db_row_id,
                agent,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid or 0)

    def trace_by_wiki_path(self, wiki_path: str, limit: int = 50) -> list[dict]:
        """按知识文件路径反查事件流 (时间倒序)。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM wiki_events WHERE wiki_path = ? "
            "ORDER BY ts DESC LIMIT ?",
            (wiki_path, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def trace_by_db_ref(
        self, db_table: str, db_row_id: str, limit: int = 50
    ) -> list[dict]:
        """按运营层表+行正向追踪衍生知识。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM wiki_events WHERE db_table = ? AND db_row_id = ? "
            "ORDER BY ts DESC LIMIT ?",
            (db_table, db_row_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """按 kind 统计事件数 (运维面板用)。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT kind, COUNT(*) AS n FROM wiki_events GROUP BY kind ORDER BY n DESC"
        ).fetchall()
        return {r["kind"]: r["n"] for r in rows}


wiki_event_repo = WikiEventRepo()
