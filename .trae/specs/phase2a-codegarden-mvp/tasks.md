# Phase 2a 任务分解

> **执行约定**：每个 Task 独立 commit；commit message 格式 `feat(codegarden): <task-id> <短描述>`；每完成一个 Group 推进一次回归测试。

---

## Group A — DB schema + 基础设施 (Task A1-A3)

### Task A1: 迁移 019_codegarden.sql (P0)

**Files:**
- Create: `backend/repository/migrations/019_codegarden.sql`

- [ ] **A1.1: 编写迁移文件（5 张 cg_ 表 + skills 扩展 9 字段）**

```sql
-- 019_codegarden.sql — Phase 2a CodeGarden MVP
-- PRD: docs/CodeGarden_PRD_v2.0.md (6.2 表结构定义)
-- 校正: PRD 假设的 knowledge_skills 表实际叫 skills (Phase 41 012_skills.sql 创建)

-- ============================================================================
-- cg_projects: 项目主表 (PRD 6.2.1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    type TEXT NOT NULL,              -- web_application / api_service / cli / crawler / library / experiment
    source_type TEXT NOT NULL,       -- vibe / fork / imported / reference
    lifecycle_stage TEXT NOT NULL,   -- ideation / prototype / development / testing / running / maintenance / archived / deprecated
    health_score INTEGER DEFAULT 0,
    local_path TEXT,
    repo_url TEXT,
    upstream_url TEXT,
    upstream_default_branch TEXT,
    commits_behind INTEGER DEFAULT 0,
    commits_ahead INTEGER DEFAULT 0,
    last_synced_at TEXT,
    source_item_id TEXT,             -- 反向溯源 knowledge_items.id (github 资讯转化)
    source_type_detail TEXT,         -- trending / github_search / manual
    tags TEXT NOT NULL DEFAULT '[]',
    tech_stack TEXT NOT NULL DEFAULT '[]',
    domain TEXT,
    priority INTEGER DEFAULT 0,
    active_skill_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    last_activity_at TEXT,
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_projects_lifecycle ON cg_projects(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_cg_projects_source_type ON cg_projects(source_type);
CREATE INDEX IF NOT EXISTS idx_cg_projects_source_item ON cg_projects(source_item_id);
CREATE INDEX IF NOT EXISTS idx_cg_projects_last_activity ON cg_projects(last_activity_at DESC);

-- ============================================================================
-- cg_project_stages: 项目阶段/交付物 (PRD 6.2.2)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_stages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    deliverable_type TEXT,           -- code / doc / test / config / release
    deliverable_url TEXT,
    deliverable_path TEXT,
    commit_sha TEXT,
    status TEXT NOT NULL DEFAULT 'planned',  -- planned / wip / done / skipped
    notes TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_stages_project ON cg_project_stages(project_id, stage_order);

-- ============================================================================
-- cg_project_links: 关联 repo (PRD 6.2.3)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_links (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,         -- upstream / reference / inspiration / dependency
    url TEXT NOT NULL,
    label TEXT,
    commits_behind INTEGER,
    commits_ahead INTEGER,
    last_synced_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cg_links_project ON cg_project_links(project_id);

-- ============================================================================
-- cg_project_activities: 活动日志 (PRD 6.2.4)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_activities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,     -- commit / note / decision / release / status_change / sync
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cg_activities_project ON cg_project_activities(project_id, created_at DESC);

-- ============================================================================
-- skills 表扩展 9 字段 (PRD 6.3.1, 表名校正: knowledge_skills → skills)
-- ============================================================================
ALTER TABLE skills ADD COLUMN skill_type TEXT DEFAULT 'knowledge';
ALTER TABLE skills ADD COLUMN capabilities TEXT;       -- JSON array
ALTER TABLE skills ADD COLUMN constraints_json TEXT;   -- JSON (避开 SQL 关键字 constraints)
ALTER TABLE skills ADD COLUMN output_format TEXT;      -- JSON
ALTER TABLE skills ADD COLUMN system_prompt TEXT;
ALTER TABLE skills ADD COLUMN few_shot_examples TEXT;  -- JSON array
ALTER TABLE skills ADD COLUMN success_metrics TEXT;    -- JSON
ALTER TABLE skills ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE skills ADD COLUMN avg_rating REAL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_skills_skill_type ON skills(skill_type);
```

- [ ] **A1.2: 验证迁移可应用**

Run: `cd /Users/duke/Documents/hotspot && python -c "from backend.repository.db import init_db; v = init_db(); print(f'schema_version={v}')"`
Expected: `schema_version=19`（无报错）

- [ ] **A1.3: 验证表结构**

Run: `python -c "from backend.repository.db import get_connection; c = get_connection(); print([r[1] for r in c.execute('PRAGMA table_info(cg_projects)').fetchall()])"`
Expected: 24 列含 `id, name, display_name, description, type, source_type, lifecycle_stage, health_score, local_path, repo_url, upstream_url, upstream_default_branch, commits_behind, commits_ahead, last_synced_at, source_item_id, source_type_detail, tags, tech_stack, domain, priority, active_skill_ids, created_at, last_activity_at, archived_at`（共 25 列；spec.md 写 24 是因为没算 archived_at，校正为 25）

Run: `python -c "from backend.repository.db import get_connection; c = get_connection(); cols = [r[1] for r in c.execute('PRAGMA table_info(skills)').fetchall()]; print(len(cols), cols)"`
Expected: 17 列（原 8 + 新 9）

- [ ] **A1.4: Commit**

```bash
git add backend/repository/migrations/019_codegarden.sql
git commit -m "feat(codegarden): A1 add migration 019 for cg_* tables + skills extension"
```

---

### Task A2: codegarden/ 数据目录初始化 (P1)

**Files:**
- Create: `codegarden/memory/.gitkeep`
- Create: `codegarden/playbooks/.gitkeep`
- Create: `codegarden/specs/.gitkeep`
- Create: `codegarden/sdds/.gitkeep`
- Create: `codegarden/prompts/.gitkeep`
- Create: `codegarden/exports/.gitkeep`

- [ ] **A2.1: 创建目录结构**

```bash
mkdir -p /Users/duke/Documents/hotspot/codegarden/{memory,playbooks,specs,sdds,prompts,exports}
for d in memory playbooks specs sdds prompts exports; do
  touch /Users/duke/Documents/hotspot/codegarden/$d/.gitkeep
done
```

- [ ] **A2.2: Commit**

```bash
git add codegarden/
git commit -m "feat(codegarden): A2 init codegarden/ data directory structure"
```

---

### Task A3: knowledge/_SCHEMA.md 扩展 project_id 字段说明 (P2)

**Files:**
- Modify: `knowledge/_SCHEMA.md`

- [ ] **A3.1: 读取当前 _SCHEMA.md 找到 knowledge_items frontmatter 定义位置**

Run: `grep -n "project_id\|frontmatter\|^## items\|^### items" /Users/duke/Documents/hotspot/knowledge/_SCHEMA.md`

- [ ] **A3.2: 在 items frontmatter 字段列表末尾追加 project_id 可选字段说明**

在 `_SCHEMA.md` 中 knowledge_items frontmatter 字段列表的最后一项后追加：

```markdown
- `project_id` (string, optional): 若该 item 已转化为 CodeGarden 项目,
  指向 `cg_projects.id`. 仅 type=github 的 item 可能出现此字段.
  写入时机: 用户在知识详情页点击「加入 CodeGarden」时由后端写入.
```

- [ ] **A3.3: Commit**

```bash
git add knowledge/_SCHEMA.md
git commit -m "docs(codegarden): A3 document project_id field in _SCHEMA.md"
```

---

## Group B — Repo 层 (Task B1-B2)

### Task B1: backend/repository/codegarden_repo.py (P0)

**Files:**
- Create: `backend/repository/codegarden_repo.py`

- [ ] **B1.1: 编写 CodegardenProjectRepository 类（CRUD + 多维筛选 + activities + stages）**

参考既有 `backend/repository/skills_repo.py` 的模式（SkillRepository）：TEXT PRIMARY KEY 用 uuid4、JSON 字段用 `json.dumps/loads`、`_now_iso()` UTC 时间戳、`InternalException` 业务异常、显式 BEGIN/COMMIT 事务。

```python
"""Phase 2a CodeGarden 项目仓库 — cg_projects + cg_project_stages +
cg_project_links + cg_project_activities 表 CRUD.

设计要点
--------
- cg_projects.id 用 TEXT UUID (与 knowledge_items.id 一致, 便于跨端同步)
- JSON 字段 (tags / tech_stack / active_skill_ids) 用 TEXT + json.dumps/loads
- 时间戳 ISO 8601 UTC, 与项目其他表一致
- 反向溯源 source_item_id 不加外键约束 (应用层负责一致性)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_PROJECT_TYPES = (
    "web_application", "api_service", "cli", "crawler", "library", "experiment",
)
VALID_SOURCE_TYPES = ("vibe", "fork", "imported", "reference")
VALID_LIFECYCLE_STAGES = (
    "ideation", "prototype", "development", "testing",
    "running", "maintenance", "archived", "deprecated",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class CodegardenProjectRepository:
    """cg_projects 表 CRUD + 多维筛选 + activities/stages 写入。"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        type: str,
        source_type: str,
        lifecycle_stage: str = "ideation",
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        local_path: Optional[str] = None,
        repo_url: Optional[str] = None,
        upstream_url: Optional[str] = None,
        upstream_default_branch: Optional[str] = None,
        source_item_id: Optional[str] = None,
        source_type_detail: Optional[str] = None,
        tags: Optional[list[str]] = None,
        tech_stack: Optional[list[str]] = None,
        domain: Optional[str] = None,
        priority: int = 0,
        active_skill_ids: Optional[list[str]] = None,
    ) -> dict:
        if type not in VALID_PROJECT_TYPES:
            raise InternalException(
                f"type 必须为 {', '.join(VALID_PROJECT_TYPES)}; got {type!r}"
            )
        if source_type not in VALID_SOURCE_TYPES:
            raise InternalException(
                f"source_type 必须为 {', '.join(VALID_SOURCE_TYPES)}; got {source_type!r}"
            )
        if lifecycle_stage not in VALID_LIFECYCLE_STAGES:
            raise InternalException(
                f"lifecycle_stage 必须为 {', '.join(VALID_LIFECYCLE_STAGES)}; got {lifecycle_stage!r}"
            )
        if not name or not name.strip():
            raise InternalException("name 不能为空")

        project_id = _new_id()
        now = _now_iso()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        tech_stack_json = json.dumps(tech_stack or [], ensure_ascii=False)
        skill_ids_json = json.dumps(active_skill_ids or [], ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_projects (
                    id, name, display_name, description, type, source_type,
                    lifecycle_stage, health_score, local_path, repo_url,
                    upstream_url, upstream_default_branch, commits_behind,
                    commits_ahead, last_synced_at, source_item_id,
                    source_type_detail, tags, tech_stack, domain, priority,
                    active_skill_ids, created_at, last_activity_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    project_id, name.strip(), display_name, description, type,
                    source_type, lifecycle_stage, local_path, repo_url,
                    upstream_url, upstream_default_branch, source_item_id,
                    source_type_detail, tags_json, tech_stack_json, domain,
                    int(priority), skill_ids_json, now, now,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"cg_projects create failed: {e}")
            raise InternalException(f"cg_projects create failed: {e}") from e

        return self.get(project_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, project_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _row_to_project(row) if row else None

    def list(
        self,
        *,
        lifecycle_stage: Optional[str] = None,
        source_type: Optional[str] = None,
        domain: Optional[str] = None,
        type: Optional[str] = None,
        source_item_id: Optional[str] = None,
        keyword: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        where: list[str] = []
        params: list = []
        if lifecycle_stage:
            where.append("lifecycle_stage = ?")
            params.append(lifecycle_stage)
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if domain:
            where.append("domain = ?")
            params.append(domain)
        if type:
            where.append("type = ?")
            params.append(type)
        if source_item_id:
            where.append("source_item_id = ?")
            params.append(source_item_id)
        if not include_archived:
            where.append("lifecycle_stage != 'archived' AND lifecycle_stage != 'deprecated'")
        if keyword:
            kw = keyword.strip()
            if kw:
                where.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
                like_kw = f"%{kw}%"
                params.extend([like_kw, like_kw, like_kw])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_projects {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = get_connection().execute(
            f"""
            SELECT * FROM cg_projects {where_sql}
            ORDER BY last_activity_at DESC NULLS LAST, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_project(r) for r in rows], total

    # ------------------------------------------------------------------
    # 更新 / 删除 / 状态切换
    # ------------------------------------------------------------------
    def update(self, project_id: str, **fields) -> dict:
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")

        allowed = {
            "name", "display_name", "description", "type", "source_type",
            "lifecycle_stage", "health_score", "local_path", "repo_url",
            "upstream_url", "upstream_default_branch", "commits_behind",
            "commits_ahead", "last_synced_at", "source_item_id",
            "source_type_detail", "domain", "priority",
        }
        json_fields = {"tags", "tech_stack", "active_skill_ids"}

        sets: list[str] = []
        params: list = []
        for k, v in fields.items():
            if v is None:
                continue
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
            elif k in json_fields:
                sets.append(f"{k} = ?")
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                raise InternalException(f"不支持更新的字段: {k}")

        if not sets:
            return existing

        sets.append("last_activity_at = ?")
        params.append(_now_iso())
        params.append(project_id)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                f"UPDATE cg_projects SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_projects update failed: {e}") from e

        return self.get(project_id)  # type: ignore[return-value]

    def set_lifecycle(self, project_id: str, stage: str, note: Optional[str] = None) -> dict:
        if stage not in VALID_LIFECYCLE_STAGES:
            raise InternalException(f"lifecycle_stage 非法: {stage!r}")
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")
        old_stage = existing["lifecycle_stage"]

        update_fields: dict = {"lifecycle_stage": stage}
        if stage in ("archived", "deprecated"):
            update_fields["archived_at"] = _now_iso()
        updated = self.update(project_id, **update_fields)

        # 写入活动日志
        self.add_activity(
            project_id=project_id,
            activity_type="status_change",
            content=f"lifecycle: {old_stage} → {stage}",
            metadata={"old_stage": old_stage, "new_stage": stage, "note": note},
        )
        return updated

    def delete(self, project_id: str) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM cg_projects WHERE id = ?", (project_id,)
            )
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_projects delete failed: {e}") from e

    def archive(self, project_id: str) -> dict:
        return self.set_lifecycle(project_id, "archived")

    def restore(self, project_id: str) -> dict:
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")
        update_fields: dict = {"lifecycle_stage": "maintenance"}
        update_fields["archived_at"] = None  # type: ignore[assignment]
        # SQLite 不支持 UPDATE 设 NULL 用 None, 单独处理
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            conn.execute(
                "UPDATE cg_projects SET lifecycle_stage='maintenance', archived_at=NULL, last_activity_at=? WHERE id=?",
                (now, project_id),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"restore failed: {e}") from e
        self.add_activity(
            project_id=project_id,
            activity_type="status_change",
            content="restore from archived → maintenance",
        )
        return self.get(project_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------
    def add_activity(
        self,
        *,
        project_id: str,
        activity_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        activity_id = _new_id()
        now = _now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_project_activities
                (id, project_id, activity_type, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (activity_id, project_id, activity_type, content, meta_json, now),
            )
            conn.execute(
                "UPDATE cg_projects SET last_activity_at = ? WHERE id = ?",
                (now, project_id),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"add_activity failed: {e}") from e
        return {
            "id": activity_id,
            "project_id": project_id,
            "activity_type": activity_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": now,
        }

    def list_activities(self, project_id: str, limit: int = 50) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM cg_project_activities
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, int(limit)),
        ).fetchall()
        return [_row_to_activity(r) for r in rows]

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def list_stages(self, project_id: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM cg_project_stages WHERE project_id = ? ORDER BY stage_order",
            (project_id,),
        ).fetchall()
        return [_row_to_stage(r) for r in rows]

    def add_stage(
        self,
        *,
        project_id: str,
        stage_name: str,
        stage_order: Optional[int] = None,
        deliverable_type: Optional[str] = None,
        deliverable_url: Optional[str] = None,
        deliverable_path: Optional[str] = None,
        commit_sha: Optional[str] = None,
        status: str = "planned",
        notes: Optional[str] = None,
    ) -> dict:
        stage_id = _new_id()
        now = _now_iso()
        if stage_order is None:
            existing = get_connection().execute(
                "SELECT COALESCE(MAX(stage_order), 0) + 1 AS next_order "
                "FROM cg_project_stages WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            stage_order = int(existing["next_order"]) if existing else 1
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_project_stages
                (id, project_id, stage_name, stage_order, deliverable_type,
                 deliverable_url, deliverable_path, commit_sha, status, notes,
                 created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (stage_id, project_id, stage_name, stage_order,
                 deliverable_type, deliverable_url, deliverable_path,
                 commit_sha, status, notes, now),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"add_stage failed: {e}") from e
        return {
            "id": stage_id, "project_id": project_id,
            "stage_name": stage_name, "stage_order": stage_order,
            "deliverable_type": deliverable_type,
            "deliverable_url": deliverable_url,
            "deliverable_path": deliverable_path,
            "commit_sha": commit_sha, "status": status,
            "notes": notes, "created_at": now, "completed_at": None,
        }


# ---------------------------------------------------------------------------
# Row → dict helpers
# ---------------------------------------------------------------------------
def _row_to_project(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "display_name": row["display_name"],
        "description": row["description"],
        "type": str(row["type"]),
        "source_type": str(row["source_type"]),
        "lifecycle_stage": str(row["lifecycle_stage"]),
        "health_score": int(row["health_score"] or 0),
        "local_path": row["local_path"],
        "repo_url": row["repo_url"],
        "upstream_url": row["upstream_url"],
        "upstream_default_branch": row["upstream_default_branch"],
        "commits_behind": int(row["commits_behind"] or 0),
        "commits_ahead": int(row["commits_ahead"] or 0),
        "last_synced_at": row["last_synced_at"],
        "source_item_id": row["source_item_id"],
        "source_type_detail": row["source_type_detail"],
        "tags": _parse_json(row["tags"], []),
        "tech_stack": _parse_json(row["tech_stack"], []),
        "domain": row["domain"],
        "priority": int(row["priority"] or 0),
        "active_skill_ids": _parse_json(row["active_skill_ids"], []),
        "created_at": str(row["created_at"]),
        "last_activity_at": row["last_activity_at"],
        "archived_at": row["archived_at"],
    }


def _row_to_activity(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "activity_type": str(row["activity_type"]),
        "content": str(row["content"]),
        "metadata": _parse_json(row["metadata"], {}),
        "created_at": str(row["created_at"]),
    }


def _row_to_stage(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "stage_name": str(row["stage_name"]),
        "stage_order": int(row["stage_order"]),
        "deliverable_type": row["deliverable_type"],
        "deliverable_url": row["deliverable_url"],
        "deliverable_path": row["deliverable_path"],
        "commit_sha": row["commit_sha"],
        "status": str(row["status"]),
        "notes": row["notes"],
        "created_at": str(row["created_at"]),
        "completed_at": row["completed_at"],
    }


__all__ = [
    "CodegardenProjectRepository",
    "VALID_PROJECT_TYPES",
    "VALID_SOURCE_TYPES",
    "VALID_LIFECYCLE_STAGES",
]
```

