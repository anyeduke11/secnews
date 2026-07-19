"""Phase 2a CodeGarden 知识桥接服务 — 资讯 → 项目转化通道.

职责
----
- list_candidates(): 列出 type=github 且未转化的 knowledge_items (候选二开源)
- find_existing_project(item_id): 幂等检查, 返回已转化的 project (或 None)
- create_from_knowledge(item_id, source_type, local_path):
    从 knowledge_item 一键创建 cg_projects 记录,
    写入 source_item_id 反向溯源,
    更新 knowledge_items frontmatter project_id 字段
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_repo import CodegardenProjectRepository
from backend.repository.db import get_connection
from backend.services.knowledge_sync import ITEMS_DIR


class CodegardenKnowledgeBridge:
    """资讯→项目转化服务。"""

    def __init__(self) -> None:
        self.repo = CodegardenProjectRepository()

    # ------------------------------------------------------------------
    # 候选源列表
    # ------------------------------------------------------------------
    def list_candidates(self, limit: int = 100) -> list[dict]:
        """列出 type=github 的 knowledge_items 中尚未转化的（无 project_id）.

        返回字段: id, title, source_url, domain, topic, ingested_at, updated_at
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
        """若 knowledge_item 已转化为 cg_projects, 返回既有 project; 否则 None.

        用于 from-knowledge 端点幂等校验 (首次 201 / 重复 200)。
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM cg_projects WHERE source_item_id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return self.repo.get(str(row["id"]))

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
        """从 knowledge_item 创建 cg_projects 记录.

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
        """在 knowledge/items/{item_id}.md frontmatter 中写入 project_id 字段.

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
