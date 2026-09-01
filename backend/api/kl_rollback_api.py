"""v0.5+: KL (Knowledge Lifecycle) 回滚 API.

提供 /api/kl/rollback 端点, 调用 T5PublishToRefine trigger 把 KL 状态从
PUBLISHED 回滚到 REFINING (用于 Batch ⑦ T5 假象兜底).
"""
from fastapi import APIRouter, HTTPException

from backend.services.triggers.t5_publish_to_refine import T5Trigger

router = APIRouter(prefix="/api/kl", tags=["kl"])


@router.post("/rollback/{item_id}")
async def rollback_knowledge_item(item_id: str):
    """User-initiated rollback of a knowledge item from kl:publish to kl:refine.

    The item's .md file is backed up to knowledge/backups/ before rollback.
    """
    trigger = T5Trigger()
    try:
        result = trigger.rollback(item_id)
        return {"status": "ok", "result": result}
    except ValueError as e:
        # Item not found or not in publish state
        raise HTTPException(status_code=400, detail={"message": str(e)})