"""Phase 2b CodeGarden API 端点 — 服务网格 + 资源中枢 + 联动引擎.

路由清单 (spec §4)
-----------------
M2 服务网格 (9 端点):
- GET    /api/codegarden/services                 列表 (筛选 project_id/status/namespace/type/runtime/keyword)
- POST   /api/codegarden/services                 创建
- GET    /api/codegarden/services/{id}            详情
- PATCH  /api/codegarden/services/{id}            更新
- DELETE /api/codegarden/services/{id}            删除
- POST   /api/codegarden/services/scan            触发自动发现扫描
- POST   /api/codegarden/services/{id}/restart    创建重启任务
- GET    /api/codegarden/services/{id}/logs?tail=100  获取日志
- GET    /api/codegarden/services/{id}/metrics    获取指标
- GET    /api/codegarden/services/topology        服务拓扑图 (React Flow)

M3 资源中枢 (8 端点):
- GET    /api/codegarden/resources                列表 (筛选 type/status/owner)
- POST   /api/codegarden/resources                创建
- GET    /api/codegarden/resources/{id}           详情
- DELETE /api/codegarden/resources/{id}           删除
- POST   /api/codegarden/resources/allocate-port  智能分配端口
- POST   /api/codegarden/resources/release-port   释放端口 (8898 返回 403)
- POST   /api/codegarden/resources/env-templates  保存环境变量模板 (敏感字段加密)
- GET    /api/codegarden/resources/env-templates/{id}  加载并解密模板

M4 联动引擎 (8 端点):
- GET    /api/codegarden/dependencies             列表 (筛选 source/target/dep_type)
- POST   /api/codegarden/dependencies             创建
- DELETE /api/codegarden/dependencies/{id}        删除
- GET    /api/codegarden/dependencies/impact?target_type=&target_id=  影响分析
- GET    /api/codegarden/events                   事件列表
- POST   /api/codegarden/events                   发布事件
- GET    /api/codegarden/playbooks                Playbook 列表
- POST   /api/codegarden/playbooks/{name}/run     执行 Playbook

设计原则
--------
- 同步 DB 操作通过 asyncio.to_thread 包装
- 8898 端口保护返回 403 (从 InternalException 捕获)
- 错误统一用 HTTPException + 中文 message
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_orchestration_repo import (
    VALID_DEP_ENTITY_TYPES,
    VALID_DEP_TYPES,
    VALID_EVENT_SOURCES,
    VALID_EVENT_STATUSES,
    VALID_EVENT_TYPES,
)
from backend.repository.codegarden_resource_repo import (
    PROTECTED_PORTS,
    VALID_RESOURCE_STATUSES,
    VALID_RESOURCE_TYPES,
)
from backend.repository.codegarden_service_repo import (
    VALID_HEALTH_CHECK_TYPES,
    VALID_RUNTIMES,
    VALID_SERVICE_STATUSES,
    VALID_SERVICE_TYPES,
)
from backend.services.codegarden_orchestration_service import (
    CodegardenOrchestrationService,
)
from backend.services.codegarden_resource_service import CodegardenResourceService
from backend.services.codegarden_service_service import CodegardenServiceService

router = APIRouter(prefix="/api/codegarden", tags=["codegarden-phase2b"])


# ===========================================================================
# Request / Response models
# ===========================================================================
class CreateServiceRequest(BaseModel):
    name: str = Field(..., max_length=200, description="服务名 (必填)")
    type: str = Field(..., description=f"类型: {', '.join(VALID_SERVICE_TYPES)}")
    runtime: str = Field(..., description=f"运行时: {', '.join(VALID_RUNTIMES)}")
    status: str = Field("unknown", description=f"状态: {', '.join(VALID_SERVICE_STATUSES)}")
    project_id: Optional[str] = None
    namespace: Optional[str] = None
    endpoint_host: Optional[str] = None
    endpoint_port: Optional[int] = None
    endpoint_domain: Optional[str] = None
    health_check_type: Optional[str] = None
    health_check_path: Optional[str] = None
    health_check_interval: int = Field(30, ge=5, le=3600)
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    dependencies: list[str] = Field(default_factory=list)
    env_vars: dict = Field(default_factory=dict)


class PatchServiceRequest(BaseModel):
    name: Optional[str] = None
    namespace: Optional[str] = None
    type: Optional[str] = None
    runtime: Optional[str] = None
    status: Optional[str] = None
    endpoint_host: Optional[str] = None
    endpoint_port: Optional[int] = None
    endpoint_domain: Optional[str] = None
    health_check_type: Optional[str] = None
    health_check_path: Optional[str] = None
    health_check_interval: Optional[int] = Field(None, ge=5, le=3600)
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    project_id: Optional[str] = None


class CreateResourceRequest(BaseModel):
    type: str = Field(..., description=f"类型: {', '.join(VALID_RESOURCE_TYPES)}")
    value: str = Field(..., description="值 (端口号/域名/模板名/卷名)")
    status: str = Field("free", description=f"状态: {', '.join(VALID_RESOURCE_STATUSES)}")
    owner_service_id: Optional[str] = None
    owner_project_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    reserved_until: Optional[str] = None


class AllocatePortRequest(BaseModel):
    preferred_port: Optional[int] = Field(None, ge=1, le=65535, description="期望端口 (可选)")
    owner_service_id: Optional[str] = None
    owner_project_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ReleasePortRequest(BaseModel):
    port: int = Field(..., ge=1, le=65535)


class SaveEnvTemplateRequest(BaseModel):
    name: str = Field(..., max_length=100, description="模板名 (如 production/development)")
    env_vars: dict = Field(..., description="环境变量字典")
    owner_project_id: Optional[str] = None


class CreateDependencyRequest(BaseModel):
    source_type: str = Field(..., description=f"源类型: {', '.join(VALID_DEP_ENTITY_TYPES)}")
    source_id: str = Field(..., description="源 ID")
    target_type: str = Field(..., description=f"目标类型: {', '.join(VALID_DEP_ENTITY_TYPES)}")
    target_id: str = Field(..., description="目标 ID")
    dep_type: str = Field(..., description=f"依赖类型: {', '.join(VALID_DEP_TYPES)}")
    metadata: dict = Field(default_factory=dict)


class PublishEventRequest(BaseModel):
    event_type: str = Field(..., description=f"事件类型: {', '.join(VALID_EVENT_TYPES)}")
    source_type: str = Field(..., description=f"源类型: {', '.join(VALID_EVENT_SOURCES)}")
    source_id: str = Field(..., description="源 ID")
    payload: dict = Field(default_factory=dict)


class RunPlaybookRequest(BaseModel):
    params: dict = Field(default_factory=dict)


# ===========================================================================
# M2 服务网格 (10 端点)
# ===========================================================================
@router.get("/services")
async def list_services(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    namespace: Optional[str] = None,
    type: Optional[str] = None,
    runtime: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """M2-1: 服务列表."""
    svc = CodegardenServiceService()
    services, total = await asyncio.to_thread(
        svc.list_services,
        project_id=project_id, status=status, namespace=namespace,
        type=type, runtime=runtime, keyword=keyword,
        limit=limit, offset=offset,
    )
    return {"items": services, "total": total, "limit": limit, "offset": offset}


@router.post("/services")
async def create_service(req: CreateServiceRequest, response: Response):
    """M2-2: 创建服务."""
    svc = CodegardenServiceService()
    try:
        service = await asyncio.to_thread(svc.create_service, **req.model_dump())
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.status_code = 201
    return service


@router.get("/services/topology")
async def get_topology():
    """M2-3: 服务拓扑图 (React Flow nodes + edges)."""
    svc = CodegardenServiceService()
    return await asyncio.to_thread(svc.get_topology)


@router.get("/services/{service_id}")
async def get_service(service_id: str):
    """M2-4: 服务详情."""
    svc = CodegardenServiceService()
    service = await asyncio.to_thread(svc.get_service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail=f"service {service_id} 不存在")
    return service


@router.patch("/services/{service_id}")
async def update_service(service_id: str, req: PatchServiceRequest):
    """M2-5: 更新服务."""
    svc = CodegardenServiceService()
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="无更新字段")
    try:
        return await asyncio.to_thread(svc.update_service, service_id, **fields)
    except InternalException as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))


@router.delete("/services/{service_id}")
async def delete_service(service_id: str):
    """M2-6: 删除服务."""
    svc = CodegardenServiceService()
    ok = await asyncio.to_thread(svc.delete_service, service_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"service {service_id} 不存在")
    return {"deleted": True, "id": service_id}


@router.post("/services/scan")
async def scan_services():
    """M2-7: 触发自动发现扫描 (lsof + docker + pm2)."""
    svc = CodegardenServiceService()
    return await asyncio.to_thread(svc.scan_local_services)


@router.post("/services/{service_id}/restart")
async def restart_service(service_id: str, response: Response):
    """M2-8: 创建服务重启任务 (task_type=service_restart)."""
    svc = CodegardenServiceService()
    try:
        result = await asyncio.to_thread(svc.restart_service, service_id)
    except InternalException as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))
    response.status_code = 202
    return result


@router.get("/services/{service_id}/logs")
async def get_service_logs(service_id: str, tail: int = Query(100, ge=1, le=1000)):
    """M2-9: 获取服务日志."""
    svc = CodegardenServiceService()
    try:
        return await asyncio.to_thread(svc.get_logs, service_id, tail)
    except InternalException as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))


@router.get("/services/{service_id}/metrics")
async def get_service_metrics(service_id: str):
    """M2-10: 获取服务指标."""
    svc = CodegardenServiceService()
    try:
        return await asyncio.to_thread(svc.get_metrics, service_id)
    except InternalException as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))


# ===========================================================================
# M3 资源中枢 (8 端点)
# ===========================================================================
@router.get("/resources")
async def list_resources(
    type: Optional[str] = None,
    status: Optional[str] = None,
    owner_service_id: Optional[str] = None,
    owner_project_id: Optional[str] = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """M3-1: 资源列表."""
    rsc = CodegardenResourceService()
    items, total = await asyncio.to_thread(
        rsc.list_resources,
        type=type, status=status,
        owner_service_id=owner_service_id, owner_project_id=owner_project_id,
        limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/resources")
async def create_resource(req: CreateResourceRequest, response: Response):
    """M3-2: 创建资源."""
    rsc = CodegardenResourceService()
    try:
        resource = await asyncio.to_thread(rsc.create_resource, **req.model_dump())
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.status_code = 201
    return resource


@router.get("/resources/env-templates")
async def list_env_templates():
    """M3-3: 列出环境变量模板."""
    rsc = CodegardenResourceService()
    return {"items": await asyncio.to_thread(rsc.list_env_templates)}


@router.get("/resources/{resource_id}")
async def get_resource(resource_id: str):
    """M3-4: 资源详情."""
    rsc = CodegardenResourceService()
    resource = await asyncio.to_thread(rsc.get_resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail=f"resource {resource_id} 不存在")
    return resource


@router.delete("/resources/{resource_id}")
async def delete_resource(resource_id: str):
    """M3-5: 删除资源."""
    rsc = CodegardenResourceService()
    ok = await asyncio.to_thread(rsc.delete_resource, resource_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"resource {resource_id} 不存在")
    return {"deleted": True, "id": resource_id}


@router.post("/resources/allocate-port")
async def allocate_port(req: AllocatePortRequest, response: Response):
    """M3-6: 智能分配端口 (避开 cg_resources 已分配 + lsof 实时占用 + 8898 保护)."""
    rsc = CodegardenResourceService()
    try:
        resource = await asyncio.to_thread(
            rsc.allocate_port,
            owner_service_id=req.owner_service_id,
            owner_project_id=req.owner_project_id,
            preferred_port=req.preferred_port,
            metadata=req.metadata,
        )
    except InternalException as e:
        msg = str(e)
        # 8898 保护 / 已分配 / lsof 占用 均返回 403 或 409
        if "受保护" in msg:
            raise HTTPException(status_code=403, detail=msg)
        if "已被" in msg or "已满" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    response.status_code = 201
    return resource


@router.post("/resources/release-port")
async def release_port(req: ReleasePortRequest):
    """M3-7: 释放端口 (8898 返回 403)."""
    rsc = CodegardenResourceService()
    try:
        resource = await asyncio.to_thread(rsc.release_port, req.port)
    except InternalException as e:
        msg = str(e)
        if "受保护" in msg:
            raise HTTPException(status_code=403, detail=msg)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return resource


@router.post("/resources/env-templates")
async def save_env_template(req: SaveEnvTemplateRequest, response: Response):
    """M3-8: 保存环境变量模板 (敏感字段 Fernet 加密)."""
    rsc = CodegardenResourceService()
    try:
        resource = await asyncio.to_thread(
            rsc.save_env_template,
            name=req.name, env_vars=req.env_vars,
            owner_project_id=req.owner_project_id,
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.status_code = 201
    return resource


@router.get("/resources/env-templates/{resource_id}")
async def load_env_template(resource_id: str):
    """M3-9: 加载并解密环境变量模板."""
    rsc = CodegardenResourceService()
    try:
        return await asyncio.to_thread(rsc.load_env_template, resource_id)
    except InternalException as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))


# ===========================================================================
# M4 联动引擎 (8 端点)
# ===========================================================================
@router.get("/dependencies")
async def list_dependencies(
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    dep_type: Optional[str] = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """M4-1: 依赖列表."""
    orch = CodegardenOrchestrationService()
    items, total = await asyncio.to_thread(
        orch.list_dependencies,
        source_type=source_type, source_id=source_id,
        target_type=target_type, target_id=target_id, dep_type=dep_type,
        limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/dependencies")
async def create_dependency(req: CreateDependencyRequest, response: Response):
    """M4-2: 创建依赖."""
    orch = CodegardenOrchestrationService()
    try:
        dep = await asyncio.to_thread(orch.create_dependency, **req.model_dump())
    except InternalException as e:
        msg = str(e)
        if "已存在" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    response.status_code = 201
    return dep


@router.delete("/dependencies/{dep_id}")
async def delete_dependency(dep_id: str):
    """M4-3: 删除依赖."""
    orch = CodegardenOrchestrationService()
    ok = await asyncio.to_thread(orch.delete_dependency, dep_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"dependency {dep_id} 不存在")
    return {"deleted": True, "id": dep_id}


@router.get("/dependencies/impact")
async def impact_analysis(
    target_type: str = Query(..., description=f"目标类型: {', '.join(VALID_DEP_ENTITY_TYPES)}"),
    target_id: str = Query(..., description="目标 ID"),
    max_depth: int = Query(10, ge=1, le=50),
):
    """M4-4: 影响分析 — 反向追溯所有上游 source."""
    orch = CodegardenOrchestrationService()
    impacts = await asyncio.to_thread(
        orch.impact_analysis,
        target_type=target_type, target_id=target_id, max_depth=max_depth,
    )
    return {"target_type": target_type, "target_id": target_id, "impacts": impacts, "count": len(impacts)}


@router.get("/events")
async def list_events(
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """M4-5: 事件列表."""
    orch = CodegardenOrchestrationService()
    items, total = await asyncio.to_thread(
        orch.list_events,
        event_type=event_type, status=status,
        source_type=source_type, source_id=source_id,
        limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/events")
async def publish_event(req: PublishEventRequest, response: Response):
    """M4-6: 发布事件 (写 cg_events + 创建 event_handler task)."""
    orch = CodegardenOrchestrationService()
    try:
        result = await asyncio.to_thread(
            orch.publish_event,
            event_type=req.event_type, source_type=req.source_type,
            source_id=req.source_id, payload=req.payload,
        )
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    response.status_code = 201
    return result


@router.get("/playbooks")
async def list_playbooks():
    """M4-7: Playbook 列表 (扫 codegarden/playbooks/*.yml)."""
    orch = CodegardenOrchestrationService()
    items = await asyncio.to_thread(orch.list_playbooks)
    return {"items": items, "count": len(items)}


@router.post("/playbooks/{name}/run")
async def run_playbook(name: str, req: RunPlaybookRequest, response: Response):
    """M4-8: 执行 Playbook (创建 playbook_run task)."""
    orch = CodegardenOrchestrationService()
    try:
        result = await asyncio.to_thread(orch.run_playbook, name, req.params)
    except InternalException as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    response.status_code = 202
    return result


__all__ = ["router"]