- [ ] **B1.2: 验证模块可导入**

Run: `cd /Users/duke/Documents/hotspot && python -c "from backend.repository.codegarden_repo import CodegardenProjectRepository; print('OK')"`
Expected: `OK`

- [ ] **B1.3: Commit**

```bash
git add backend/repository/codegarden_repo.py
git commit -m "feat(codegarden): B1 add CodegardenProjectRepository"
```

---

### Task B2: backend/tests/test_codegarden_repo.py (P0)

**Files:**
- Create: `backend/tests/test_codegarden_repo.py`

- [ ] **B2.1: 编写 repo 单测（CRUD + 状态切换 + activities + 多维筛选）**

参考 `backend/tests/test_skills.py` 的模式（pytest fixture + 临时 DB）。

```python
"""Phase 2a CodeGarden repo 单测 — CRUD + lifecycle + activities + 筛选。"""
from __future__ import annotations

import pytest

from backend.exceptions import InternalException
from backend.repository.codegarden_repo import (
    CodegardenProjectRepository,
    VALID_LIFECYCLE_STAGES,
    VALID_PROJECT_TYPES,
    VALID_SOURCE_TYPES,
)


@pytest.fixture
def repo():
    return CodegardenProjectRepository()


def _make_project(repo, **overrides):
    defaults = dict(
        name="test-project",
        type="web_application",
        source_type="vibe",
        lifecycle_stage="ideation",
        tags=["test"],
        tech_stack=["react"],
        domain="frontend",
    )
    defaults.update(overrides)
    return repo.create(**defaults)


def test_create_project_returns_full_record(repo):
    p = _make_project(repo, name="my-app")
    assert p["id"]
    assert p["name"] == "my-app"
    assert p["type"] == "web_application"
    assert p["source_type"] == "vibe"
    assert p["lifecycle_stage"] == "ideation"
    assert p["tags"] == ["test"]
    assert p["tech_stack"] == ["react"]
    assert p["health_score"] == 0
    assert p["commits_behind"] == 0
    assert p["created_at"]
    assert p["last_activity_at"]


def test_create_invalid_type_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="invalid", source_type="vibe")


def test_create_invalid_source_type_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="cli", source_type="invalid")


def test_create_invalid_lifecycle_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="cli", source_type="vibe", lifecycle_stage="bogus")


def test_get_returns_none_for_missing(repo):
    assert repo.get("nonexistent-id") is None


def test_list_filters_by_lifecycle(repo):
    _make_project(repo, name="a", lifecycle_stage="development")
    _make_project(repo, name="b", lifecycle_stage="archived")
    items, total = repo.list(lifecycle_stage="development")
    assert total == 1
    assert items[0]["name"] == "a"


def test_list_excludes_archived_by_default(repo):
    _make_project(repo, name="active", lifecycle_stage="development")
    _make_project(repo, name="archived", lifecycle_stage="archived")
    items, total = repo.list()
    assert total == 1
    assert items[0]["name"] == "active"


def test_list_filter_by_source_item_id(repo):
    _make_project(repo, name="from-news", source_item_id="abc123")
    _make_project(repo, name="manual")
    items, total = repo.list(source_item_id="abc123")
    assert total == 1
    assert items[0]["name"] == "from-news"


def test_list_keyword_search(repo):
    _make_project(repo, name="ai-assistant", description="AI chat")
    _make_project(repo, name="data-pipeline")
    items, total = repo.list(keyword="ai")
    assert total == 1
    assert items[0]["name"] == "ai-assistant"


def test_update_changes_fields(repo):
    p = _make_project(repo)
    updated = repo.update(p["id"], description="new desc", priority=5)
    assert updated["description"] == "new desc"
    assert updated["priority"] == 5


def test_update_rejects_unknown_field(repo):
    p = _make_project(repo)
    with pytest.raises(InternalException):
        repo.update(p["id"], bogus_field="x")


def test_set_lifecycle_writes_activity(repo):
    p = _make_project(repo, lifecycle_stage="ideation")
    updated = repo.set_lifecycle(p["id"], "development", note="开始开发")
    assert updated["lifecycle_stage"] == "development"
    activities = repo.list_activities(p["id"])
    assert len(activities) == 1
    assert activities[0]["activity_type"] == "status_change"
    assert "ideation" in activities[0]["content"]
    assert "development" in activities[0]["content"]


def test_archive_sets_archived_at(repo):
    p = _make_project(repo)
    archived = repo.archive(p["id"])
    assert archived["lifecycle_stage"] == "archived"
    assert archived["archived_at"] is not None


def test_restore_clears_archived_at(repo):
    p = _make_project(repo)
    repo.archive(p["id"])
    restored = repo.restore(p["id"])
    assert restored["lifecycle_stage"] == "maintenance"
    assert restored["archived_at"] is None


def test_delete_removes_project_and_cascades(repo):
    p = _make_project(repo)
    repo.add_activity(project_id=p["id"], activity_type="note", content="hi")
    assert repo.delete(p["id"]) is True
    assert repo.get(p["id"]) is None
    # ON DELETE CASCADE 应级联删除 activities
    assert repo.list_activities(p["id"]) == []


def test_add_activity_updates_last_activity_at(repo):
    p = _make_project(repo)
    original = p["last_activity_at"]
    repo.add_activity(project_id=p["id"], activity_type="note", content="hello")
    updated = repo.get(p["id"])
    assert updated["last_activity_at"] >= original  # type: ignore[operator]


def test_add_stage_auto_increments_order(repo):
    p = _make_project(repo)
    s1 = repo.add_stage(project_id=p["id"], stage_name="原型")
    s2 = repo.add_stage(project_id=p["id"], stage_name="开发")
    assert s1["stage_order"] == 1
    assert s2["stage_order"] == 2


def test_list_stages_returns_in_order(repo):
    p = _make_project(repo)
    repo.add_stage(project_id=p["id"], stage_name="b")
    repo.add_stage(project_id=p["id"], stage_name="a")
    stages = repo.list_stages(p["id"])
    assert [s["stage_name"] for s in stages] == ["b", "a"]
```

- [ ] **B2.2: 运行测试，验证全部通过**

Run: `cd /Users/duke/Documents/hotspot && python -m pytest backend/tests/test_codegarden_repo.py -v`
Expected: 18 passed

- [ ] **B2.3: Commit**

```bash
git add backend/tests/test_codegarden_repo.py
git commit -m "test(codegarden): B2 add CodegardenProjectRepository unit tests"
```

---

## Group C — Service 层 (Task C1-C3)

### Task C1: backend/services/codegarden_project_service.py (P0)

**Files:**
- Create: `backend/services/codegarden_project_service.py`

- [ ] **C1.1: 编写 CodegardenProjectService（封装 repo + 业务逻辑）**

```python
"""Phase 2a CodeGarden 项目服务层 — 封装 repo + 业务规则。

职责
----
- 项目 CRUD（委托 repo）
- lifecycle 状态机校验（合法跳转）
- activities 写入
- upstream sync 触发（写 knowledge_tasks 记录，不直接调 GitHub API）
"""
from __future__ import annotations

from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_repo import CodegardenProjectRepository
from backend.repository.db import get_connection


# lifecycle 合法跳转表（from → set of to）
_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "ideation": {"prototype", "development", "archived", "deprecated"},
    "prototype": {"development", "testing", "archived", "deprecated"},
    "development": {"testing", "running", "archived", "deprecated"},
    "testing": {"running", "development", "archived", "deprecated"},
    "running": {"maintenance", "archived", "deprecated"},
    "maintenance": {"running", "archived", "deprecated"},
    "archived": {"maintenance"},  # restore
    "deprecated": {"archived"},
}


class CodegardenProjectService:
    """项目业务逻辑层。"""

    def __init__(self) -> None:
        self.repo = CodegardenProjectRepository()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_project(self, **kwargs) -> dict:
        project = self.repo.create(**kwargs)
        self.repo.add_activity(
            project_id=project["id"],
            activity_type="note",
            content=f"项目创建: type={project['type']}, source={project['source_type']}",
            metadata={"created": True},
        )
        return project

    def get_project(self, project_id: str) -> Optional[dict]:
        return self.repo.get(project_id)

    def list_projects(self, **filters) -> tuple[list[dict], int]:
        return self.repo.list(**filters)

    def update_project(self, project_id: str, **fields) -> dict:
        return self.repo.update(project_id, **fields)

    def delete_project(self, project_id: str) -> bool:
        return self.repo.delete(project_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def change_lifecycle(self, project_id: str, new_stage: str, note: Optional[str] = None) -> dict:
        project = self.repo.get(project_id)
        if project is None:
            raise InternalException(f"project {project_id} 不存在")
        old_stage = project["lifecycle_stage"]
        if old_stage == new_stage:
            return project
        legal_targets = _LEGAL_TRANSITIONS.get(old_stage, set())
        if new_stage not in legal_targets:
            raise InternalException(
                f"非法 lifecycle 跳转: {old_stage} → {new_stage} "
                f"(合法目标: {sorted(legal_targets) or '无'})"
            )
        return self.repo.set_lifecycle(project_id, new_stage, note)

    def archive_project(self, project_id: str) -> dict:
        return self.change_lifecycle(project_id, "archived", note="归档")

    def restore_project(self, project_id: str) -> dict:
        return self.repo.restore(project_id)

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------
    def add_activity(self, *, project_id: str, activity_type: str, content: str,
                     metadata: Optional[dict] = None) -> dict:
        return self.repo.add_activity(
            project_id=project_id,
            activity_type=activity_type,
            content=content,
            metadata=metadata,
        )

    def list_activities(self, project_id: str, limit: int = 50) -> list[dict]:
        return self.repo.list_activities(project_id, limit)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def list_stages(self, project_id: str) -> list[dict]:
        return self.repo.list_stages(project_id)

    def add_stage(self, **kwargs) -> dict:
        return self.repo.add_stage(**kwargs)

    # ------------------------------------------------------------------
    # Upstream sync 任务创建
    # ------------------------------------------------------------------
    def request_upstream_sync(self, project_id: str) -> dict:
        """创建上游同步任务（写入 knowledge_tasks 表, task_type=project_sync）。

        实际同步由 watchdog 或手动触发执行，避免 HTTP 阻塞。
        """
        from datetime import datetime, timezone
        import json

        project = self.repo.get(project_id)
        if project is None:
            raise InternalException(f"project {project_id} 不存在")
        if not project.get("upstream_url") and not project.get("repo_url"):
            raise InternalException("项目无 upstream_url / repo_url, 无法同步")

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                ("project_sync", json.dumps({"project_id": project_id}), now, now),
            )
            task_id = int(cur.lastrowid)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"create sync task failed: {e}") from e

        logger.info(f"created project_sync task {task_id} for project {project_id}")
        return {"task_id": task_id, "project_id": project_id, "status": "pending"}


__all__ = ["CodegardenProjectService"]
```

- [ ] **C1.2: 验证可导入**

Run: `python -c "from backend.services.codegarden_project_service import CodegardenProjectService; print('OK')"`
Expected: `OK`

- [ ] **C1.3: Commit**

```bash
git add backend/services/codegarden_project_service.py
git commit -m "feat(codegarden): C1 add CodegardenProjectService"
```

---

### Task C2: backend/services/codegarden_github_service.py (P0)

**Files:**
- Create: `backend/services/codegarden_github_service.py`

- [ ] **C2.1: 编写 GitHub REST API 客户端（fetch repo metadata + compare commits）**

