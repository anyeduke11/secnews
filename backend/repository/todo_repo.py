"""Phase 36 待办 (Todos) 仓库: todos 表 CRUD

设计要点
--------
- 单 user 本地系统（无 user_id 字段）
- 同一 favorite ``source_id`` 重复添加等价于 no-op (upsert 语义) —
  API 层调用 :py:meth:`add_or_get` 实现
- 收藏快照: favorite-source 添加时从 ``favorites`` 表拷贝
  title/url/source/category, 避免 hotspots 表更新/删除后 todo 显示空标题
- 状态迁移: ``open→done`` 填 ``completed_at``; ``open→archived`` 或
  ``done→archived`` 填 ``archived_at``; ``archived→open`` 清空两个时间戳
- DB 层不加 UNIQUE 约束 (允许 user 加同一 favorite 多次作为多个 task);
  唯一性靠 :py:meth:`add_or_get` 在 favorite 路径下查重
- 时间戳用 ``datetime.now(timezone.utc).isoformat()`` 存为 ISO 字符串
  (与项目其他表一致)

Phase 46: 紧急自动判断
---------------------
- ``deadline`` 列存 'YYYY-MM-DD' (ISO 日期)
- ``urgent`` 列保留作 legacy fallback (旧数据无 deadline 时仍用原值)
- 序列化时 :py:meth:`TodoItem.to_dict` 调用
  :func:`backend.utils.business_days.compute_effective_urgent` 把
  deadline 转换为 effective_urgent, 写回响应。
- 4 象限统计 (by_priority) 也基于 effective_urgent 重算。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.utils.business_days import compute_effective_urgent


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
VALID_SOURCE_TYPES = ("favorite", "manual")
VALID_STATUSES = ("open", "done", "archived")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
class TodoItem:
    """待办条目的内存模型（不直接复用 HotspotItem/FavoriteItem 以保表独立）。

    Phase 46: 新增 ``deadline`` (ISO 日期字符串 'YYYY-MM-DD')。
    序列化时 :py:meth:`to_dict` 把 ``deadline`` 转换为
    ``effective_urgent`` 并写回 ``urgent`` 字段 (实现紧急自动判断)。
    """

    __slots__ = (
        "id",
        "source_type",
        "source_id",
        "title",
        "url",
        "source",
        "category",
        "urgent",          # 原始值 (legacy fallback), 默认 0
        "important",
        "deadline",        # ISO 'YYYY-MM-DD' or None
        "note",
        "status",
        "created_at",
        "updated_at",
        "completed_at",
        "archived_at",
    )

    def __init__(
        self,
        *,
        id: int,
        source_type: str,
        source_id: Optional[str],
        title: str,
        url: Optional[str],
        source: Optional[str],
        category: Optional[str],
        urgent: int,
        important: int,
        deadline: Optional[str],
        note: Optional[str],
        status: str,
        created_at: str,
        updated_at: str,
        completed_at: Optional[str],
        archived_at: Optional[str],
    ):
        self.id = id
        self.source_type = source_type
        self.source_id = source_id
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        self.urgent = urgent
        self.important = important
        self.deadline = deadline
        self.note = note
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.completed_at = completed_at
        self.archived_at = archived_at

    def to_dict(self) -> dict:
        """序列化为 API 响应。

        Phase 46 关键修复: ``urgent`` 字段返回 **effective_urgent**
        (从 deadline 派生), 而非 DB 里的原始值。
        """
        effective_urgent = compute_effective_urgent(
            self.deadline, fallback_urgent=self.urgent,
        )
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "urgent": effective_urgent,  # Phase 46: 派生值
            "important": self.important,
            "deadline": self.deadline,
            "note": self.note,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "archived_at": self.archived_at,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_todo(row: sqlite3.Row) -> TodoItem:
    return TodoItem(
        id=int(row["id"]),
        source_type=str(row["source_type"]),
        source_id=(str(row["source_id"]) if row["source_id"] is not None else None),
        title=str(row["title"]),
        url=(str(row["url"]) if row["url"] is not None else None),
        source=(str(row["source"]) if row["source"] is not None else None),
        category=(str(row["category"]) if row["category"] is not None else None),
        urgent=int(row["urgent"]),
        important=int(row["important"]),
        deadline=(str(row["deadline"]) if row["deadline"] is not None else None),
        note=(str(row["note"]) if row["note"] is not None else None),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=(str(row["completed_at"]) if row["completed_at"] is not None else None),
        archived_at=(str(row["archived_at"]) if row["archived_at"] is not None else None),
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class TodoRepository:
    """对 ``todos`` 表的 CRUD + 简单聚合。"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add_or_get(
        self,
        *,
        source_type: str,
        source_id: Optional[str],
        title: str,
        url: Optional[str],
        source: Optional[str],
        category: Optional[str],
        important: int,
        deadline: Optional[str] = None,
        note: Optional[str] = None,
    ) -> tuple[TodoItem, bool]:
        """添加或幂等返回已存在 todo。

        - ``source_type=favorite`` + ``source_id`` 重复 → 返回 (existing, False)
        - 其他情况 (manual / 新 favorite) → 新建 (new, True)

        favorite-source 路径下, 若 ``source_id`` 已在 ``favorites`` 表中,
        title/url/source/category 用 favorites 表的快照值 (调用方传的值被
        覆盖, 避免脏数据写入)。

        Phase 46: 不再接受 ``urgent`` 参数, 紧急由 deadline 派生;
        ``important`` 仍由用户决定。
        """
        if source_type not in VALID_SOURCE_TYPES:
            raise InternalException(
                f"source_type must be one of {VALID_SOURCE_TYPES}; got {source_type!r}"
            )
        # title 校验: manual 必填; favorite 可空 (下方从 favorites 表派生)
        if source_type == "manual" and (not title or not str(title).strip()):
            raise InternalException("title is required when source_type=manual")
        if source_type == "favorite" and not (source_id and str(source_id).strip()):
            raise InternalException("source_id is required when source_type=favorite")
        if source_type == "manual" and source_id is not None:
            # manual 永远不允许带 source_id
            source_id = None

        conn = get_connection()
        now = _now_iso()

        # favorite-source 重复检查 (走 partial index idx_todos_source)
        if source_type == "favorite":
            existing_row = conn.execute(
                """
                SELECT * FROM todos
                WHERE source_type = 'favorite' AND source_id = ?
                """,
                (source_id,),
            ).fetchone()
            if existing_row is not None:
                return _row_to_todo(existing_row), False

        # favorite-source 时, 优先从 favorites 表拉快照 (保证 source/category 正确)
        if source_type == "favorite":
            fav_row = conn.execute(
                "SELECT title, source, url, category FROM favorites WHERE hotspot_id = ?",
                (source_id,),
            ).fetchone()
            if fav_row is not None:
                title = str(fav_row["title"])
                source = str(fav_row["source"]) if fav_row["source"] is not None else source
                url = str(fav_row["url"]) if fav_row["url"] is not None else url
                category = (
                    str(fav_row["category"]) if fav_row["category"] is not None else category
                )

        # Phase 46: 紧急从 deadline 派生; DB 仍存 urgent=0 (兼容 legacy schema)
        stored_urgent = 0

        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO todos (
                    source_type, source_id, title, url, source, category,
                    urgent, important, deadline, note, status,
                    created_at, updated_at, completed_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, NULL, NULL)
                """,
                (
                    source_type,
                    source_id,
                    title,
                    url,
                    source,
                    category,
                    int(stored_urgent),
                    int(important or 0),
                    (deadline.strip() if isinstance(deadline, str) and deadline.strip() else None),
                    note,
                    now,
                    now,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("todo add failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"todo add failed: {e}") from e

        new_id = int(cur.lastrowid)
        item = TodoItem(
            id=new_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            url=url,
            source=source,
            category=category,
            urgent=int(stored_urgent),
            important=int(important or 0),
            deadline=(deadline.strip() if isinstance(deadline, str) and deadline.strip() else None),
            note=note,
            status="open",
            created_at=now,
            updated_at=now,
            completed_at=None,
            archived_at=None,
        )
        return item, True

    # ------------------------------------------------------------------
    # 列表 + 统计
    # ------------------------------------------------------------------
    def list(
        self,
        *,
        status: Optional[str] = None,
        urgent: Optional[int] = None,
        important: Optional[int] = None,
        limit: int = 200,
    ) -> tuple[list[TodoItem], int]:
        """多维筛选 + 排序 (effective_urgent DESC, important DESC, created_at DESC)。

        Phase 46: ``urgent`` 参数指 **effective_urgent** (派生自 deadline);
        legacy 数据 (deadline IS NULL) fallback 到 ``urgent`` 列。
        SQL 没法直接算业务日差, 所以 urgent 过滤走「全量 SELECT + Python
        recalc + 二次筛选 + 截 limit」。行数小, 性能可接受。
        """
        conn = get_connection()
        limit = max(1, min(int(limit or 200), 1000))

        where: list[str] = []
        params: list = []
        if status:
            where.append("status = ?")
            params.append(status)
        if important is not None:
            where.append("important = ?")
            params.append(int(important))
        # urgent 过滤在 Python 层做 (见下)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM todos {where_sql}", params
        ).fetchone()
        total_raw = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM todos
            {where_sql}
            ORDER BY important DESC, created_at DESC
            """,
            params,
        ).fetchall()

        items = [_row_to_todo(r) for r in rows]

        # Phase 46: Python 层按 effective_urgent 二次过滤 + 排序
        if urgent is not None:
            target = int(urgent)
            items = [
                it for it in items
                if int(it.to_dict()["urgent"]) == target
            ]
        # 排序: effective_urgent DESC → important DESC → created_at DESC
        def _sort_key(it: HotspotItem) -> tuple:
            d = it.to_dict()
            return (
                -int(d["urgent"]),       # effective_urgent 大者排前
                -int(it.important or 0),
                -(int(datetime.fromisoformat(it.created_at.replace("Z", "+00:00")).timestamp())
                  if it.created_at else 0),
                -it.id,                   # 稳定兜底
            )

        items.sort(key=_sort_key)
        # Phase 46: total 反映「过滤后」真实行数, 便于前端分页/计数
        total = len(items)
        return items[:limit], total

    def count(self) -> dict:
        """返回 by_status {open, done, archived} + by_priority 四象限 + total。

        Phase 46: by_priority 用 effective_urgent 派生, 不用 DB 里的 urgent 列。
        """
        conn = get_connection()
        by_status = {"open": 0, "done": 0, "archived": 0}
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM todos GROUP BY status"
        ).fetchall()
        for r in rows:
            key = str(r["status"])
            if key in by_status:
                by_status[key] = int(r["n"])

        # by_priority — 4 象限 (open + done 一起, archived 不计入)
        # Phase 46: 用 effective_urgent (Python 派生) 而非 DB 列
        pri_rows = conn.execute(
            """
            SELECT id, important, urgent, deadline
            FROM todos
            WHERE status IN ('open', 'done')
            """
        ).fetchall()
        by_priority = {
            "urgent_important": 0,
            "urgent_only": 0,
            "important_only": 0,
            "neither": 0,
        }
        for r in pri_rows:
            d = r["deadline"]
            effective_urgent = compute_effective_urgent(
                d, fallback_urgent=int(r["urgent"] or 0),
            )
            imp = int(r["important"] or 0)
            if effective_urgent and imp:
                by_priority["urgent_important"] += 1
            elif effective_urgent and not imp:
                by_priority["urgent_only"] += 1
            elif not effective_urgent and imp:
                by_priority["important_only"] += 1
            else:
                by_priority["neither"] += 1

        total_row = conn.execute("SELECT COUNT(*) AS n FROM todos").fetchone()
        total = int(total_row["n"]) if total_row else 0

        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
        }

    def get(self, todo_id: int) -> Optional[TodoItem]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (int(todo_id),)).fetchone()
        return _row_to_todo(row) if row else None

    # ------------------------------------------------------------------
    # 更新 / 删除
    # ------------------------------------------------------------------
    def update(
        self,
        todo_id: int,
        *,
        important: Optional[int] = None,
        deadline: Optional[str] = None,
        deadline_set: bool = False,
        status: Optional[str] = None,
        note: Optional[str] = None,
    ) -> TodoItem:
        """部分更新 + 状态迁移时间戳维护。

        Phase 46:
        - ``urgent`` 不再可写 (紧急由 deadline 派生)。
        - ``deadline`` 字段 (None=不改; 字符串=覆盖; 空字符串=清空)。
        - ``deadline_set=True`` 显式标记「deadline 字段已传入, 即使值为 None
          也应清空」。区分「未传字段」与「传了 None/空字符串」。

        ``important`` 仍可改 (无 deadline_set 歧义问题, 因为 0 是合法值)。

        状态迁移:
        - ``open → done`` 填 ``completed_at``
        - ``open → archived`` 或 ``done → archived`` 填 ``archived_at``
          (completed_at 保留)
        - ``archived → open`` 清空 ``completed_at`` / ``archived_at``
        - 其他 (e.g. done → open) 也清空时间戳, 保持「复活」语义

        任何修改同步 ``updated_at``。
        """
        conn = get_connection()
        existing = self.get(todo_id)
        if existing is None:
            raise InternalException(f"todo {todo_id} not found")

        new_urgent = existing.urgent  # Phase 46: 不再接受外部修改
        new_important = int(important) if important is not None else existing.important
        new_status = status if status is not None else existing.status
        new_note = note if note is not None else existing.note

        # deadline 处理: deadline_set=True 表示调用方明确传了此字段
        #   - deadline 是 None 或空字符串 → 清空
        #   - deadline 是有效字符串 → 覆盖
        # deadline_set=False → 保持现有值 (兼容旧调用方)
        if deadline_set:
            if deadline is None:
                new_deadline = None
            elif isinstance(deadline, str):
                s = deadline.strip()
                new_deadline = s if s else None
            else:
                new_deadline = None
        else:
            new_deadline = existing.deadline

        if new_status not in VALID_STATUSES:
            raise InternalException(
                f"status must be one of {VALID_STATUSES}; got {new_status!r}"
            )

        now = _now_iso()
        completed_at = existing.completed_at
        archived_at = existing.archived_at

        prev_status = existing.status
        if new_status == "done":
            # open → done 或 done → done 都填 completed_at
            completed_at = now
        elif new_status == "archived":
            # open → archived 或 done → archived 都填 archived_at
            # (completed_at 保留, 表示「先完成再归档」)
            archived_at = now
        elif new_status == "open":
            # 复活: 清空两个时间戳
            completed_at = None
            archived_at = None

        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE todos SET
                    urgent = ?,
                    important = ?,
                    deadline = ?,
                    status = ?,
                    note = ?,
                    updated_at = ?,
                    completed_at = ?,
                    archived_at = ?
                WHERE id = ?
                """,
                (
                    int(new_urgent),
                    int(new_important),
                    new_deadline,
                    new_status,
                    new_note,
                    now,
                    completed_at,
                    archived_at,
                    int(todo_id),
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("todo update failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"todo update failed: {e}") from e

        updated = self.get(todo_id)
        # 不应发生, 但保险
        if updated is None:
            raise InternalException(f"todo {todo_id} disappeared after update")
        return updated

    def delete(self, todo_id: int) -> bool:
        """硬删除。返回是否实际删除了一行。"""
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM todos WHERE id = ?", (int(todo_id),))
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("todo delete failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"todo delete failed: {e}") from e

    # ------------------------------------------------------------------
    # 跨表查询: 列出「已收藏但未入 todo」的 favorites 项
    # ------------------------------------------------------------------
    def list_available_favorites(self, limit: int = 200) -> list[dict]:
        """返回 favorites 表中 ``hotspot_id NOT IN (todos where source_type=favorite)`` 的项。

        优先从 ``favorites`` 自身读快照 (title/source/url/category);
        若某字段为 NULL/空, 再回退到 ``hotspots`` 表 (LEFT JOIN)。
        """
        conn = get_connection()
        limit = max(1, min(int(limit or 200), 1000))
        rows = conn.execute(
            """
            SELECT
                f.hotspot_id AS hotspot_id,
                f.title      AS fav_title,
                f.source     AS fav_source,
                f.url        AS fav_url,
                f.category   AS fav_category,
                h.url        AS hot_url,
                h.source     AS hot_source,
                h.category   AS hot_category
            FROM favorites f
            LEFT JOIN hotspots h ON h.id = f.hotspot_id
            WHERE f.hotspot_id NOT IN (
                SELECT source_id FROM todos WHERE source_type = 'favorite' AND source_id IS NOT NULL
            )
            ORDER BY f.favorited_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            title = r["fav_title"] or ""
            source = r["fav_source"] or r["hot_source"] or ""
            url = r["fav_url"] or r["hot_url"] or ""
            category = r["fav_category"] or r["hot_category"]
            out.append(
                {
                    "hotspot_id": str(r["hotspot_id"]),
                    "title": str(title),
                    "url": str(url),
                    "source": str(source) if source else None,
                    "category": str(category) if category else None,
                }
            )
        return out


__all__ = ["TodoRepository", "TodoItem", "VALID_SOURCE_TYPES", "VALID_STATUSES"]
