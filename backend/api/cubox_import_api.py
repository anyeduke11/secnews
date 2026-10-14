"""UI 收尾批 C2 (DEV-0195) — cubox 导入兜底 API (CLI 导出 JSON / 本地目录)。

背景: 在线同步 (``POST /api/knowledge/sync``) 依赖后端进程能找到 cubox-cli,
PATH/认证异常即静默 0 条; 本文件提供两条人工兜底导入路径。

路由清单 (prefix 自带, 挂 knowledge 聚合层惯例)
--------
- ``POST /api/knowledge/cubox/import-cards``  导入 CLI 导出的卡片 JSON 数组
- ``POST /api/knowledge/cubox/import-dir``    扫描本地目录 (*.json + 递归 *.md) 导入
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.exceptions import InvalidParamException

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class CuboxCardsIn(BaseModel):
    """CLI 导出卡片批量导入请求体 (即 cubox-cli card list -o json 的输出数组)。"""

    cards: list[dict]


class CuboxDirIn(BaseModel):
    """本地目录导入请求体。"""

    path: str = Field(min_length=1)


@router.post("/cubox/import-cards")
async def import_cubox_cards_endpoint(body: CuboxCardsIn) -> dict:
    """导入 cubox CLI 导出的卡片 JSON (同步直导, ≤5000 条, 不走异步任务)。"""
    from backend.services.cubox_sync import import_cubox_cards

    if len(body.cards) > 5000:
        raise InvalidParamException("单次导入上限 5000 条 (请分批)")
    result = import_cubox_cards(body.cards)
    return {"imported": result["total"], **result}


@router.post("/cubox/import-dir")
async def import_cubox_dir_endpoint(body: CuboxDirIn) -> dict:
    """扫描本地目录中的 cubox 卡片并导入 (顶层 ``*.json`` + 递归 ``*.md``)。

    ``*.json`` = cubox-cli 导出数组; ``*.md`` = cubox 本地化知识库卡片,
    按 frontmatter (``source_url``/``url`` + ``title`` + ``tags``) 反解。
    路径校验: 绝对路径 + 存在目录。本地运维导入 (非出站请求, 无 SSRF 面)。
    """
    from backend.services.cubox_sync import import_cubox_dir

    try:
        return await asyncio.to_thread(import_cubox_dir, body.path.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


__all__ = ["router"]