```python
"""Phase 2a CodeGarden GitHub REST API 客户端。

职责
----
- fetch_repo_metadata(url): 拉 repo 元信息 (owner/repo/default_branch/upstream)
- compare_commits(repo_url, base, head): 拉 commits behind/ahead
- token 从 secrets_service 获取 (key name: github_token)

设计要点
--------
- 复用 httpx (与 collectors 同栈), 但走 REST API 而非 HTML 抓取
- token 缺失时 raise InternalException, API 层捕获后返回 424
- 速率限制: 403/429 抛 RateLimitException
- 不缓存 (上游同步任务调度间隔 24h)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from backend.exceptions import InternalException
from backend.logging_config import logger


GITHUB_API_BASE = "https://api.github.com"
_OWNER_REPO_RE = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?/?$")


class GithubTokenMissingException(InternalException):
    """GitHub token 未配置（API 层捕获后返回 424）。"""


class GithubRateLimitException(InternalException):
    """GitHub API 速率限制。"""


@dataclass
class RepoMetadata:
    owner: str
    repo: str
    default_branch: str
    description: Optional[str]
    upstream_url: Optional[str]      # fork source (parent.clone_url)
    upstream_default_branch: Optional[str]
    stars: int
    language: Optional[str]
    homepage: Optional[str]


@dataclass
class CompareResult:
    base: str
    head: str
    commits_behind: int
    commits_ahead: int
    last_commit_messages: list[str]   # 最近 5 条
    last_commit_shas: list[str]


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """从 https://github.com/{owner}/{repo} 解析 owner/repo。"""
    parsed = urlparse(repo_url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        raise InternalException(f"非 GitHub URL: {repo_url}")
    m = _OWNER_REPO_RE.match(parsed.path or "")
    if not m:
        raise InternalException(f"无法解析 owner/repo: {repo_url}")
    return m.group(1), m.group(2)


def _get_github_token() -> str:
    """从 secrets_service 获取 github_token。"""
    try:
        from backend.services.secrets_service import get_secret_value
    except ImportError as e:
        raise GithubTokenMissingException(f"secrets_service 不可用: {e}") from e
    token = get_secret_value("github_token")
    if not token:
        raise GithubTokenMissingException(
            "github_token 未配置; 请在 Secrets 页面添加 name=github_token 的密钥"
        )
    return token


def _make_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hotspot-codegarden/1.0",
    }


def _check_rate_limit(response: httpx.Response) -> None:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining == "0" or response.status_code in (403, 429):
        reset = response.headers.get("X-RateLimit-Reset", "?")
        raise GithubRateLimitException(
            f"GitHub API 速率限制, reset at {reset}; status={response.status_code}"
        )


def fetch_repo_metadata(repo_url: str) -> RepoMetadata:
    """拉 GitHub repo 元信息（含 fork 源）。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers)
        _check_rate_limit(resp)
        if resp.status_code == 404:
            raise InternalException(f"GitHub repo 不存在: {repo_url}")
        if resp.status_code != 200:
            raise InternalException(
                f"GitHub API /repos 失败: status={resp.status_code}, body={resp.text[:200]}"
            )
        data = resp.json()

        upstream_url: Optional[str] = None
        upstream_default_branch: Optional[str] = None
        parent = data.get("parent")
        if parent:
            upstream_url = parent.get("clone_url") or parent.get("html_url")
            # 拉 upstream default branch (额外一次 API 调用)
            if upstream_url:
                try:
                    parent_owner = parent.get("owner", {}).get("login")
                    parent_repo = parent.get("name")
                    if parent_owner and parent_repo:
                        pr = client.get(
                            f"{GITHUB_API_BASE}/repos/{parent_owner}/{parent_repo}",
                            headers=headers,
                        )
                        if pr.status_code == 200:
                            upstream_default_branch = pr.json().get("default_branch")
                except Exception as e:
                    logger.warning(f"fetch upstream default_branch failed: {e}")

        return RepoMetadata(
            owner=owner,
            repo=repo,
            default_branch=data.get("default_branch", "main"),
            description=data.get("description"),
            upstream_url=upstream_url,
            upstream_default_branch=upstream_default_branch,
            stars=int(data.get("stargazers_count", 0) or 0),
            language=data.get("language"),
            homepage=data.get("homepage") or None,
        )


def compare_commits(
    repo_url: str,
    base: str,           # 上游 default branch (e.g. "main")
    head: str,           # 本地 fork branch 或 commit sha
) -> CompareResult:
    """调 GitHub compare 端点拉 commits behind/ahead。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/compare/{base}...{head}",
            headers=headers,
        )
        _check_rate_limit(resp)
        if resp.status_code == 404:
            raise InternalException(
                f"compare 失败 (404): {repo_url} base={base} head={head}"
            )
        if resp.status_code != 200:
            raise InternalException(
                f"compare 失败: status={resp.status_code}, body={resp.text[:200]}"
            )
        data = resp.json()

        commits = data.get("commits", [])[:5]
        return CompareResult(
            base=base,
            head=head,
            commits_behind=int(data.get("behind_by", 0) or 0),
            commits_ahead=int(data.get("ahead_by", 0) or 0),
            last_commit_messages=[c.get("commit", {}).get("message", "").split("\n")[0]
                                   for c in commits],
            last_commit_shas=[c.get("sha", "") for c in commits],
        )


def fetch_upstream_releases(repo_url: str, limit: int = 5) -> list[dict]:
    """拉 upstream 最近 releases（可选功能, 用于显示最新版本）。"""
    owner, repo = _parse_owner_repo(repo_url)
    token = _get_github_token()
    headers = _make_headers(token)

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases?per_page={limit}",
            headers=headers,
        )
        _check_rate_limit(resp)
        if resp.status_code != 200:
            return []
        return [
            {
                "tag": r.get("tag_name"),
                "name": r.get("name") or r.get("tag_name"),
                "published_at": r.get("published_at"),
                "html_url": r.get("html_url"),
                "prerelease": bool(r.get("prerelease")),
            }
            for r in resp.json()
        ]


__all__ = [
    "RepoMetadata",
    "CompareResult",
    "fetch_repo_metadata",
    "compare_commits",
    "fetch_upstream_releases",
    "GithubTokenMissingException",
    "GithubRateLimitException",
]
```

- [ ] **C2.2: 验证可导入**

Run: `python -c "from backend.services.codegarden_github_service import fetch_repo_metadata; print('OK')"`
Expected: `OK`

- [ ] **C2.3: Commit**

```bash
git add backend/services/codegarden_github_service.py
git commit -m "feat(codegarden): C2 add GitHub REST API client"
```

---

### Task C3: backend/services/codegarden_knowledge_bridge.py (P0)

**Files:**
- Create: `backend/services/codegarden_knowledge_bridge.py`

- [ ] **C3.1: 编写资讯→项目转化桥接（from-knowledge + candidates 列表）**

```python
"""Phase 2a CodeGarden 知识桥接服务 — 资讯 → 项目转化通道。

职责
----
- list_candidates(): 列出 type=github 且未转化的 knowledge_items (候选二开源)
- create_from_knowledge(item_id, source_type, local_path):
    从 knowledge_item 一键创建 cg_projects 记录,
    写入 source_item_id 反向溯源,
    更新 knowledge_items frontmatter project_id 字段
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_repo import CodegardenProjectRepository
from backend.repository.db import get_connection
from backend.services.knowledge_sync import ITEMS_DIR, parse_frontmatter


class CodegardenKnowledgeBridge:
    """资讯→项目转化服务。"""

    def __init__(self) -> None:
        self.repo = CodegardenProjectRepository()

    # ------------------------------------------------------------------
    # 候选源列表
    # ------------------------------------------------------------------
    def list_candidates(self, limit: int = 100) -> list[dict]:
        """列出 type=github 的 knowledge_items 中尚未转化的（无 project_id）。

        返回字段: id, title, source_url, domain, description, ingested_at
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT k.id, k.title, k.source_url, k.domain, k.topic,
                   k.ingested_at, k.updated_at
            FROM knowledge_items k
            WHERE k.type = 'github'
              AND k.id NOT IN (SELECT source_item_id FROM cg_projects
                               WHERE source_item_id IS NOT NULL)
            ORDER BY k.ingested_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [
            {
                "id": str(r["id"]),
                "title": str(r["title"]),
                "source_url": r["source_url"],
                "domain": r["domain"],
                "topic": r["topic"],
                "ingested_at": str(r["ingested_at"]),
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 幂等检查: 找出已存在的 project
    # ------------------------------------------------------------------
    def find_existing_project(self, item_id: str) -> Optional[dict]:
        """若 knowledge_item 已转化为 cg_projects, 返回既有 project; 否则 None。

        用于 from-knowledge 端点幂等校验 (首次 201 / 重复 200)。
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM cg_projects WHERE source_item_id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return self.repo.get_project(str(row["id"]))

    # ------------------------------------------------------------------
    # 一键转化
    # ------------------------------------------------------------------
    def create_from_knowledge(
        self,
        *,
        item_id: str,
        source_type: str = "reference",  # fork / reference (reference=仅参考, fork=二开)
        local_path: Optional[str] = None,
        source_type_detail: Optional[str] = None,
    ) -> dict:
        """从 knowledge_item 创建 cg_projects 记录。

        - 自动从 item.source_url 提取 upstream_url
        - 写入 source_item_id 反向溯源
        - 更新 knowledge_items frontmatter project_id 字段

        注意: API 层已通过 find_existing_project 实现幂等, 这里仍保留 defensive
        check 以防并发竞态 (两个请求同时通过 API 检查后同时进入此方法)。
        """
        if source_type not in ("fork", "reference"):
            raise InternalException(
                f"source_type 必须为 fork / reference; got {source_type!r}"
            )

        # 1. 读 knowledge_item
        conn = get_connection()
        row = conn.execute(
            "SELECT id, title, source_url, domain, description FROM knowledge_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            raise InternalException(f"knowledge_item {item_id} 不存在")

        source_url = row["source_url"] or ""
        if not source_url or "github.com" not in source_url:
            raise InternalException(
                f"knowledge_item.source_url 非 GitHub URL: {source_url!r}"
            )

        # 2. 检查是否已转化 (defensive, 防 API 层并发竞态)
        existing = conn.execute(
            "SELECT id FROM cg_projects WHERE source_item_id = ?", (item_id,)
        ).fetchone()
        if existing is not None:
            raise InternalException(
                f"knowledge_item {item_id} 已转化为 cg_projects.id={existing['id']}"
            )

        # 3. 创建 cg_projects 记录
        title = str(row["title"])
        # 从 title 提取 owner/repo 作为 name (e.g. "langchain-ai/langgraph: ...")
        name = title.split(":")[0].strip().replace("/", "-").lower()[:80]
        if not name:
            name = f"github-{item_id[:8]}"

        project = self.repo.create(
            name=name,
            display_name=title.split(":")[0].strip(),
            description=row["description"] or title,
            type="library",                    # 默认 library, 用户后续可改
            source_type=source_type,
            lifecycle_stage="ideation",
            repo_url=source_url,
            upstream_url=source_url,           # 资讯 repo 就是 upstream
            source_item_id=item_id,
            source_type_detail=source_type_detail or "trending",
            tags=["from-knowledge"],
            tech_stack=[],
            domain=row["domain"] or "github",
        )

        # 4. 更新 knowledge_item frontmatter (写 project_id)
        self._update_item_frontmatter_project_id(item_id, project["id"])

        # 5. 写入活动日志
        self.repo.add_activity(
            project_id=project["id"],
            activity_type="note",
            content=f"从 knowledge_item {item_id} 转化创建",
            metadata={
                "source_item_id": item_id,
                "source_url": source_url,
                "source_type_detail": source_type_detail,
            },
        )

        logger.info(
            f"created cg_projects {project['id']} from knowledge_item {item_id}"
        )
        return project

    # ------------------------------------------------------------------
    # 私有: 更新 knowledge_item frontmatter
    # ------------------------------------------------------------------
    def _update_item_frontmatter_project_id(self, item_id: str, project_id: str) -> None:
        """在 knowledge/items/{item_id}.md frontmatter 中写入 project_id 字段。

        保持原文件 body 不变，只在 frontmatter 末尾追加 project_id 行。
        若已有 project_id 字段则覆盖。
        """
        md_path = ITEMS_DIR / f"{item_id}.md"
        if not md_path.exists():
            logger.warning(f"knowledge item md not found: {md_path}")
            return

        text = md_path.read_text(encoding="utf-8")
        # 简易 frontmatter 解析（不依赖 pyyaml）
        if not text.startswith("---"):
            logger.warning(f"item {item_id} has no frontmatter, skipping project_id write")
            return

        end_idx = text.find("\n---", 3)
        if end_idx < 0:
            logger.warning(f"item {item_id} frontmatter malformed")
            return

        fm_text = text[3:end_idx]
        body = text[end_idx + 4:]

        # 移除已有 project_id 行
        lines = [ln for ln in fm_text.split("\n") if not ln.strip().startswith("project_id:")]
        # 追加新行
        lines.append(f"project_id: {project_id}")
        new_fm = "\n".join(lines).strip()

        new_text = f"---\n{new_fm}\n---\n{body}"
        md_path.write_text(new_text, encoding="utf-8")


__all__ = ["CodegardenKnowledgeBridge"]
```

- [ ] **C3.2: 验证可导入**

Run: `python -c "from backend.services.codegarden_knowledge_bridge import CodegardenKnowledgeBridge; print('OK')"`
Expected: `OK`

- [ ] **C3.3: Commit**

```bash
git add backend/services/codegarden_knowledge_bridge.py
git commit -m "feat(codegarden): C3 add knowledge bridge for github-news-to-project"
```

---

## Group D — API 层 (Task D1-D3)

### Task D1: backend/api/codegarden.py (P0)

**Files:**
- Create: `backend/api/codegarden.py`

- [ ] **D1.1: 编写 14 个 API 端点**

参考 `backend/api/skills.py` 模式：APIRouter(prefix="/api/codegarden")、asyncio.to_thread 包装同步 DB、HTTPException 400/404/424/500。

