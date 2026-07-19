"""Phase 2a CodeGarden API 端点.

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
    """从 GitHub URL 导入项目（拉 repo metadata + upstream）.

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
    """从 knowledge_item 一键创建 cg_projects 记录 (幂等).

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
