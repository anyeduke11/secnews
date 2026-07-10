"""Phase 41 Skill 管理仓库: skills 表 CRUD + 列表筛选。

设计要点
--------
- name / url / install_command 必填
- source 为 npx / uvx / curl / git / manual 之一, 默认 manual
- tags 用 JSON 字符串数组存储; 列表筛选时用 LIKE 匹配 (小数据集够用)
- 时间戳用 ISO 8601 UTC, 与项目其他表一致
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_SOURCES = ("npx", "uvx", "curl", "git", "manual")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
class SkillItem:
    """Skill 内存模型。"""

    __slots__ = (
        "id",
        "name",
        "url",
        "install_command",
        "description",
        "source",
        "tags",
        "created_at",
        "updated_at",
    )

    def __init__(
        self,
        *,
        id: int,
        name: str,
        url: str,
        install_command: str,
        description: Optional[str],
        source: str,
        tags: list[str],
        created_at: str,
        updated_at: str,
    ):
        self.id = id
        self.name = name
        self.url = url
        self.install_command = install_command
        self.description = description
        self.source = source
        self.tags = tags
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "install_command": self.install_command,
            "description": self.description,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_skill(row: sqlite3.Row) -> SkillItem:
    raw_tags = row["tags"] or "[]"
    try:
        tags = json.loads(raw_tags) if isinstance(raw_tags, str) else []
    except (TypeError, ValueError):
        tags = []
    if not isinstance(tags, list):
        tags = []
    return SkillItem(
        id=int(row["id"]),
        name=str(row["name"]),
        url=str(row["url"]),
        install_command=str(row["install_command"]),
        description=(str(row["description"]) if row["description"] is not None else None),
        source=str(row["source"] or "manual"),
        tags=[str(t) for t in tags],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _validate_required(name: str, url: str, install_command: str) -> None:
    if not name or not name.strip():
        raise InternalException("name 不能为空")
    if not url or not url.strip():
        raise InternalException("url 不能为空")
    if not install_command or not install_command.strip():
        raise InternalException("install_command 不能为空")


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class SkillRepository:
    """对 ``skills`` 表的 CRUD + 列表筛选。"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add(
        self,
        *,
        name: str,
        url: str,
        install_command: str,
        description: Optional[str] = None,
        source: str = "manual",
        tags: Optional[list[str]] = None,
    ) -> SkillItem:
        """新增 skill。"""
        _validate_required(name, url, install_command)
        if source not in VALID_SOURCES:
            raise InternalException(
                f"source 必须为 {', '.join(VALID_SOURCES)}; got {source!r}"
            )
        tags_list = tags or []
        if not isinstance(tags_list, list):
            raise InternalException("tags 必须为字符串数组")
        tags_json = json.dumps([str(t) for t in tags_list], ensure_ascii=False)

        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO skills (
                    name, url, install_command, description, source, tags,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    url.strip(),
                    install_command,
                    description,
                    source,
                    tags_json,
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
            logger.error("skill add failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"skill add failed: {e}") from e

        new_id = int(cur.lastrowid)
        return SkillItem(
            id=new_id,
            name=name.strip(),
            url=url.strip(),
            install_command=install_command,
            description=description,
            source=source,
            tags=[str(t) for t in tags_list],
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------
    def list(
        self,
        *,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> tuple[list[SkillItem], int]:
        """多维筛选 + 关键词搜索 (name/description LIKE)。"""
        conn = get_connection()
        limit = max(1, min(int(limit or 200), 1000))

        where: list[str] = []
        params: list = []
        if source:
            where.append("source = ?")
            params.append(source)
        if tag:
            # tags 是 JSON 字符串, 用 LIKE 包含匹配; 简单且够用
            where.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        if keyword:
            kw = keyword.strip()
            if kw:
                where.append("(name LIKE ? OR description LIKE ?)")
                like_kw = f"%{kw}%"
                params.extend([like_kw, like_kw])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM skills {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM skills
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [_row_to_skill(r) for r in rows], total

    def get(self, skill_id: int) -> Optional[SkillItem]:
        conn = get_connection()
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (int(skill_id),)).fetchone()
        return _row_to_skill(row) if row else None

    def count_by_source(self) -> dict[str, int]:
        """按 source 统计总数 (用于筛选 tab 徽标)。"""
        conn = get_connection()
        rows = conn.execute(
            "SELECT source, COUNT(*) AS n FROM skills GROUP BY source"
        ).fetchall()
        out: dict[str, int] = {s: 0 for s in VALID_SOURCES}
        for r in rows:
            key = str(r["source"] or "manual")
            if key in out:
                out[key] = int(r["n"])
        total_row = conn.execute("SELECT COUNT(*) AS n FROM skills").fetchone()
        out["all"] = int(total_row["n"]) if total_row else 0
        return out

    # ------------------------------------------------------------------
    # 更新 / 删除
    # ------------------------------------------------------------------
    def update(
        self,
        skill_id: int,
        *,
        name: Optional[str] = None,
        url: Optional[str] = None,
        install_command: Optional[str] = None,
        description: Optional[str] = None,
        source: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> SkillItem:
        """部分更新; 未传的字段保持原值。"""
        existing = self.get(skill_id)
        if existing is None:
            raise InternalException(f"skill {skill_id} 不存在")

        new_name = name.strip() if name is not None else existing.name
        new_url = url.strip() if url is not None else existing.url
        new_install = install_command if install_command is not None else existing.install_command
        new_description = description if description is not None else existing.description
        new_source = source if source is not None else existing.source
        new_tags = tags if tags is not None else existing.tags

        _validate_required(new_name, new_url, new_install)
        if new_source not in VALID_SOURCES:
            raise InternalException(
                f"source 必须为 {', '.join(VALID_SOURCES)}; got {new_source!r}"
            )
        tags_json = json.dumps([str(t) for t in new_tags], ensure_ascii=False)

        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE skills SET
                    name = ?, url = ?, install_command = ?,
                    description = ?, source = ?, tags = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_name,
                    new_url,
                    new_install,
                    new_description,
                    new_source,
                    tags_json,
                    now,
                    int(skill_id),
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("skill update failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"skill update failed: {e}") from e

        updated = self.get(skill_id)
        if updated is None:
            raise InternalException(f"skill {skill_id} disappeared after update")
        return updated

    def delete(self, skill_id: int) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM skills WHERE id = ?", (int(skill_id),))
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("skill delete failed", extra={"trace_id": "", "err": str(e)})
            raise InternalException(f"skill delete failed: {e}") from e


__all__ = ["SkillRepository", "SkillItem", "VALID_SOURCES"]