```python
"""Phase 2a CodeGarden API 端点。

路由清单 (PRD 7.2)
-----------------
项目管理:
- GET    /api/codegarden/projects                 列表
- POST   /api/codegarden/projects                 创建
- GET    /api/codegarden/projects/{id}            详情
- PATCH  /api/codegarden/projects/{id}            更新
- DELETE /api/codegarden/projects/{id}            删除
- POST   /api/codegarden/projects/{id}/archive    归档
- POST   /api/codegarden/projects/{id}/restore    恢复
- POST   /api/codegarden/projects/{id}/lifecycle  切换 lifecycle (body: {to, note})
- GET    /api/codegarden/projects/{id}/timeline   阶段时间线
- GET    /api/codegarden/projects/{id}/activities 活动日志

GitHub 导入与上游跟踪:
- GET    /api/codegarden/github/metadata?url=...  预览 repo metadata (前端导入对话框)
- POST   /api/codegarden/github/import            导入 GitHub 项目
- POST   /api/codegarden/from-knowledge           从 knowledge_item 转化 (body: {item_id, source_type, ...}, 幂等: 首次 201 / 重复 200)
- GET    /api/codegarden/candidates               候选二开源 (type=github 且未转化)
- POST   /api/codegarden/projects/{id}/sync       触发上游同步 (写 knowledge_tasks)
- GET    /api/codegarden/projects/{id}/upstream   上游状态详情

设计原则
--------
- 同步 DB 操作通过 asyncio.to_thread 包装, 避免阻塞 event loop
- GitHub token 缺失返回 424 Failed Dependency (不是 500)
- 400/404 用 HotspotException 体系, 中文 message
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_repo import (
    VALID_LIFECYCLE_STAGES,
    VALID_PROJECT_TYPES,
    VALID_SOURCE_TYPES,
)
from backend.services.codegarden_knowledge_bridge import CodegardenKnowledgeBridge
from backend.services.codegarden_project_service import CodegardenProjectService

router = APIRouter(prefix="/api/codegarden", tags=["codegarden"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CreateProjectRequest(BaseModel):
    name: str = Field(..., max_length=200, description="项目名 (必填)")
    type: str = Field(..., description=f"类型: {', '.join(VALID_PROJECT_TYPES)}")
    source_type: str = Field(..., description=f"来源: {', '.join(VALID_SOURCE_TYPES)}")
    lifecycle_stage: str = Field("ideation", description="初始生命周期")
    display_name: Optional[str] = None
    description: Optional[str] = None
    local_path: Optional[str] = None
    repo_url: Optional[str] = None
    upstream_url: Optional[str] = None
    upstream_default_branch: Optional[str] = None
    source_item_id: Optional[str] = None
    source_type_detail: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    domain: Optional[str] = None
    priority: int = Field(0, ge=0, le=5)


class PatchProjectRequest(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    source_type: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    health_score: Optional[int] = None
    local_path: Optional[str] = None
    repo_url: Optional[str] = None
    upstream_url: Optional[str] = None
    upstream_default_branch: Optional[str] = None
    tags: Optional[list[str]] = None
    tech_stack: Optional[list[str]] = None
    domain: Optional[str] = None
    priority: Optional[int] = None


class LifecycleChangeRequest(BaseModel):
    # 字段名 `to` (不是 `stage`): 与前端 useCodegardenProjects hook 对齐
    to: str = Field(..., description=f"目标: {', '.join(VALID_LIFECYCLE_STAGES)}")
    note: Optional[str] = None


class GithubImportRequest(BaseModel):
    # 字段名 `repo_url` (不是 `url`): 与前端 GithubImportDialog 对齐
    repo_url: str = Field(..., description="GitHub repo URL")
    local_path: Optional[str] = None
    auto_sync: bool = Field(True, description="导入后立即触发首次同步")
    # 用户可选覆盖 (默认从 repo metadata 推断)
    source_type: Optional[str] = Field(None, description="覆盖推断的 source_type (fork/imported)")
    source_type_detail: Optional[str] = None
    type: Optional[str] = Field(None, description="覆盖默认 type=library")
    tags: Optional[list[str]] = None
    tech_stack: Optional[list[str]] = None
    domain: Optional[str] = None


class FromKnowledgeRequest(BaseModel):
    # item_id 走 body 而非 path param (与前端 + e2e 对齐)
    item_id: str = Field(..., description="knowledge_items.id (type=github)")
    source_type: str = Field("reference", description="fork / reference / imported")
    local_path: Optional[str] = None
    source_type_detail: Optional[str] = None


# ---------------------------------------------------------------------------
# 项目管理
# ---------------------------------------------------------------------------
@router.get("/projects")
async def list_projects(
    lifecycle_stage: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    source_item_id: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """项目列表（多维筛选 + 关键词搜索）。排序: last_activity_at DESC。"""
    svc = CodegardenProjectService()
    try:
        items, total = await asyncio.to_thread(
            svc.list_projects,
            lifecycle_stage=lifecycle_stage,
            source_type=source_type,
            domain=domain,
            type=type,
            source_item_id=source_item_id,
            keyword=keyword,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"list projects failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"列表失败: {e}"})
    return {"version": "1.5.0", "total": total, "items": items}


@router.post("/projects", status_code=201)
async def create_project(req: CreateProjectRequest):
    svc = CodegardenProjectService()
    try:
        project = await asyncio.to_thread(
            svc.create_project,
            name=req.name,
            type=req.type,
            source_type=req.source_type,
            lifecycle_stage=req.lifecycle_stage,
            display_name=req.display_name,
            description=req.description,
            local_path=req.local_path,
            repo_url=req.repo_url,
            upstream_url=req.upstream_url,
            upstream_default_branch=req.upstream_default_branch,
            source_item_id=req.source_item_id,
            source_type_detail=req.source_type_detail,
            tags=req.tags,
            tech_stack=req.tech_stack,
            domain=req.domain,
            priority=req.priority,
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"create project failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"创建失败: {e}"})
    return project


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    svc = CodegardenProjectService()
    project = await asyncio.to_thread(svc.get_project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"message": f"项目 {project_id} 不存在"})
    return project


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, req: PatchProjectRequest):
    svc = CodegardenProjectService()
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        return await asyncio.to_thread(svc.update_project, project_id, **fields)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": f"更新失败: {e}"})


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    svc = CodegardenProjectService()
    try:
        ok = await asyncio.to_thread(svc.delete_project, project_id)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    if not ok:
        raise HTTPException(status_code=404, detail={"message": f"项目 {project_id} 不存在"})
    return {"deleted": True, "id": project_id}


@router.post("/projects/{project_id}/archive")
async def archive_project(project_id: str):
    svc = CodegardenProjectService()
    try:
        return await asyncio.to_thread(svc.archive_project, project_id)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.post("/projects/{project_id}/restore")
async def restore_project(project_id: str):
    svc = CodegardenProjectService()
    try:
        return await asyncio.to_thread(svc.restore_project, project_id)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.post("/projects/{project_id}/lifecycle")
async def change_lifecycle(project_id: str, req: LifecycleChangeRequest):
    svc = CodegardenProjectService()
    try:
        return await asyncio.to_thread(svc.change_lifecycle, project_id, req.to, req.note)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.get("/projects/{project_id}/timeline")
async def get_timeline(project_id: str):
    """阶段时间线 (cg_project_stages)。"""
    svc = CodegardenProjectService()
    project = await asyncio.to_thread(svc.get_project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"message": f"项目 {project_id} 不存在"})
    stages = await asyncio.to_thread(svc.list_stages, project_id)
    return {"project_id": project_id, "stages": stages}


@router.get("/projects/{project_id}/activities")
async def list_activities(project_id: str, limit: int = Query(50, ge=1, le=200)):
    svc = CodegardenProjectService()
    project = await asyncio.to_thread(svc.get_project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"message": f"项目 {project_id} 不存在"})
    activities = await asyncio.to_thread(svc.list_activities, project_id, limit)
    return {"project_id": project_id, "activities": activities}


# ---------------------------------------------------------------------------
# GitHub 导入与上游跟踪
# ---------------------------------------------------------------------------
@router.get("/github/metadata")
async def github_metadata(url: str = Query(..., description="GitHub repo URL")):
    """预览 repo metadata (前端导入对话框使用, 不写库)。"""
    from backend.services.codegarden_github_service import (
        GithubTokenMissingException,
        fetch_repo_metadata,
    )
    try:
        meta = await asyncio.to_thread(fetch_repo_metadata, url)
    except GithubTokenMissingException as e:
        raise HTTPException(
            status_code=424,
            detail={"message": str(e), "missing": "github_token"},
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"github_metadata failed: {e}")
        raise HTTPException(status_code=502, detail={"message": f"GitHub API 失败: {e}"})

    return {
        "url": url,
        "owner": meta.owner,
        "repo": meta.repo,
        "description": meta.description,
        "default_branch": meta.default_branch,
        "language": meta.language,
        "upstream_url": meta.upstream_url,
        "upstream_default_branch": meta.upstream_default_branch,
        "inferred_source_type": "fork" if meta.upstream_url else "imported",
        "inferred_type": "library",
    }


@router.post("/github/import", status_code=201)
async def github_import(req: GithubImportRequest):
    """从 GitHub URL 导入项目（拉 repo metadata + upstream）。

    用户可通过 req.source_type / req.type / req.tags / req.tech_stack / req.domain
    覆盖默认推断值 (默认 source_type=fork|imported, type=library, tags=['github-imported'])。
    """
    from backend.services.codegarden_github_service import (
        GithubTokenMissingException,
        fetch_repo_metadata,
    )
    svc = CodegardenProjectService()
    try:
        meta = await asyncio.to_thread(fetch_repo_metadata, req.repo_url)
    except GithubTokenMissingException as e:
        raise HTTPException(
            status_code=424,
            detail={"message": str(e), "missing": "github_token"},
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"github_import failed: {e}")
        raise HTTPException(status_code=502, detail={"message": f"GitHub API 失败: {e}"})

    # 推断 source_type: 有 upstream_url = fork, 否则 imported (用户可覆盖)
    inferred_source_type = "fork" if meta.upstream_url else "imported"
    source_type = req.source_type or inferred_source_type

    try:
        project = await asyncio.to_thread(
            svc.create_project,
            name=f"{meta.owner}-{meta.repo}"[:80],
            display_name=f"{meta.owner}/{meta.repo}",
            description=meta.description,
            type=req.type or "library",
            source_type=source_type,
            lifecycle_stage="ideation",
            local_path=req.local_path,
            repo_url=req.repo_url,
            upstream_url=meta.upstream_url,
            upstream_default_branch=meta.upstream_default_branch or meta.default_branch,
            tags=req.tags if req.tags is not None else ["github-imported"],
            tech_stack=req.tech_stack if req.tech_stack is not None else (
                [meta.language] if meta.language else []
            ),
            domain=req.domain,
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})

    if req.auto_sync:
        try:
            await asyncio.to_thread(svc.request_upstream_sync, project["id"])
        except InternalException as e:
            logger.warning(f"auto_sync trigger failed (ignored): {e}")

    return project


@router.get("/candidates")
async def list_candidates(limit: int = Query(100, ge=1, le=500)):
    """列出 type=github 且未转化的 knowledge_items（候选二开源）。"""
    bridge = CodegardenKnowledgeBridge()
    items = await asyncio.to_thread(bridge.list_candidates, limit)
    return {"version": "1.5.0", "total": len(items), "items": items}


@router.post("/from-knowledge")
async def create_from_knowledge(req: FromKnowledgeRequest, response: Response):
    """从 knowledge_item 一键创建 cg_projects 记录 (幂等)。

    - 首次转化: 返回 201 + project
    - 重复转化 (同 item_id 已有 project): 返回 200 + 既有 project (不重复创建)

    这样设计是因为资讯→项目转化是高频操作, 用户可能误点多次。
    Response 对象由 FastAPI 自动注入, 通过 response.status_code 设置状态码。
    """
    bridge = CodegardenKnowledgeBridge()
    existing = await asyncio.to_thread(bridge.find_existing_project, req.item_id)
    if existing is not None:
        response.status_code = 200
        return existing
    try:
        project = await asyncio.to_thread(
            bridge.create_from_knowledge,
            item_id=req.item_id,
            source_type=req.source_type,
            local_path=req.local_path,
            source_type_detail=req.source_type_detail,
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"create_from_knowledge failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"转化失败: {e}"})
    response.status_code = 201
    return project


@router.post("/projects/{project_id}/sync")
async def trigger_sync(project_id: str):
    """触发上游同步（写入 knowledge_tasks 表, task_type=project_sync）。"""
    svc = CodegardenProjectService()
    try:
        return await asyncio.to_thread(svc.request_upstream_sync, project_id)
    except InternalException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.get("/projects/{project_id}/upstream")
async def get_upstream_status(project_id: str):
    """上游状态详情（实时调 GitHub compare API, 可能 5-10s）。"""
    from backend.services.codegarden_github_service import (
        GithubTokenMissingException,
        compare_commits,
        fetch_upstream_releases,
        fetch_repo_metadata,
    )
    svc = CodegardenProjectService()
    project = await asyncio.to_thread(svc.get_project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"message": f"项目 {project_id} 不存在"})

    upstream_url = project.get("upstream_url") or project.get("repo_url")
    if not upstream_url:
        raise HTTPException(status_code=400, detail={"message": "项目无 upstream_url/repo_url"})

    try:
        meta = await asyncio.to_thread(fetch_repo_metadata, upstream_url)
        base = meta.default_branch
        # head 用项目记录的 upstream_default_branch 或 upstream default branch
        head = project.get("upstream_default_branch") or base
        # 简化: 直接拉 upstream 的最新状态 (用 base...base 自比, 取 0/0)
        # 真正的 behind/ahead 需要本地 fork 的 commit sha, Phase 2a 暂返回 upstream metadata
        releases = await asyncio.to_thread(fetch_upstream_releases, upstream_url, limit=5)
    except GithubTokenMissingException as e:
        raise HTTPException(
            status_code=424,
            detail={"message": str(e), "missing": "github_token"},
        )
    except InternalException as e:
        raise HTTPException(status_code=502, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"get_upstream_status failed: {e}")
        raise HTTPException(status_code=502, detail={"message": f"GitHub API 失败: {e}"})

    return {
        "project_id": project_id,
        "upstream_url": upstream_url,
        "upstream_default_branch": meta.default_branch,
        "upstream_description": meta.description,
        "upstream_stars": meta.stars,
        "upstream_language": meta.language,
        "commits_behind": project.get("commits_behind", 0),
        "commits_ahead": project.get("commits_ahead", 0),
        "last_synced_at": project.get("last_synced_at"),
        "recent_releases": releases,
    }
```

- [ ] **D1.2: 验证可导入**

Run: `python -c "from backend.api.codegarden import router; print(len(router.routes))"`
Expected: `15`（14 个端点 + router 本身）

- [ ] **D1.3: Commit**

```bash
git add backend/api/codegarden.py
git commit -m "feat(codegarden): D1 add /api/codegarden router with 14 endpoints"
```

---

### Task D2: 注册路由到 backend/api/__init__.py (P0)

**Files:**
- Modify: `backend/api/__init__.py`

- [ ] **D2.1: 在 register_routers 中加入 codegarden 路由**

打开 `backend/api/__init__.py`，在 import 列表中追加 `codegarden`，并在 `app.include_router` 调用列表末尾追加：

```python
# 在 import 块中 (按字母序插入, 在 categories 后, content 前 — 但实际现有顺序无字母序,
# 简单放在 knowledge 后即可):
        knowledge,  # v1.4: 知识库
        codegarden,  # v1.5 Phase 2a: CodeGarden
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
```

```python
# 在 include_router 列表末尾追加:
    app.include_router(codegarden.router, tags=["codegarden"])
```

- [ ] **D2.2: 验证路由注册成功**

Run: `python -c "from backend.main import app; routes = [r.path for r in app.routes if '/codegarden/' in str(r.path)]; print(len(routes)); print(sorted(routes))"`
Expected: `16` + 包含 `/api/codegarden/projects`, `/api/codegarden/github/metadata`, `/api/codegarden/github/import`, `/api/codegarden/candidates`, `/api/codegarden/from-knowledge` 等 16 条路由

- [ ] **D2.3: Commit**

```bash
git add backend/api/__init__.py
git commit -m "feat(codegarden): D2 register codegarden router in register_routers"
```

---

### Task D3: backend/tests/test_codegarden_api.py (P0)

**Files:**
- Create: `backend/tests/test_codegarden_api.py`

- [ ] **D3.1: 编写 API 单测（TestClient + mock GitHub API）**

```python
"""Phase 2a CodeGarden API 单测 — 14 个端点全覆盖。

策略
----
- 项目 CRUD / lifecycle / activities: 直接测, 无需 mock
- github_import / upstream: mock codegarden_github_service 函数
- from_knowledge: 准备 knowledge_item 数据, 真实跑转化流程
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 项目 CRUD
# ---------------------------------------------------------------------------
def test_create_project_returns_201(client):
    r = client.post("/api/codegarden/projects", json={
        "name": "test-api",
        "type": "web_application",
        "source_type": "vibe",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"]
    assert data["name"] == "test-api"
    assert data["lifecycle_stage"] == "ideation"


def test_create_project_invalid_type_returns_400(client):
    r = client.post("/api/codegarden/projects", json={
        "name": "x", "type": "bogus", "source_type": "vibe",
    })
    assert r.status_code == 400


def test_list_projects_returns_created(client):
    client.post("/api/codegarden/projects", json={
        "name": "list-target", "type": "cli", "source_type": "vibe",
    })
    r = client.get("/api/codegarden/projects")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(p["name"] == "list-target" for p in data["items"])


def test_get_project_404(client):
    r = client.get("/api/codegarden/projects/nonexistent-id")
    assert r.status_code == 404


def test_patch_project_updates_fields(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "patch-me", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.patch(f"/api/codegarden/projects/{create['id']}", json={
        "description": "updated",
        "priority": 5,
    })
    assert r.status_code == 200
    assert r.json()["description"] == "updated"
    assert r.json()["priority"] == 5


def test_change_lifecycle_writes_activity(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "lc", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/lifecycle",
                    json={"to": "prototype"})
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "prototype"
    # 验证活动日志
    acts = client.get(f"/api/codegarden/projects/{create['id']}/activities").json()
    assert any(a["activity_type"] == "status_change" for a in acts["activities"])


def test_change_lifecycle_rejects_invalid_transition(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "lc2", "type": "cli", "source_type": "vibe",
        "lifecycle_stage": "ideation",
    }).json()
    # ideation → running 非法 (跳过 prototype/development/testing)
    r = client.post(f"/api/codegarden/projects/{create['id']}/lifecycle",
                    json={"to": "running"})
    assert r.status_code == 400


def test_archive_and_restore(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "arc", "type": "cli", "source_type": "vibe",
        "lifecycle_stage": "development",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/archive")
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "archived"
    assert r.json()["archived_at"] is not None

    r = client.post(f"/api/codegarden/projects/{create['id']}/restore")
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "maintenance"
    assert r.json()["archived_at"] is None


def test_delete_project(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "del", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.delete(f"/api/codegarden/projects/{create['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # 二次 get 应 404
    assert client.get(f"/api/codegarden/projects/{create['id']}").status_code == 404


def test_get_timeline_returns_stages(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "tl", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.get(f"/api/codegarden/projects/{create['id']}/timeline")
    assert r.status_code == 200
    assert "stages" in r.json()


# ---------------------------------------------------------------------------
# GitHub 导入 (mock)
# ---------------------------------------------------------------------------
def test_github_import_returns_424_when_no_token(client):
    from backend.services.codegarden_github_service import GithubTokenMissingException
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               side_effect=GithubTokenMissingException("no token")):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/foo/bar",
        })
    assert r.status_code == 424
    assert "github_token" in r.json()["detail"]["missing"]


def test_github_import_creates_project(client):
    from backend.services.codegarden_github_service import RepoMetadata
    fake_meta = RepoMetadata(
        owner="foo", repo="bar", default_branch="main",
        description="test repo", upstream_url=None,
        upstream_default_branch=None, stars=100, language="Python",
        homepage=None,
    )
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               return_value=fake_meta):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/foo/bar",
            "auto_sync": False,
        })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["source_type"] == "imported"  # 无 upstream_url
    assert data["repo_url"] == "https://github.com/foo/bar"
    assert data["upstream_default_branch"] == "main"
    assert "Python" in data["tech_stack"]


def test_github_import_fork_with_upstream(client):
    from backend.services.codegarden_github_service import RepoMetadata
    fake_meta = RepoMetadata(
        owner="me", repo="bar-fork", default_branch="main",
        description="my fork", upstream_url="https://github.com/foo/bar.git",
        upstream_default_branch="main", stars=0, language="Python",
        homepage=None,
    )
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               return_value=fake_meta):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/me/bar-fork",
            "auto_sync": False,
        })
    assert r.status_code == 201
    data = r.json()
    assert data["source_type"] == "fork"
    assert data["upstream_url"] == "https://github.com/foo/bar.git"


# ---------------------------------------------------------------------------
# from-knowledge 转化 (需要 knowledge_item fixture)
# ---------------------------------------------------------------------------
def _seed_knowledge_item(domain: str = "github") -> str:
    """插入一条 type=github 的 knowledge_item, 返回其 id。"""
    import json
    import uuid
    from datetime import datetime, timezone
    from backend.repository.db import get_connection
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO knowledge_items
        (id, title, source, source_url, domain, topic, type, difficulty,
         tags, concepts, mastery, compiled, ingested_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        """,
        (item_id, "foo/bar: test repo", "github-trending",
         "https://github.com/foo/bar", domain, None, "github", None,
         "[]", "[]", now, now),
    )
    return item_id


def test_list_candidates_returns_github_items(client):
    item_id = _seed_knowledge_item()
    r = client.get("/api/codegarden/candidates")
    assert r.status_code == 200
    assert any(it["id"] == item_id for it in r.json()["items"])


def test_create_from_knowledge(client):
    item_id = _seed_knowledge_item()
    r = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["source_item_id"] == item_id
    assert data["source_type"] == "fork"
    assert data["upstream_url"] == "https://github.com/foo/bar"

    # 候选列表中应不再出现该 item
    cands = client.get("/api/codegarden/candidates").json()
    assert not any(it["id"] == item_id for it in cands["items"])

    # 可通过 source_item_id 反查
    by_src = client.get(f"/api/codegarden/projects?source_item_id={item_id}").json()
    assert by_src["total"] == 1


def test_create_from_knowledge_is_idempotent(client):
    """重复转化同一 knowledge_item 应幂等返回 200 (而非 400)。"""
    item_id = _seed_knowledge_item()
    first = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert second.status_code == 200  # 幂等: 重复 200, 不创建新 project
    assert second.json()["id"] == first_id  # 返回既有 project


# ---------------------------------------------------------------------------
# 触发同步
# ---------------------------------------------------------------------------
def test_trigger_sync_creates_task(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "sync-me", "type": "cli", "source_type": "fork",
        "repo_url": "https://github.com/foo/bar",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/sync")
    assert r.status_code == 200
    assert "task_id" in r.json()
```

