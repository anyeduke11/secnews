"""Phase 36 待办 (Todos) API 端点

路由清单
--------
- ``GET    /api/todos``                          列表 + 多维筛选
- ``GET    /api/todos/count``                    按 status/priority 统计
- ``GET    /api/todos/available_favorites``      列出「已收藏但未入 todo」项
- ``POST   /api/todos``                          创建 (favorite-source 重复幂等)
- ``PATCH  /api/todos/{id}``                     部分更新 + 状态迁移时间戳
- ``DELETE /api/todos/{id}``                     硬删除

错误约定
--------
- 400: 参数不合法 (空 title / 未知 source_type / 非法 status / 非法 limit)
- 404: todo 不存在
- 500: DB 异常
- 中文 message, 结构化 ``{"message": "..."}`` 走 HotspotException 体系

异步策略
--------
所有同步 DB 操作通过 ``asyncio.to_thread`` 包装, 避免阻塞 event loop,
与 favorites / history API 保持一致。

Phase 46: 紧急自动判断
---------------------
- ``POST/PATCH`` 不再接受 ``urgent`` 字段, 紧急由 ``deadline`` 派生。
- 提交字段: ``title`` + ``important`` + ``deadline`` + ``note``。
- 响应中 ``urgent`` 仍返回 (effective_urgent), 前端无需改。
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.exceptions import InvalidParamException
from backend.logging_config import logger
from backend.repository.todo_repo import (
    VALID_SOURCE_TYPES,
    VALID_STATUSES,
    TodoRepository,
)

router = APIRouter(prefix="/api/todos", tags=["todos"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AddTodoRequest(BaseModel):
    """添加 todo 请求体 (Phase 46)。

    - ``title``: manual 时必填 (内部校验); favorite 时可选 (会被 favorites
      快照覆盖, 占位即可)。
    - ``deadline``: 截止日期 'YYYY-MM-DD' (可选); 用于自动判断紧急。
    - ``important``: 0/1, 用户主动决定。
    - ``urgent`` 已移除 — 由 ``deadline`` 派生, 紧急阈值 ≤ 1 业务日。
    """

    source_type: str = Field(..., description="'favorite' 或 'manual'")
    source_id: Optional[str] = Field(None, max_length=128, description="favorite 时必填")
    title: Optional[str] = Field(None, max_length=500, description="todo 标题; manual 必填")
    url: Optional[str] = Field(None, max_length=2000)
    source: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=50)
    # Phase 46: ``urgent`` 移除; ``deadline`` 替代
    important: int = Field(0, ge=0, le=1, description="0/1")
    deadline: Optional[str] = Field(
        None, max_length=10, description="截止日期 'YYYY-MM-DD'"
    )
    note: Optional[str] = Field(None, description="备注")


class PatchTodoRequest(BaseModel):
    """部分更新 todo 请求体 (Phase 46)。"""

    important: Optional[int] = Field(None, ge=0, le=1)
    deadline: Optional[str] = Field(
        None, max_length=10, description="截止日期 'YYYY-MM-DD'; 空字符串清空"
    )
    status: Optional[str] = Field(None)
    note: Optional[str] = Field(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _validate_source_type(source_type: str) -> str:
    if not source_type or source_type not in VALID_SOURCE_TYPES:
        valid = ", ".join(repr(s) for s in VALID_SOURCE_TYPES)
        raise HTTPException(
            status_code=400,
            detail={"message": f"source_type 必须为 {valid}; got {source_type!r}"},
        )
    return source_type


def _validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        valid = ", ".join(repr(s) for s in VALID_STATUSES)
        raise HTTPException(
            status_code=400,
            detail={"message": f"status 必须为 {valid}; got {status!r}"},
        )
    return status


def _validate_deadline(deadline: Optional[str]) -> Optional[str]:
    """校验 deadline 格式 'YYYY-MM-DD'。空字符串 → None (清空)。"""
    if deadline is None:
        return None
    s = deadline.strip()
    if not s:
        return None
    from datetime import date
    try:
        date.fromisoformat(s)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"message": f"deadline 格式必须为 'YYYY-MM-DD'; got {deadline!r}"},
        )
    return s


def _build_list_payload(
    status: Optional[str],
    urgent: Optional[int],
    important: Optional[int],
    limit: int,
) -> dict:
    if status is not None and status != "":
        # 校验 status
        if status not in VALID_STATUSES:
            raise InvalidParamException(
                f"status 必须为 {', '.join(VALID_STATUSES)}; got {status!r}"
            )
    repo = TodoRepository()
    items, total = repo.list(
        status=status if status else None,
        urgent=urgent,
        important=important,
        limit=limit,
    )
    return {
        "version": "1.2.0",
        "total": total,
        "items": [it.to_dict() for it in items],
    }


def _build_count_payload() -> dict:
    repo = TodoRepository()
    counts = repo.count()
    return {
        "version": "1.2.0",
        "total": counts["total"],
        "by_status": counts["by_status"],
        "by_priority": counts["by_priority"],
    }


def _build_available_favorites_payload(limit: int) -> dict:
    repo = TodoRepository()
    items = repo.list_available_favorites(limit=limit)
    return {
        "version": "1.2.0",
        "total": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_todos(
    status: Optional[str] = Query(None, description="状态筛选: open/done/archived"),
    urgent: Optional[int] = Query(None, ge=0, le=1, description="紧急筛选 0/1"),
    important: Optional[int] = Query(None, ge=0, le=1, description="重要筛选 0/1"),
    limit: int = Query(200, ge=1, le=1000, description="最多返回条数"),
):
    """多维筛选 todos。排序: urgent DESC → important DESC → created_at DESC。"""
    try:
        return await asyncio.to_thread(
            _build_list_payload, status, urgent, important, limit
        )
    except InvalidParamException as e:
        raise HTTPException(status_code=400, detail={"message": e.message})
    except Exception as e:
        logger.error(f"list todos failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"列表失败: {e}"})


@router.get("/count")
async def count_todos():
    """按 status / priority 4 象限 + total 统计。"""
    try:
        return await asyncio.to_thread(_build_count_payload)
    except Exception as e:
        logger.error(f"count todos failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"统计失败: {e}"})


@router.get("/available_favorites")
async def list_available_favorites(
    limit: int = Query(200, ge=1, le=1000, description="最多返回条数"),
):
    """列出「已收藏但未进 todo」的 favorites 项 (备用入口)。"""
    try:
        return await asyncio.to_thread(_build_available_favorites_payload, limit)
    except Exception as e:
        logger.error(f"list available_favorites failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"列表失败: {e}"})


@router.post("")
async def add_todo(req: AddTodoRequest):
    """创建 todo。

    - favorite-source 重复 → 200 + created=false + 已存在 todo
    - 其他 (manual / 新 favorite) → 201 + created=true + 新 todo
    - title 必填规则: manual 必填; favorite 可选 (从 favorites 表快照)
    """
    source_type = _validate_source_type(req.source_type)
    if source_type == "favorite" and not (req.source_id and req.source_id.strip()):
        raise HTTPException(
            status_code=400,
            detail={"message": "source_id 不能为空 (source_type=favorite 时必填)"},
        )
    if source_type == "manual" and (not req.title or not req.title.strip()):
        raise HTTPException(
            status_code=400,
            detail={"message": "title 不能为空 (source_type=manual 时必填)"},
        )
    # favorite 路径: req.title 可空, repo.add_or_get 会从 favorites 表派生

    repo = TodoRepository()
    deadline = _validate_deadline(req.deadline)
    try:
        item, created = await asyncio.to_thread(
            repo.add_or_get,
            source_type=source_type,
            source_id=req.source_id.strip() if req.source_id else None,
            title=req.title.strip() if req.title else None,
            url=req.url,
            source=req.source,
            category=req.category,
            important=int(req.important or 0),
            deadline=deadline,
            note=req.note,
        )
    except Exception as e:
        logger.error(f"add todo failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"添加失败: {e}"})

    payload = {
        "version": "1.2.0",
        "created": created,
        "item": item.to_dict(),
    }
    # 201 = 新建; 200 = 已存在 (幂等 upsert)
    status_code = 201 if created else 200
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


@router.patch("/{todo_id}")
async def patch_todo(todo_id: int, req: PatchTodoRequest):
    """部分更新 todo + 状态迁移时间戳维护。

    Phase 46: ``urgent`` 字段移除, 紧急由 deadline 派生。
    """
    if req.status is not None:
        _validate_status(req.status)
    if req.important is not None and req.important not in (0, 1):
        raise HTTPException(status_code=400, detail={"message": "important 必须为 0 或 1"})

    deadline: Optional[str] = None
    deadline_set: bool = False  # Phase 46: 显式标记字段已传入
    if "deadline" in req.model_fields_set:
        # 显式传了 deadline (包括空字符串清空)
        deadline_set = True
        deadline = _validate_deadline(req.deadline)

    repo = TodoRepository()
    try:
        item = await asyncio.to_thread(
            repo.update,
            int(todo_id),
            important=req.important,
            deadline=deadline,
            deadline_set=deadline_set,
            status=req.status,
            note=req.note,
        )
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail={"message": f"todo {todo_id} 不存在"})
        logger.error(f"update todo failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"更新失败: {e}"})

    return {
        "version": "1.2.0",
        "item": item.to_dict(),
    }


@router.delete("/{todo_id}", status_code=204)
async def delete_todo(todo_id: int):
    """硬删除 todo。返回 204 (无论是否原本存在 — DELETE 是 idempotent)。"""
    repo = TodoRepository()
    try:
        deleted = await asyncio.to_thread(repo.delete, int(todo_id))
    except Exception as e:
        logger.error(f"delete todo failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"删除失败: {e}"})
    # 204 不应返回 body; 即便原本不存在也返回 204 保持幂等
    return Response(status_code=204)


__all__ = ["router"]