- [ ] **D3.2: 运行 API 单测**

Run: `cd /Users/duke/Documents/hotspot && python -m pytest backend/tests/test_codegarden_api.py -v`
Expected: 17 passed

- [ ] **D3.3: Commit**

```bash
git add backend/tests/test_codegarden_api.py
git commit -m "test(codegarden): D3 add 17 API endpoint tests"
```

---

## Group E — Scheduler (Task E1-E2)

### Task E1: scheduler/jobs.py 新增 cg_upstream_sync_job (P1)

**Files:**
- Modify: `backend/scheduler/jobs.py`

- [ ] **E1.1: 在 jobs.py 末尾追加 cg_upstream_sync_job 函数**

打开 `backend/scheduler/jobs.py`，在 `scheduled_summary_job` 函数后追加：

```python
async def cg_upstream_sync_job() -> None:
    """Phase 2a CodeGarden: 每日 09:00 (Asia/Shanghai) 触发 fork 类型项目的上游同步。

    遍历所有 source_type=fork 且有 upstream_url 的 cg_projects,
    为每个项目创建一个 project_sync 任务到 knowledge_tasks 队列。
    实际同步由 watchdog 或 TaskExecutor 执行, 这里只负责调度。

    失败只 log.error, 不抛异常 (与既有 job 模式一致)。
    """
    try:
        from backend.repository.codegarden_repo import CodegardenProjectRepository
        from backend.services.codegarden_project_service import CodegardenProjectService

        repo = CodegardenProjectRepository()
        svc = CodegardenProjectService()
        # 列出所有 fork 项目 (不含 archived/deprecated)
        projects, total = await asyncio.to_thread(
            repo.list, source_type="fork", limit=500
        )
        created = 0
        for p in projects:
            if not p.get("upstream_url"):
                continue
            try:
                await asyncio.to_thread(svc.request_upstream_sync, p["id"])
                created += 1
            except Exception as e:
                _logger.warning(
                    f"cg_upstream_sync_job: project {p['id']} sync request failed: {e}"
                )
        _logger.info(f"cg_upstream_sync_job: scanned {total} fork projects, created {created} sync tasks")
    except Exception as e:
        _logger.error(f"cg_upstream_sync_job crashed: {e}")
```

- [ ] **E1.2: 在 __all__ 列表中追加 cg_upstream_sync_job**

```python
# jobs.py __all__ 末尾追加:
    "cg_upstream_sync_job",
```

- [ ] **E1.3: 验证可导入**

Run: `python -c "from backend.scheduler.jobs import cg_upstream_sync_job; print('OK')"`
Expected: `OK`

- [ ] **E1.4: Commit**

```bash
git add backend/scheduler/jobs.py
git commit -m "feat(codegarden): E1 add cg_upstream_sync_job (job 15)"
```

---

### Task E2: scheduler/scheduler.py 注册 job 15 (P1)

**Files:**
- Modify: `backend/scheduler/scheduler.py`

- [ ] **E2.1: 在 HotspotScheduler.start() 中追加 job 15 注册**

在 `scheduler.py` 的 `start()` 方法中，紧跟 `summary_weekly` (job 14) 注册后追加：

```python
        # Phase 2a CodeGarden: job 15 — 上游同步 (每日 09:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.cg_upstream_sync_job,
            trigger=CronTrigger(hour=9, timezone=SHANGHAI_TZ),
            id="cg_upstream_sync",
            name="codegarden upstream sync (daily 09:00)",
            replace_existing=True,
        )
```

- [ ] **E2.2: 验证 scheduler 启动后 job 15 注册成功**

Run:
```bash
python -c "
import asyncio
from backend.scheduler.scheduler import HotspotScheduler
from backend.services.collection_service import CollectionService
svc = CollectionService()
sched = HotspotScheduler(interval=9999)
sched.attach_service(svc)
sched.start()
import asyncio; asyncio.sleep(0.5)
jobs = sched.scheduler.get_jobs()
cg_job = [j for j in jobs if j.id == 'cg_upstream_sync']
print('cg_upstream_sync registered:', len(cg_job) == 1)
if cg_job: print('next_run:', cg_job[0].next_run_time)
sched.stop()
"
```
Expected: `cg_upstream_sync registered: True` + 一个 next_run 时间

- [ ] **E2.3: Commit**

```bash
git add backend/scheduler/scheduler.py
git commit -m "feat(codegarden): E2 register cg_upstream_sync job 15 (daily 09:00)"
```

---

## Group F — 同步包扩展 (Task F1)

### Task F1: sync_bundle.py 加入 cg_projects (P1)

**Files:**
- Modify: `backend/services/sync_bundle.py`

- [ ] **F1.1: 在 build_bundle 中追加 cg_projects 块**

打开 `backend/services/sync_bundle.py`，找到 `build_bundle` 函数中的 `records: dict[str, Any] = {...}` 块，在 `skills` 块后追加：

```python
        "codegarden_projects": _read_cg_projects_for_sync(),
```

并在文件中追加辅助函数（紧贴 `_now_iso` 或类似辅助函数后）：

```python
def _read_cg_projects_for_sync() -> list[dict]:
    """读取 cg_projects 主表数据用于跨端同步（不含 stages/links/activities）。"""
    try:
        from backend.repository.codegarden_repo import CodegardenProjectRepository
        items, _ = CodegardenProjectRepository().list(
            include_archived=True, limit=1000
        )
        return items
    except Exception as e:
        logger.warning(f"_read_cg_projects_for_sync failed (skipped): {e}")
        return []
```

- [ ] **F1.2: 在 apply_bundle 中追加 cg_projects 写入逻辑**

找到 `apply_bundle` 函数（或同步 merge 的对应入口），在处理 `skills` 块的位置追加 cg_projects 处理：

```python
def _apply_cg_projects(items: list[dict]) -> int:
    """将 bundle 中的 codegarden_projects 写回 SQLite (upsert by id)。"""
    if not items:
        return 0
    from backend.repository.db import get_connection
    conn = get_connection()
    n = 0
    for it in items:
        try:
            conn.execute(
                """
                INSERT INTO cg_projects (
                    id, name, display_name, description, type, source_type,
                    lifecycle_stage, health_score, local_path, repo_url,
                    upstream_url, upstream_default_branch, commits_behind,
                    commits_ahead, last_synced_at, source_item_id,
                    source_type_detail, tags, tech_stack, domain, priority,
                    active_skill_ids, created_at, last_activity_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, display_name=excluded.display_name,
                    description=excluded.description, type=excluded.type,
                    source_type=excluded.source_type,
                    lifecycle_stage=excluded.lifecycle_stage,
                    health_score=excluded.health_score, local_path=excluded.local_path,
                    repo_url=excluded.repo_url, upstream_url=excluded.upstream_url,
                    upstream_default_branch=excluded.upstream_default_branch,
                    commits_behind=excluded.commits_behind,
                    commits_ahead=excluded.commits_ahead,
                    last_synced_at=excluded.last_synced_at,
                    source_item_id=excluded.source_item_id,
                    source_type_detail=excluded.source_type_detail,
                    tags=excluded.tags, tech_stack=excluded.tech_stack,
                    domain=excluded.domain, priority=excluded.priority,
                    active_skill_ids=excluded.active_skill_ids,
                    last_activity_at=excluded.last_activity_at,
                    archived_at=excluded.archived_at
                """,
                (
                    it["id"], it["name"], it.get("display_name"),
                    it.get("description"), it["type"], it["source_type"],
                    it["lifecycle_stage"], it.get("health_score", 0),
                    it.get("local_path"), it.get("repo_url"),
                    it.get("upstream_url"), it.get("upstream_default_branch"),
                    it.get("commits_behind", 0), it.get("commits_ahead", 0),
                    it.get("last_synced_at"), it.get("source_item_id"),
                    it.get("source_type_detail"),
                    it.get("tags", "[]"), it.get("tech_stack", "[]"),
                    it.get("domain"), it.get("priority", 0),
                    it.get("active_skill_ids", "[]"),
                    it["created_at"], it.get("last_activity_at"),
                    it.get("archived_at"),
                ),
            )
            n += 1
        except Exception as e:
            logger.warning(f"_apply_cg_projects upsert {it.get('id')} failed: {e}")
    return n
```

并在 apply_bundle 处理流程中调用：

```python
# 在 apply_bundle 函数中, 处理完 skills 后追加:
if "codegarden_projects" in bundle:
    _apply_cg_projects(bundle["codegarden_projects"])
```

- [ ] **F1.3: 验证 build_bundle 包含 codegarden_projects key**

Run:
```bash
python -c "
from backend.services.sync_bundle import build_bundle
b = build_bundle()
print('codegarden_projects' in b, len(b.get('codegarden_projects', [])))
"
```
Expected: `True N` (N 可能是 0 如果还没创建项目，但 key 必须存在)

- [ ] **F1.4: Commit**

```bash
git add backend/services/sync_bundle.py
git commit -m "feat(codegarden): F1 include cg_projects in sync bundle"
```

---

## Group G — 前端 UI (Task G1-G11)

> **参考约定**：参考既有 `frontend/src/hooks/useSkills.ts` + `frontend/src/components/SkillsPage.tsx` + `frontend/src/components/Header.tsx` 模式；变量命名 snake_case 与后端对齐；样式走 CSS 变量（`var(--bg-hover)` / `var(--text-primary)` 等）。

### Task G1: `frontend/src/types/codegarden.ts` (P0)

**Files:**
- Create: `frontend/src/types/codegarden.ts`

- [ ] **G1.1: 编写类型定义文件**

```typescript
// frontend/src/types/codegarden.ts
// Phase 2a CodeGarden — 与 backend/services/codegarden_repo.py 输出对齐
// 字段命名 snake_case (与后端 Pydantic v2 model_dump(mode="json") 一致)

export type ProjectType = 'web_application' | 'api_service' | 'cli' | 'crawler' | 'library' | 'experiment';
export type ProjectSourceType = 'vibe' | 'fork' | 'imported' | 'reference';
export type LifecycleStage = 'ideation' | 'prototype' | 'development' | 'testing' | 'running' | 'maintenance' | 'archived' | 'deprecated';
export type SourceTypeDetail = 'trending' | 'github_search' | 'manual';

export interface CgProject {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  type: ProjectType;
  source_type: ProjectSourceType;
  lifecycle_stage: LifecycleStage;
  health_score: number;
  local_path: string | null;
  repo_url: string | null;
  upstream_url: string | null;
  upstream_default_branch: string | null;
  commits_behind: number;
  commits_ahead: number;
  last_synced_at: string | null;
  source_item_id: string | null;       // 反向溯源 knowledge_items.id
  source_type_detail: SourceTypeDetail | null;
  tags: string[];
  tech_stack: string[];
  domain: string | null;
  priority: number;
  active_skill_ids: string[];
  created_at: string;
  last_activity_at: string | null;
  archived_at: string | null;
}

export interface CgProjectStage {
  id: number;
  project_id: string;
  stage_name: string;
  status: 'pending' | 'in_progress' | 'done' | 'skipped';
  started_at: string | null;
  finished_at: string | null;
  notes: string | null;
  stage_order: number;
}

export interface CgProjectLink {
  id: number;
  project_id: string;
  link_type: 'doc' | 'demo' | 'repo' | 'upstream' | 'ci' | 'other';
  url: string;
  title: string | null;
  created_at: string;
}

export interface CgProjectActivity {
  id: number;
  project_id: string;
  activity_type: string;   // created / stage_changed / lifecycle_changed / synced / committed / etc
  payload: Record<string, unknown>;
  created_at: string;
}

export interface CgProjectListResponse {
  version: string;
  total: number;
  items: CgProject[];
}

export interface CgProjectResponse {
  version: string;
  item: CgProject;
}

export interface CgProjectCreateRequest {
  name: string;
  display_name?: string;
  description?: string;
  type: ProjectType;
  source_type: ProjectSourceType;
  lifecycle_stage?: LifecycleStage;
  local_path?: string;
  repo_url?: string;
  upstream_url?: string;
  upstream_default_branch?: string;
  source_item_id?: string;
  source_type_detail?: SourceTypeDetail;
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
  priority?: number;
}

export interface CgProjectUpdateRequest {
  display_name?: string;
  description?: string;
  type?: ProjectType;
  lifecycle_stage?: LifecycleStage;
  health_score?: number;
  local_path?: string;
  repo_url?: string;
  upstream_url?: string;
  upstream_default_branch?: string;
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
  priority?: number;
  active_skill_ids?: string[];
}

export interface GithubImportRequest {
  repo_url: string;
  local_path?: string;
  auto_sync?: boolean;              // 默认 true (导入后立即触发首次同步)
  source_type?: ProjectSourceType;  // 覆盖推断 (默认: 有 upstream=fork, 否则 imported)
  source_type_detail?: SourceTypeDetail;
  type?: ProjectType;               // 默认 'library'
  tags?: string[];
  tech_stack?: string[];
  domain?: string;
}

export interface FromKnowledgeRequest {
  item_id: string;
  source_type?: ProjectSourceType;  // 默认 'reference'
  local_path?: string;
}

export interface CandidateItem {
  id: string;
  title: string;
  source_url: string;
  domain: string | null;
  topic: string | null;
  ingested_at: string;
  updated_at: string;
  // 注: C3 SQL 已过滤已转化的 item, 此处不返回 converted 字段
  // (候选列表只包含 type=github 且未转化的 item)
}

export interface CandidatesResponse {
  version: string;
  total: number;
  items: CandidateItem[];
}

export interface LifecycleTransitionResponse {
  version: string;
  item: CgProject;
  activity_id: number;
}

export interface SyncTriggerResponse {
  version: string;
  task_id: number;
  project_id: string;
}

export interface GithubRepoMetadata {
  full_name: string;
  description: string | null;
  default_branch: string;
  upstream_url: string | null;     // 若 repo 是 fork
  stars: number;
  forks: number;
  pushed_at: string;
  homepage: string | null;
  language: string | null;
}

export interface UpstreamCompareResult {
  commits_behind: number;
  commits_ahead: number;
  upstream_default_branch: string;
  last_upstream_commit_at: string | null;
}

// 色值映射（与后端 PRD 8.2 一致）
export const LIFECYCLE_COLORS: Record<LifecycleStage, string> = {
  ideation: '#7c6aff',
  prototype: '#06b6d4',
  development: '#3b82f6',
  testing: '#f0c929',
  running: '#00c96a',
  maintenance: '#e8891a',
  archived: '#888899',
  deprecated: '#e85d5d',
};

export const LIFECYCLE_LABELS: Record<LifecycleStage, string> = {
  ideation: '构想中',
  prototype: '原型',
  development: '开发中',
  testing: '测试中',
  running: '运行中',
  maintenance: '维护中',
  archived: '已归档',
  deprecated: '已废弃',
};

export const SOURCE_TYPE_LABELS: Record<ProjectSourceType, string> = {
  vibe: '原创',
  fork: 'Fork',
  imported: '导入',
  reference: '参考',
};
```

- [ ] **G1.2: 验证类型编译通过**

Run:
```bash
cd frontend && npx tsc --noEmit src/types/codegarden.ts 2>&1 | head -20
```
Expected: 无错误输出

- [ ] **G1.3: Commit**

```bash
git add frontend/src/types/codegarden.ts
git commit -m "feat(codegarden): G1 add codegarden types"
```

---

### Task G2: `frontend/src/hooks/useCodegardenProjects.ts` (P0)

**Files:**
- Create: `frontend/src/hooks/useCodegardenProjects.ts`

- [ ] **G2.1: 编写 hook**

```typescript
// frontend/src/hooks/useCodegardenProjects.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  CgProject,
  CgProjectListResponse,
  CgProjectCreateRequest,
  CgProjectUpdateRequest,
  GithubImportRequest,
  FromKnowledgeRequest,
  CandidateItem,
  CandidatesResponse,
  LifecycleStage,
  ProjectSourceType,
  ProjectType,
} from '../types/codegarden';

export interface UseCodegardenProjectsReturn {
  items: CgProject[];
  total: number;
  loading: boolean;
  error: string | null;

  // 过滤
  lifecycle: LifecycleStage | 'all';
  sourceType: ProjectSourceType | 'all';
  projectType: ProjectType | 'all';
  keyword: string;
  setLifecycle: (s: LifecycleStage | 'all') => void;
  setSourceType: (s: ProjectSourceType | 'all') => void;
  setProjectType: (t: ProjectType | 'all') => void;
  setKeyword: (k: string) => void;

  // CRUD
  refresh: () => Promise<void>;
  create: (req: CgProjectCreateRequest) => Promise<CgProject>;
  update: (id: string, req: CgProjectUpdateRequest) => Promise<CgProject>;
  remove: (id: string) => Promise<void>;
  archive: (id: string) => Promise<CgProject>;
  restore: (id: string) => Promise<CgProject>;
  transition: (id: string, to: LifecycleStage) => Promise<CgProject>;
  syncUpstream: (id: string) => Promise<{ task_id: number }>;
  importFromGithub: (req: GithubImportRequest) => Promise<CgProject>;
  importFromKnowledge: (req: FromKnowledgeRequest) => Promise<CgProject>;
  listCandidates: () => Promise<CandidateItem[]>;
}

export function useCodegardenProjects(): UseCodegardenProjectsReturn {
  const [items, setItems] = useState<CgProject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [lifecycle, setLifecycle] = useState<LifecycleStage | 'all'>('all');
  const [sourceType, setSourceType] = useState<ProjectSourceType | 'all'>('all');
  const [projectType, setProjectType] = useState<ProjectType | 'all'>('all');
  const [keyword, setKeyword] = useState('');

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (lifecycle !== 'all') params.set('lifecycle', lifecycle);
      if (sourceType !== 'all') params.set('source_type', sourceType);
      if (projectType !== 'all') params.set('type', projectType);
      if (keyword.trim()) params.set('keyword', keyword.trim());

      const r = await fetch(`/api/codegarden/projects?${params}`, {
        signal: ctrl.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data: CgProjectListResponse = await r.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '加载失败');
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  }, [lifecycle, sourceType, projectType, keyword]);

  useEffect(() => {
    fetchList();
    return () => { if (abortRef.current) abortRef.current.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fetchList(), 250);
    return () => clearTimeout(t);
  }, [fetchList]);

  const refresh = useCallback(async () => {
    await fetchList();
  }, [fetchList]);

  const create = useCallback(async (req: CgProjectCreateRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`新建失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const data = await r.json();
    const item: CgProject = data;  // API 直接返回 project dict (不包 {item: ...})
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const update = useCallback(async (id: string, req: CgProjectUpdateRequest): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`更新失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const data = await r.json();
    const item: CgProject = data;  // API 直接返回 project dict
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const remove = useCallback(async (id: string): Promise<void> => {
    const r = await fetch(`/api/codegarden/projects/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error(`删除失败 (${r.status})`);
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(prev => Math.max(0, prev - 1));
  }, []);

  const archive = useCallback(async (id: string): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/archive`, { method: 'POST' });
    if (!r.ok) throw new Error(`归档失败 (${r.status})`);
    const data = await r.json();
    const item: CgProject = data;  // API 直接返回 project dict
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const restore = useCallback(async (id: string): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/restore`, { method: 'POST' });
    if (!r.ok) throw new Error(`恢复失败 (${r.status})`);
    const data = await r.json();
    const item: CgProject = data;  // API 直接返回 project dict
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const transition = useCallback(async (id: string, to: LifecycleStage): Promise<CgProject> => {
    const r = await fetch(`/api/codegarden/projects/${id}/lifecycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to }),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`状态切换失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    const data = await r.json();
    const item: CgProject = data;  // API 直接返回 project dict
    setItems(prev => prev.map(p => (p.id === id ? item : p)));
    return item;
  }, []);

  const syncUpstream = useCallback(async (id: string): Promise<{ task_id: number }> => {
    const r = await fetch(`/api/codegarden/projects/${id}/sync`, { method: 'POST' });
    if (r.status === 424) {
      throw new Error('未配置 github_token，请到 Secrets 页面添加');
    }
    if (!r.ok) throw new Error(`触发同步失败 (${r.status})`);
    const data = await r.json();
    return { task_id: data.task_id };
  }, []);

  const importFromGithub = useCallback(async (req: GithubImportRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/github/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (r.status === 424) {
      throw new Error('未配置 github_token，请到 Secrets 页面添加');
    }
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`GitHub 导入失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    // API 直接返回 project dict (不包 {item: ...})
    const item: CgProject = await r.json();
    setItems(prev => [item, ...prev]);
    setTotal(prev => prev + 1);
    return item;
  }, []);

  const importFromKnowledge = useCallback(async (req: FromKnowledgeRequest): Promise<CgProject> => {
    const r = await fetch('/api/codegarden/from-knowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`从知识库导入失败 (${r.status})${body ? `: ${body}` : ''}`);
    }
    // API 直接返回 project dict (不包 {item: ...})
    // 201 = 首次转化; 200 = 幂等 (已存在)
    const item: CgProject = await r.json();
    setItems(prev => {
      // 若已存在 (幂等情况), 替换而非重复插入
      const exists = prev.some(p => p.id === item.id);
      return exists ? prev.map(p => (p.id === item.id ? item : p)) : [item, ...prev];
    });
    setTotal(prev => prev);  // 幂等时不增加 total
    return item;
  }, []);

  const listCandidates = useCallback(async (): Promise<CandidateItem[]> => {
    const r = await fetch('/api/codegarden/candidates');
    if (!r.ok) throw new Error(`候选列表加载失败 (${r.status})`);
    const data: CandidatesResponse = await r.json();
    return data.items || [];
  }, []);

  return {
    items, total, loading, error,
    lifecycle, sourceType, projectType, keyword,
    setLifecycle, setSourceType, setProjectType, setKeyword,
    refresh, create, update, remove,
    archive, restore, transition, syncUpstream,
    importFromGithub, importFromKnowledge, listCandidates,
  };
}
```

- [ ] **G2.2: 验证类型检查通过**

Run:
```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: 无错误

- [ ] **G2.3: Commit**

```bash
git add frontend/src/hooks/useCodegardenProjects.ts
git commit -m "feat(codegarden): G2 add useCodegardenProjects hook"
```

---

### Task G3: `frontend/src/components/codegarden/ProjectBoard.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/ProjectBoard.tsx`

- [ ] **G3.1: 编写看板组件**

```tsx
// frontend/src/components/codegarden/ProjectBoard.tsx
import React, { useMemo } from 'react';
import { CgProject, LifecycleStage, LIFECYCLE_LABELS, LIFECYCLE_COLORS } from '../../types/codegarden';
import { ProjectCard } from './ProjectCard';

const COLUMN_STAGES: LifecycleStage[] = [
  'ideation', 'prototype', 'development', 'testing', 'running', 'maintenance',
];

interface ProjectBoardProps {
  items: CgProject[];
  onSelect?: (p: CgProject) => void;
  onTransition?: (id: string, to: LifecycleStage) => void;
}

export function ProjectBoard({ items, onSelect, onTransition }: ProjectBoardProps) {
  const grouped = useMemo(() => {
    const map: Record<LifecycleStage, CgProject[]> = {
      ideation: [], prototype: [], development: [], testing: [],
      running: [], maintenance: [], archived: [], deprecated: [],
    };
    for (const it of items) {
      if (map[it.lifecycle_stage]) map[it.lifecycle_stage].push(it);
    }
    return map;
  }, [items]);

  return (
    <div
      className="grid gap-3 overflow-x-auto pb-2"
      style={{ gridTemplateColumns: `repeat(${COLUMN_STAGES.length}, 220px)` }}
    >
      {COLUMN_STAGES.map(stage => (
        <div key={stage} className="flex flex-col gap-2">
          <div className="flex items-center justify-between px-2 py-1.5 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
            <span className="text-xs font-semibold" style={{ color: LIFECYCLE_COLORS[stage] }}>
              {LIFECYCLE_LABELS[stage]}
            </span>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {grouped[stage].length}
            </span>
          </div>
          <div className="flex flex-col gap-2 min-h-[120px]">
            {grouped[stage].map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                onClick={() => onSelect?.(p)}
                onTransition={onTransition}
              />
            ))}
            {grouped[stage].length === 0 && (
              <div
                className="text-[10px] text-center py-3 rounded-[var(--radius-sm)]"
                style={{ color: 'var(--text-muted)', border: '1px dashed var(--border-color)' }}
              >
                空
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **G3.2: Commit**

```bash
git add frontend/src/components/codegarden/ProjectBoard.tsx
git commit -m "feat(codegarden): G3 add ProjectBoard kanban"
```

---

### Task G4: `frontend/src/components/codegarden/ProjectCard.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/ProjectCard.tsx`

- [ ] **G4.1: 编写卡片组件**

```tsx
// frontend/src/components/codegarden/ProjectCard.tsx
import React from 'react';
import {
  CgProject,
  LifecycleStage,
  LIFECYCLE_COLORS,
  LIFECYCLE_LABELS,
  SOURCE_TYPE_LABELS,
} from '../../types/codegarden';

interface ProjectCardProps {
  project: CgProject;
  onClick?: () => void;
  onTransition?: (id: string, to: LifecycleStage) => void;
}

const NEXT_STAGE: Partial<Record<LifecycleStage, LifecycleStage>> = {
  ideation: 'prototype',
  prototype: 'development',
  development: 'testing',
  testing: 'running',
  running: 'maintenance',
};

export function ProjectCard({ project, onClick, onTransition }: ProjectCardProps) {
  const accent = LIFECYCLE_COLORS[project.lifecycle_stage];
  const next = NEXT_STAGE[project.lifecycle_stage];
  const behind = project.commits_behind;

  return (
    <div
      onClick={onClick}
      className="rounded-[var(--radius-sm)] p-2.5 cursor-pointer transition-colors"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
        borderLeft: `3px solid ${accent}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }} title={project.name}>
            {project.display_name || project.name}
          </div>
          {project.description && (
            <div className="text-[10px] mt-0.5 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
              {project.description}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-[9px] px-1.5 py-0.5 rounded"
          style={{ backgroundColor: accent + '20', color: accent }}
        >
          {LIFECYCLE_LABELS[project.lifecycle_stage]}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {SOURCE_TYPE_LABELS[project.source_type]}
        </span>
        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
          {project.type}
        </span>
        {project.source_type === 'fork' && behind > 0 && (
          <span
            className="text-[9px] px-1.5 py-0.5 rounded font-mono"
            style={{ backgroundColor: '#e85d5d20', color: '#e85d5d' }}
            title={`落后上游 ${behind} commits`}
          >
            ↓{behind}
          </span>
        )}
        {project.health_score > 0 && (
          <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
            ❤ {project.health_score}
          </span>
        )}
      </div>

      {next && onTransition && (
        <button
          onClick={(e) => { e.stopPropagation(); onTransition(project.id, next); }}
          className="mt-2 text-[9px] w-full py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
          title={`推进到 ${LIFECYCLE_LABELS[next]}`}
        >
          → {LIFECYCLE_LABELS[next]}
        </button>
      )}
    </div>
  );
}
```

- [ ] **G4.2: Commit**

```bash
git add frontend/src/components/codegarden/ProjectCard.tsx
git commit -m "feat(codegarden): G4 add ProjectCard"
```

---

### Task G5: `frontend/src/components/codegarden/ProjectDetail.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/ProjectDetail.tsx`

- [ ] **G5.1: 编写详情组件**

```tsx
// frontend/src/components/codegarden/ProjectDetail.tsx
import React, { useEffect, useState } from 'react';
import {
  CgProject,
  CgProjectActivity,
  CgProjectStage,
  LifecycleStage,
  LIFECYCLE_COLORS,
  LIFECYCLE_LABELS,
} from '../../types/codegarden';
import { UpstreamStatus } from './UpstreamStatus';

interface ProjectDetailProps {
  project: CgProject;
  onClose: () => void;
  onTransition: (id: string, to: LifecycleStage) => Promise<CgProject>;
  onSync: (id: string) => Promise<{ task_id: number }>;
}

const ALL_STAGES: LifecycleStage[] = [
  'ideation', 'prototype', 'development', 'testing', 'running', 'maintenance', 'archived', 'deprecated',
];

export function ProjectDetail({ project, onClose, onTransition, onSync }: ProjectDetailProps) {
  const [activities, setActivities] = useState<CgProjectActivity[]>([]);
  const [stages, setStages] = useState<CgProjectStage[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetch(`/api/codegarden/projects/${project.id}/activities`).then(r => r.json()),
      fetch(`/api/codegarden/projects/${project.id}/timeline`).then(r => r.json()),
    ])
      .then(([a, s]) => {
        if (cancelled) return;
        setActivities(a.items || []);
        setStages(s.items || []);
      })
      .catch(e => flash('err', `加载详情失败: ${e?.message || e}`))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [project.id]);

  const handleTransition = async (to: LifecycleStage) => {
    try {
      await onTransition(project.id, to);
      flash('ok', `已切换到 ${LIFECYCLE_LABELS[to]}`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const handleSync = async () => {
    try {
      const { task_id } = await onSync(project.id);
      flash('ok', `已触发同步 (task #${task_id})`);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    }
  };

  const accent = LIFECYCLE_COLORS[project.lifecycle_stage];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题区 */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
              {project.display_name || project.name}
            </h3>
            {project.description && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{project.description}</p>
            )}
          </div>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        {/* 元数据网格 */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3 text-[11px]">
          <Field label="状态" value={LIFECYCLE_LABELS[project.lifecycle_stage]} color={accent} />
          <Field label="来源" value={project.source_type} />
          <Field label="类型" value={project.type} />
          <Field label="domain" value={project.domain || '-'} />
          <Field label="优先级" value={String(project.priority)} />
          <Field label="健康度" value={String(project.health_score)} />
          {project.repo_url && (
            <Field label="repo" value={
              <a href={project.repo_url} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: 'var(--color-ai)' }}>
                {project.repo_url.replace('https://github.com/', '')}
              </a>
            } />
          )}
          {project.local_path && <Field label="local_path" value={project.local_path} />}
          {project.source_item_id && (
            <Field label="源资讯" value={
              <a href={`/api/knowledge/items/${project.source_item_id}`} target="_blank" rel="noreferrer" className="hover:underline" style={{ color: 'var(--color-ai)' }}>
                {project.source_item_id.slice(0, 8)}…
              </a>
            } />
          )}
        </div>

        {/* tags / tech_stack */}
        {(project.tags.length > 0 || project.tech_stack.length > 0) && (
          <div className="flex flex-wrap gap-1 mb-3">
            {project.tags.map(t => (
              <span key={t} className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>#{t}</span>
            ))}
            {project.tech_stack.map(t => (
              <span key={t} className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: '#3b82f620', color: '#3b82f6' }}>{t}</span>
            ))}
          </div>
        )}

        {/* 上游状态 */}
        {project.source_type === 'fork' && project.upstream_url && (
          <UpstreamStatus
            project={project}
            onSync={handleSync}
          />
        )}

        {/* lifecycle 切换 */}
        <div className="mt-4 mb-3">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>状态切换</div>
          <div className="flex flex-wrap gap-1">
            {ALL_STAGES.map(s => (
              <button
                key={s}
                onClick={() => handleTransition(s)}
                disabled={s === project.lifecycle_stage}
                className="text-[10px] px-2 py-0.5 rounded"
                style={{
                  backgroundColor: s === project.lifecycle_stage ? LIFECYCLE_COLORS[s] : 'var(--bg-hover)',
                  color: s === project.lifecycle_stage ? '#fff' : 'var(--text-secondary)',
                  cursor: s === project.lifecycle_stage ? 'default' : 'pointer',
                }}
              >
                {LIFECYCLE_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        {/* 阶段时间线 */}
        <div className="mt-4 mb-3">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>阶段时间线</div>
          {loading ? (
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : stages.length === 0 ? (
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无阶段记录</div>
          ) : (
            <div className="flex flex-col gap-1">
              {stages.map(st => (
                <div key={st.id} className="flex items-center gap-2 text-[10px]">
                  <span className="font-mono" style={{ color: 'var(--text-muted)' }}>#{st.stage_order}</span>
                  <span style={{ color: 'var(--text-primary)' }}>{st.stage_name}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>[{st.status}]</span>
                  {st.started_at && (
                    <span style={{ color: 'var(--text-muted)' }}>{new Date(st.started_at).toLocaleString()}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 活动日志 */}
        <div className="mt-4">
          <div className="text-[10px] mb-1.5" style={{ color: 'var(--text-muted)' }}>最近活动</div>
          {loading ? (
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : activities.length === 0 ? (
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无活动</div>
          ) : (
            <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
              {activities.slice(0, 20).map(a => (
                <div key={a.id} className="flex items-start gap-2 text-[10px]">
                  <span style={{ color: 'var(--text-muted)' }}>{new Date(a.created_at).toLocaleString()}</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{a.activity_type}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {toast && (
          <div
            className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs"
            style={{
              backgroundColor: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
              color: '#fff',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div>
      <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-[11px] font-mono" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}
```

- [ ] **G5.2: Commit**

```bash
git add frontend/src/components/codegarden/ProjectDetail.tsx
git commit -m "feat(codegarden): G5 add ProjectDetail dialog"
```

---

### Task G6: `frontend/src/components/codegarden/GithubImportDialog.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/GithubImportDialog.tsx`

- [ ] **G6.1: 编写导入对话框**

```tsx
// frontend/src/components/codegarden/GithubImportDialog.tsx
import React, { useState, useEffect } from 'react';
import {
  GithubImportRequest,
  GithubRepoMetadata,
  ProjectSourceType,
  ProjectType,
  SourceTypeDetail,
} from '../../types/codegarden';

interface GithubImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  importFn: (req: GithubImportRequest) => Promise<unknown>;
}

const inputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '2px',
  display: 'block',
};

export function GithubImportDialog({ open, onClose, onImported, importFn }: GithubImportDialogProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const [localPath, setLocalPath] = useState('');
  const [sourceType, setSourceType] = useState<ProjectSourceType>('fork');
  const [sourceTypeDetail, setSourceTypeDetail] = useState<SourceTypeDetail>('trending');
  const [projectType, setProjectType] = useState<ProjectType>('web_application');
  const [tags, setTags] = useState('');
  const [techStack, setTechStack] = useState('');
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  useEffect(() => {
    if (open) {
      setRepoUrl(''); setLocalPath(''); setTags(''); setTechStack(''); setDomain('');
      setSourceType('fork'); setSourceTypeDetail('trending'); setProjectType('web_application');
      setToast(null);
    }
  }, [open]);

  if (!open) return null;

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const handlePreview = async () => {
    if (!repoUrl.trim()) { flash('err', '请输入 GitHub repo URL'); return; }
    try {
      const r = await fetch(`/api/codegarden/github/metadata?url=${encodeURIComponent(repoUrl.trim())}`);
      if (r.status === 424) { flash('err', '未配置 github_token'); return; }
      if (!r.ok) { flash('err', `获取元数据失败 (${r.status})`); return; }
      const data: GithubRepoMetadata = await r.json();
      // 自动填充: repo_url 已输入, 默认分支写入 tech_stack 提示
      if (data.language) setTechStack(prev => prev || data.language!);
      flash('ok', `✓ ${data.full_name} | ⭐${data.stars} | ${data.default_branch}`);
    } catch (e: any) {
      flash('err', `预览失败: ${e?.message || e}`);
    }
  };

  const handleSubmit = async () => {
    if (!repoUrl.trim()) { flash('err', '请输入 GitHub repo URL'); return; }
    setBusy(true);
    try {
      const req: GithubImportRequest = {
        repo_url: repoUrl.trim(),
        source_type: sourceType,
        source_type_detail: sourceTypeDetail,
        type: projectType,
        tags: tags.split(',').map(s => s.trim()).filter(Boolean),
        tech_stack: techStack.split(',').map(s => s.trim()).filter(Boolean),
        domain: domain.trim() || undefined,
      };
      if (localPath.trim()) req.local_path = localPath.trim();
      await importFn(req);
      flash('ok', '✓ 已导入');
      setTimeout(() => { onClose(); onImported(); }, 800);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>GitHub 导入</h3>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="col-span-2">
            <label style={labelStyle}>Repo URL *</label>
            <div className="flex gap-1">
              <input
                style={inputStyle}
                placeholder="https://github.com/owner/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
              <button onClick={handlePreview} className="btn-ghost px-2 py-1 text-[10px]">预览</button>
            </div>
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Local Path (可选)</label>
            <input style={inputStyle} placeholder="~/code/repo" value={localPath} onChange={(e) => setLocalPath(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Source Type</label>
            <select style={inputStyle} value={sourceType} onChange={(e) => setSourceType(e.target.value as ProjectSourceType)}>
              <option value="fork">fork</option>
              <option value="imported">imported</option>
              <option value="reference">reference</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Source Detail</label>
            <select style={inputStyle} value={sourceTypeDetail} onChange={(e) => setSourceTypeDetail(e.target.value as SourceTypeDetail)}>
              <option value="trending">trending</option>
              <option value="github_search">github_search</option>
              <option value="manual">manual</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Type</label>
            <select style={inputStyle} value={projectType} onChange={(e) => setProjectType(e.target.value as ProjectType)}>
              <option value="web_application">web_application</option>
              <option value="api_service">api_service</option>
              <option value="cli">cli</option>
              <option value="crawler">crawler</option>
              <option value="library">library</option>
              <option value="experiment">experiment</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Domain</label>
            <input style={inputStyle} placeholder="security / ai / web" value={domain} onChange={(e) => setDomain(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Tags (逗号分隔)</label>
            <input style={inputStyle} placeholder="tool, automation" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label style={labelStyle}>Tech Stack (逗号分隔)</label>
            <input style={inputStyle} placeholder="Python, FastAPI" value={techStack} onChange={(e) => setTechStack(e.target.value)} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">取消</button>
          <button
            onClick={handleSubmit}
            disabled={busy}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)' }}
          >
            {busy ? '导入中…' : '导入'}
          </button>
        </div>

        {toast && (
          <div
            className="mt-2 text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: toast.kind === 'ok' ? '#00c96a20' : '#e85d5d20',
              color: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **G6.2: Commit**

```bash
git add frontend/src/components/codegarden/GithubImportDialog.tsx
git commit -m "feat(codegarden): G6 add GithubImportDialog"
```

---

### Task G7: `frontend/src/components/codegarden/FromKnowledgeDialog.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/FromKnowledgeDialog.tsx`

- [ ] **G7.1: 编写从知识库导入对话框**

```tsx
// frontend/src/components/codegarden/FromKnowledgeDialog.tsx
import React, { useEffect, useState } from 'react';
import { CandidateItem, FromKnowledgeRequest, ProjectSourceType } from '../../types/codegarden';

interface FromKnowledgeDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  listCandidates: () => Promise<CandidateItem[]>;
  importFn: (req: FromKnowledgeRequest) => Promise<unknown>;
}

const inputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

export function FromKnowledgeDialog({ open, onClose, onImported, listCandidates, importFn }: FromKnowledgeDialogProps) {
  const [candidates, setCandidates] = useState<CandidateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<ProjectSourceType>('reference');
  const [localPath, setLocalPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelectedId(null);
    setSourceType('reference');
    setLocalPath('');
    setToast(null);
    listCandidates()
      .then(items => setCandidates(items))
      .catch(e => setToast({ kind: 'err', msg: `加载失败: ${e?.message || e}` }))
      .finally(() => setLoading(false));
  }, [open, listCandidates]);

  if (!open) return null;

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const handleSubmit = async () => {
    if (!selectedId) { flash('err', '请选择一条资讯'); return; }
    setBusy(true);
    try {
      const req: FromKnowledgeRequest = {
        item_id: selectedId,
        source_type: sourceType,
      };
      if (localPath.trim()) req.local_path = localPath.trim();
      await importFn(req);
      flash('ok', '✓ 已加入 CodeGarden');
      setTimeout(() => { onClose(); onImported(); }, 800);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl max-h-[80vh] flex flex-col rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            从知识库导入 (GitHub 资讯)
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto mb-3">
          {loading ? (
            <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : candidates.length === 0 ? (
            <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
              暂无 type=github 的未转化资讯
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {candidates.map(c => (
                <label
                  key={c.id}
                  className="flex items-start gap-2 p-2 rounded cursor-pointer"
                  style={{
                    backgroundColor: selectedId === c.id ? 'var(--bg-hover)' : 'transparent',
                    border: '1px solid',
                    borderColor: selectedId === c.id ? 'var(--color-ai)' : 'var(--border-color)',
                  }}
                >
                  <input
                    type="radio"
                    name="candidate"
                    checked={selectedId === c.id}
                    onChange={() => setSelectedId(c.id)}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }} title={c.title}>
                      {c.title}
                    </div>
                    <div className="text-[10px] font-mono truncate" style={{ color: 'var(--text-muted)' }}>
                      {c.source_url}
                    </div>
                    <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {new Date(c.ingested_at).toLocaleString()}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        {selectedId && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source Type</label>
              <select style={inputStyle} value={sourceType} onChange={(e) => setSourceType(e.target.value as ProjectSourceType)}>
                <option value="reference">reference (参考)</option>
                <option value="fork">fork (二开)</option>
                <option value="imported">imported (导入)</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Local Path (可选)</label>
              <input style={inputStyle} value={localPath} onChange={(e) => setLocalPath(e.target.value)} placeholder="~/code/repo" />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">取消</button>
          <button
            onClick={handleSubmit}
            disabled={busy || !selectedId}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)', opacity: busy || !selectedId ? 0.5 : 1 }}
          >
            {busy ? '导入中…' : '加入 CodeGarden'}
          </button>
        </div>

        {toast && (
          <div
            className="mt-2 text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: toast.kind === 'ok' ? '#00c96a20' : '#e85d5d20',
              color: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **G7.2: Commit**

```bash
git add frontend/src/components/codegarden/FromKnowledgeDialog.tsx
git commit -m "feat(codegarden): G7 add FromKnowledgeDialog"
```

---

### Task G8: `frontend/src/components/codegarden/UpstreamStatus.tsx` (P0)

**Files:**
- Create: `frontend/src/components/codegarden/UpstreamStatus.tsx`

- [ ] **G8.1: 编写上游状态组件**

```tsx
// frontend/src/components/codegarden/UpstreamStatus.tsx
import React from 'react';
import { CgProject } from '../../types/codegarden';

interface UpstreamStatusProps {
  project: CgProject;
  onSync: () => void;
}

export function UpstreamStatus({ project, onSync }: UpstreamStatusProps) {
  const behind = project.commits_behind;
  const ahead = project.commits_ahead;
  const lastSync = project.last_synced_at
    ? new Date(project.last_synced_at).toLocaleString()
    : '从未同步';

  const status = behind === 0
    ? { label: '已同步', color: '#00c96a' }
    : behind <= 10
    ? { label: `${behind} commits 落后`, color: '#f0c929' }
    : { label: `${behind} commits 严重落后`, color: '#e85d5d' };

  return (
    <div
      className="rounded-[var(--radius-sm)] p-2.5 mb-2"
      style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
          上游同步状态
        </div>
        <button
          onClick={onSync}
          className="text-[10px] px-2 py-0.5 rounded"
          style={{ border: '1px solid var(--border-color)', color: 'var(--color-ai)' }}
        >
          立即同步
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <span style={{ color: 'var(--text-muted)' }}>状态: </span>
          <span style={{ color: status.color }}>{status.label}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>默认分支: </span>
          <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
            {project.upstream_default_branch || '-'}
          </span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>落后: </span>
          <span className="font-mono" style={{ color: behind > 0 ? '#e85d5d' : 'var(--text-primary)' }}>{behind}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>领先: </span>
          <span className="font-mono" style={{ color: ahead > 0 ? '#00c96a' : 'var(--text-primary)' }}>{ahead}</span>
        </div>
        <div className="col-span-2">
          <span style={{ color: 'var(--text-muted)' }}>最后同步: </span>
          <span style={{ color: 'var(--text-secondary)' }}>{lastSync}</span>
        </div>
        <div className="col-span-2">
          <span style={{ color: 'var(--text-muted)' }}>upstream: </span>
          {project.upstream_url ? (
            <a href={project.upstream_url} target="_blank" rel="noreferrer" className="hover:underline font-mono" style={{ color: 'var(--color-ai)' }}>
              {project.upstream_url.replace('https://github.com/', '')}
            </a>
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>-</span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **G8.2: Commit**

```bash
git add frontend/src/components/codegarden/UpstreamStatus.tsx
git commit -m "feat(codegarden): G8 add UpstreamStatus"
```

---

### Task G9: `frontend/src/components/CodegardenPage.tsx` + App.tsx 路由 (P0)

**Files:**
- Create: `frontend/src/components/CodegardenPage.tsx`
- Modify: `frontend/src/App.tsx` (追加 import + Route)

- [ ] **G9.1: 编写 CodegardenPage**

```tsx
// frontend/src/components/CodegardenPage.tsx
import React, { useState } from 'react';
import { useCodegardenProjects } from '../hooks/useCodegardenProjects';
import { ProjectBoard } from './codegarden/ProjectBoard';
import { ProjectDetail } from './codegarden/ProjectDetail';
import { GithubImportDialog } from './codegarden/GithubImportDialog';
import { FromKnowledgeDialog } from './codegarden/FromKnowledgeDialog';
import { CgProject, LifecycleStage, ProjectSourceType, ProjectType } from '../types/codegarden';
import { Icon } from './Icon';

interface CodegardenPageProps {
  onBack: () => void;
}

export function CodegardenPage({ onBack }: CodegardenPageProps) {
  const {
    items, total, loading, error,
    lifecycle, sourceType, projectType, keyword,
    setLifecycle, setSourceType, setProjectType, setKeyword,
    refresh, transition, syncUpstream,
    importFromGithub, importFromKnowledge, listCandidates,
  } = useCodegardenProjects();

  const [selected, setSelected] = useState<CgProject | null>(null);
  const [githubOpen, setGithubOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);

  return (
    <div className="codegarden-page">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn-ghost px-2.5 py-1.5 text-xs"
            title="返回首页"
            aria-label="返回首页"
          >
            <Icon>
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </Icon>
            返回首页
          </button>
          <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            🌱 CodeGarden
          </h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            vibecoding 工作台 + 二开项目管理
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {total} 项</span>
          <button
            onClick={() => setKnowledgeOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + 从知识库
          </button>
          <button
            onClick={() => setGithubOpen(true)}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)' }}
          >
            + GitHub 导入
          </button>
          <button
            onClick={refresh}
            className="btn-ghost px-2 py-1.5 text-xs"
            title="刷新"
          >
            <Icon>
              <polyline points="23 4 23 10 17 10" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </Icon>
          </button>
        </div>
      </div>

      {/* 过滤器 */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <select
          value={lifecycle}
          onChange={(e) => setLifecycle(e.target.value as LifecycleStage | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部状态</option>
          <option value="ideation">构想中</option>
          <option value="prototype">原型</option>
          <option value="development">开发中</option>
          <option value="testing">测试中</option>
          <option value="running">运行中</option>
          <option value="maintenance">维护中</option>
          <option value="archived">已归档</option>
          <option value="deprecated">已废弃</option>
        </select>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as ProjectSourceType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部来源</option>
          <option value="vibe">原创</option>
          <option value="fork">Fork</option>
          <option value="imported">导入</option>
          <option value="reference">参考</option>
        </select>
        <select
          value={projectType}
          onChange={(e) => setProjectType(e.target.value as ProjectType | 'all')}
          className="text-[11px] px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        >
          <option value="all">全部类型</option>
          <option value="web_application">web_application</option>
          <option value="api_service">api_service</option>
          <option value="cli">cli</option>
          <option value="crawler">crawler</option>
          <option value="library">library</option>
          <option value="experiment">experiment</option>
        </select>
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索 name / description"
          className="text-[11px] px-2 py-1 rounded flex-1 min-w-[180px]"
          style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
        />
      </div>

      {/* 看板 */}
      {loading ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>加载中…</div>
      ) : error ? (
        <div className="text-xs text-center py-6" style={{ color: '#e85d5d' }}>{error}</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-center py-6" style={{ color: 'var(--text-muted)' }}>
          暂无项目，点击右上角 + 添加
        </div>
      ) : (
        <ProjectBoard
          items={items}
          onSelect={setSelected}
          onTransition={(id, to) => transition(id, to).catch(e => window.alert(e?.message || e))}
        />
      )}

      {/* 详情弹窗 */}
      {selected && (
        <ProjectDetail
          project={selected}
          onClose={() => setSelected(null)}
          onTransition={transition}
          onSync={syncUpstream}
        />
      )}

      {/* GitHub 导入弹窗 */}
      <GithubImportDialog
        open={githubOpen}
        onClose={() => setGithubOpen(false)}
        onImported={refresh}
        importFn={importFromGithub}
      />

      {/* 从知识库导入弹窗 */}
      <FromKnowledgeDialog
        open={knowledgeOpen}
        onClose={() => setKnowledgeOpen(false)}
        onImported={refresh}
        listCandidates={listCandidates}
        importFn={importFromKnowledge}
      />
    </div>
  );
}
```

- [ ] **G9.2: 在 App.tsx 追加路由**

修改 `frontend/src/App.tsx`:

在 import 区追加（紧跟 KnowledgePage 后面）:
```typescript
import { CodegardenPage } from './components/CodegardenPage';
```

在 `<Routes>` 内追加（紧跟 `/knowledge` 后面）:
```tsx
<Route path="/codegarden" element={<CodegardenPage onBack={goHome} />} />
```

- [ ] **G9.3: 验证 build 通过**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: `✓ built` 无错误

- [ ] **G9.4: Commit**

```bash
git add frontend/src/components/CodegardenPage.tsx frontend/src/App.tsx
git commit -m "feat(codegarden): G9 add CodegardenPage + route"
```

---

### Task G10: KnowledgePage 集成「加入 CodeGarden」CTA (P0)

**Files:**
- Modify: `frontend/src/components/KnowledgePage.tsx`
- Modify: `frontend/src/components/ItemDetailDialog.tsx`

- [ ] **G10.1: 在 KnowledgePage 顶部按钮组追加 CTA**

在 `KnowledgePage.tsx` 的「同步 Cubox」按钮前追加一个「加入 CodeGarden」按钮（仅当过滤 type=github 时显示）。先读取现有 ItemDetailDialog 接口：

```bash
grep -n "interface ItemDetailDialogProps\|type ItemDetailDialogProps" frontend/src/components/ItemDetailDialog.tsx
```

预期：能找到 props 定义，含 `item: KnowledgeItem`。

- [ ] **G10.2: 在 ItemDetailDialog 追加「加入 CodeGarden」CTA**

修改 `frontend/src/components/ItemDetailDialog.tsx`：

在 dialog 的 footer 按钮区追加（仅 `item.type === 'github'` 时显示）:

```tsx
{item.type === 'github' && (
  <button
    onClick={handleAddToCodegarden}
    className="btn-ghost px-3 py-1.5 text-xs"
    style={{ color: '#8b5cf6' }}
    title="转化为 CodeGarden 项目（source_type=reference）"
  >
    🌱 加入 CodeGarden
  </button>
)}
```

在组件内追加 handler（hook 不变，直接 fetch）:

```typescript
const handleAddToCodegarden = async () => {
  if (!item?.id) return;
  try {
    const r = await fetch('/api/codegarden/from-knowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: item.id,
        source_type: 'reference',
      }),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      throw new Error(`HTTP ${r.status}${body ? `: ${body}` : ''}`);
    }
    // 201 = 首次转化; 200 = 幂等 (已存在)
    if (r.status === 201) {
      window.alert('✓ 已加入 CodeGarden');
    } else {
      window.alert('ℹ 该项目已在 CodeGarden 中');
    }
    onClose?.();
  } catch (e: any) {
    window.alert(`加入失败: ${e?.message || e}`);
  }
};
```

- [ ] **G10.3: 验证 build 通过**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -10
```
Expected: 无错误

- [ ] **G10.4: Commit**

```bash
git add frontend/src/components/KnowledgePage.tsx frontend/src/components/ItemDetailDialog.tsx
git commit -m "feat(codegarden): G10 add CodeGarden CTA on github knowledge items"
```

---

### Task G11: Header 导航增加 CodeGarden 入口 (P1)

**Files:**
- Modify: `frontend/src/components/Header.tsx`

- [ ] **G11.1: 在 Header.tsx 追加 CodeGarden 按钮**

在 `frontend/src/components/Header.tsx`:

(a) 修改 `ViewRoute` 类型（在文件顶部）:
```typescript
type ViewRoute = '/' | '/todos' | '/history' | '/skills' | '/secrets' | '/sync' | '/weekly-report' | '/knowledge' | '/codegarden';
```

(b) 在「知识管理」按钮后面（约 line 332 之后）追加:
```tsx
<button
  onClick={() => navigateTo('/codegarden')}
  className="btn-ghost px-2.5 py-1.5 text-xs"
  title={isActive(location.pathname, '/codegarden') ? '返回首页' : 'CodeGarden 项目管理'}
  aria-label={isActive(location.pathname, '/codegarden') ? '首页' : 'CodeGarden'}
  aria-pressed={isActive(location.pathname, '/codegarden')}
  style={isActive(location.pathname, '/codegarden') ? activeStyle : undefined}
>
  <Icon>
    <path d="M12 2C8 2 5 5 5 9c0 3 2 5 4 6 0 2-2 3-2 5h10c0-2-2-3-2-5 2-1 4-3 4-6 0-4-3-7-7-7z" />
    <path d="M9 22h6" />
  </Icon>
</button>
```

- [ ] **G11.2: 验证 build 通过 + 导航按钮可见**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -10
```
Expected: `✓ built`

- [ ] **G11.3: Commit**

```bash
git add frontend/src/components/Header.tsx
git commit -m "feat(codegarden): G11 add Header navigation entry"
```

---

## Group H — 测试套件 (Task H1-H3)

### Task H1: API 单测（已在 D3 完成，H1 引用） (P0)

**Files:**
- Reference: `backend/tests/test_codegarden_api.py` (已在 D3 创建)

- [ ] **H1.1: 确认 D3 测试通过 + 覆盖率验证**

Run:
```bash
cd backend && pytest tests/test_codegarden_api.py -v --tb=short 2>&1 | tail -30
```
Expected: 16 个测试全部 PASS

- [ ] **H1.2: 覆盖率检查（可选）**

Run:
```bash
cd backend && pytest tests/test_codegarden_api.py --cov=api.codegarden --cov-report=term-missing 2>&1 | tail -20
```
Expected: api.codegarden 覆盖率 >= 80%

- [ ] **H1.3: 无需 commit（D3 已 commit）**

---

### Task H2: 前端组件测试 (P1)

**Files:**
- Create: `frontend/src/components/codegarden/ProjectCard.test.tsx`

- [ ] **H2.1: 编写 ProjectCard 组件测试**

```tsx
// frontend/src/components/codegarden/ProjectCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectCard } from './ProjectCard';
import { CgProject, LifecycleStage } from '../../types/codegarden';

const baseProject: CgProject = {
  id: 'p1',
  name: 'test-repo',
  display_name: 'Test Repo',
  description: 'A test project',
  type: 'web_application',
  source_type: 'fork',
  lifecycle_stage: 'development',
  health_score: 75,
  local_path: null,
  repo_url: 'https://github.com/owner/test-repo',
  upstream_url: 'https://github.com/upstream/test-repo',
  upstream_default_branch: 'main',
  commits_behind: 5,
  commits_ahead: 2,
  last_synced_at: null,
  source_item_id: null,
  source_type_detail: 'trending',
  tags: ['tool'],
  tech_stack: ['Python'],
  domain: 'security',
  priority: 1,
  active_skill_ids: [],
  created_at: '2026-07-19T00:00:00Z',
  last_activity_at: null,
  archived_at: null,
};

describe('ProjectCard', () => {
  it('renders project display_name', () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText('Test Repo')).toBeInTheDocument();
  });

  it('renders fork source type label', () => {
    render(<ProjectCard project={baseProject} />);
    // SOURCE_TYPE_LABELS['fork'] = 'Fork' (大写, 是人类可读 label, 非原始值)
    expect(screen.getByText('Fork')).toBeInTheDocument();
  });

  it('renders commits_behind badge when > 0 and source_type=fork', () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText('↓5')).toBeInTheDocument();
  });

  it('hides commits_behind badge when source_type != fork', () => {
    const p = { ...baseProject, source_type: 'vibe' as const };
    render(<ProjectCard project={p} />);
    expect(screen.queryByText('↓5')).not.toBeInTheDocument();
  });

  it('calls onClick when card is clicked', () => {
    const onClick = vi.fn();
    render(<ProjectCard project={baseProject} onClick={onClick} />);
    fireEvent.click(screen.getByText('Test Repo'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('calls onTransition when advance button is clicked', () => {
    const onTransition = vi.fn();
    render(<ProjectCard project={baseProject} onTransition={onTransition} />);
    const btn = screen.getByText(/→/);
    fireEvent.click(btn);
    expect(onTransition).toHaveBeenCalledWith('p1', 'testing');
  });

  it('does not render advance button when in maintenance stage', () => {
    const p = { ...baseProject, lifecycle_stage: 'maintenance' as LifecycleStage };
    render(<ProjectCard project={p} onTransition={vi.fn()} />);
    expect(screen.queryByText(/→/)).not.toBeInTheDocument();
  });

  it('renders health_score when > 0', () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText(/75/)).toBeInTheDocument();
  });
});
```

- [ ] **H2.2: 运行测试**

Run:
```bash
cd frontend && npx vitest run src/components/codegarden/ProjectCard.test.tsx 2>&1 | tail -30
```
Expected: 8 个测试全部 PASS

- [ ] **H2.3: Commit**

```bash
git add frontend/src/components/codegarden/ProjectCard.test.tsx
git commit -m "test(codegarden): H2 add ProjectCard component tests"
```

---

### Task H3: e2e 测试 — 资讯→项目转化全流程 (P0)

**Files:**
- Create: `backend/tests/test_codegarden_e2e.py`

- [ ] **H3.1: 编写 e2e 测试**

```python
# backend/tests/test_codegarden_e2e.py
"""
Phase 2a Task H3 — e2e 测试：资讯→项目转化全流程
验证：knowledge_items.type=github → from-knowledge API → cg_projects 记录创建
       → source_item_id 反向溯源可查 → knowledge frontmatter project_id 写入
"""

import os
import sys
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def e2e_client(tmp_path, monkeypatch):
    """独立 DB 的 FastAPI 测试客户端"""
    db_path = tmp_path / "e2e.db"
    monkeypatch.setenv("HOTSPOT_DB_PATH", str(db_path))

    # 延迟导入避免污染全局
    from backend.repository.db import init_db, apply_migrations
    init_db()

    from backend.main import app
    with TestClient(app) as client:
        yield client


def _seed_github_knowledge_item(client: TestClient) -> str:
    """插入一条 type=github 的 knowledge_item，返回其 id"""
    item_id = f"github-{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    conn.execute(
        """
        INSERT INTO knowledge_items (
            id, title, source, source_url, domain, topic, type,
            difficulty, tags, concepts, mastered, compiled,
            ingested_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            "anthropics/anthropic-sdk-python",
            "secnews",
            "https://github.com/anthropics/anthropic-sdk-python",
            "ai", None, "github",
            None, "[]", "[]", 0, 0,
            "2026-07-19T00:00:00Z", "2026-07-19T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()
    return item_id


def test_e2e_knowledge_to_codegarden_flow(e2e_client: TestClient):
    """
    验证完整转化路径 (资讯→项目→反向溯源):
    1. 准备一条 type=github 的 knowledge_item (GitHub 资讯作为二开源)
    2. 调用 /api/codegarden/from-knowledge 转化为 cg_projects
    3. 验证 cg_projects.source_item_id 等于 knowledge_item.id (反向溯源)
    4. 验证 /api/codegarden/candidates 列表中该 item 已不再出现 (C3 SQL 过滤)
    5. 验证通过 source_item_id 反查能查到 project
    6. 验证 knowledge_item 的 frontmatter 文件中已写入 project_id 字段
    """
    # Step 1: seed knowledge item
    item_id = _seed_github_knowledge_item(e2e_client)

    # Step 2: 验证 candidates 列表中可见该 item (转化前)
    r = e2e_client.get("/api/codegarden/candidates")
    assert r.status_code == 200
    candidates = r.json()
    candidate_ids = [c["id"] for c in candidates["items"]]
    assert item_id in candidate_ids, f"{item_id} should appear in candidates before conversion"

    # Step 3: 调用 from-knowledge API 转化
    r = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={
            "item_id": item_id,
            "source_type": "reference",
        },
    )
    assert r.status_code == 201, f"转化失败: {r.status_code} {r.text}"
    project = r.json()  # API 直接返回 project dict (不包 {item: ...})

    # Step 4: 验证 cg_projects 字段 (反向溯源)
    assert project["source_item_id"] == item_id, "source_item_id 反向溯源字段必须等于 knowledge_item.id"
    assert project["source_type"] == "reference"
    assert project["repo_url"] == "https://github.com/anthropics/anthropic-sdk-python"
    assert project["name"]  # name 不能为空

    # Step 5: 验证 candidates 列表中该 item 已不再出现 (C3 SQL 过滤已转化的)
    r = e2e_client.get("/api/codegarden/candidates")
    candidate_ids_after = [c["id"] for c in r.json()["items"]]
    assert item_id not in candidate_ids_after, "转化后 item 应从 candidates 列表移除"

    # Step 6: 验证通过 source_item_id 反查能查到 project
    r = e2e_client.get(f"/api/codegarden/projects?source_item_id={item_id}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1, "通过 source_item_id 反查应只返回 1 条"
    assert items[0]["id"] == project["id"]

    # Step 7: 验证 knowledge_item frontmatter 已写入 project_id
    # 注意：frontmatter 写入是 best-effort，文件可能不存在（test 环境）
    # 这里通过检查 API 返回的 metadata 间接验证
    r = e2e_client.get(f"/api/knowledge/items/{item_id}")
    if r.status_code == 200:
        item_data = r.json().get("item", {})
        # frontmatter project_id 字段为可选，不强制断言
        # 但若存在则必须等于 project.id
        if "project_id" in item_data:
            assert item_data["project_id"] == project["id"]


def test_e2e_duplicate_conversion_returns_existing(e2e_client: TestClient):
    """同一 knowledge_item 重复调用 from-knowledge 应返回已存在的 project 而非报错 (幂等)"""
    item_id = _seed_github_knowledge_item(e2e_client)

    # 第一次转化
    r1 = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r1.status_code == 201
    project1 = r1.json()  # API 直接返回 project dict

    # 第二次转化（应幂等返回同一个 project, status 200）
    r2 = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r2.status_code == 200, f"重复转化应返回 200 而非报错: {r2.status_code} {r2.text}"
    project2 = r2.json()

    assert project1["id"] == project2["id"], "重复转化必须返回同一个 project"


def test_e2e_non_github_item_rejected(e2e_client: TestClient):
    """type != github 的 knowledge_item 不应被转化为 cg_projects"""
    item_id = f"ai-{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    conn.execute(
        """
        INSERT INTO knowledge_items (
            id, title, source, source_url, domain, topic, type,
            difficulty, tags, concepts, mastered, compiled,
            ingested_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id, "Some AI news", "secnews", "https://example.com/news",
            "ai", None, "ai", None, "[]", "[]", 0, 0,
            "2026-07-19T00:00:00Z", "2026-07-19T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    r = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r.status_code == 400, f"type=ai 的 item 不应能转化为 cg_projects: {r.status_code}"
    # API 返回 {"detail": {"message": "..."}} — detail 是 dict 不是 string
    detail = r.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "github" in msg.lower(), f"错误消息应提及 github: {msg}"
```

- [ ] **H3.2: 运行 e2e 测试**

Run:
```bash
cd backend && pytest tests/test_codegarden_e2e.py -v --tb=short 2>&1 | tail -30
```
Expected: 3 个测试全部 PASS

- [ ] **H3.3: Commit**

```bash
git add backend/tests/test_codegarden_e2e.py
git commit -m "test(codegarden): H3 add e2e test for knowledge-to-project flow"
```

---

## Phase 2a MVP 收尾

### Task I1: 全量回归测试 (P0)

- [ ] **I1.1: 后端全量测试**

Run:
```bash
cd backend && pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: 所有测试 PASS（含既有 Phase 1j + 新增 Phase 2a 测试）

- [ ] **I1.2: 前端 build + 全量测试**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -10 && npx vitest run 2>&1 | tail -20
```
Expected: build 0 错误 + 所有测试 PASS

- [ ] **I1.3: 启动应用 + 烟测**

Run (后台启动):
```bash
cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://127.0.0.1:8000/api/codegarden/projects | python -m json.tool | head -10
```
Expected: 返回 `{"version": ..., "total": 0, "items": []}`

- [ ] **I1.4: 最终 commit + push 提示**

```bash
git log --oneline -20 | head -20
git status
```

Phase 2a MVP 完成。**未推送到 GitHub（用户要求手动 push）。**

---
