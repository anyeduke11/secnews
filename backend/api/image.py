"""图片生成 + 图理解 API (v0.7.4-image).

- POST /api/image/generate: 文生图 → {ok, images, provider, model, latency_ms}
- POST /api/image/understand: 图理解 → {ok, text, provider, model, latency_ms}

复用 Batch ⑥ 已落的 AIService 单点四级链 (凭据解析与密钥打标);
复用现有 record_audit 模板 (observability_records.record_audit).
不入 feature gate (sensenova 凭据空时自然 fail-soft 返 ok=false).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.ai_hub.image_service import (
    ImageGenerationError,
    ImageGenerationService,
)

router = APIRouter(prefix="/api/image", tags=["image"])


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    size: str = Field("1024x1024", description="WIDTHxHEIGHT, sensenova u1.5-lite 支持档位")
    n: int = Field(1, ge=1, le=4, description="生成数量 (公测期免费, 上限 4)")
    watermark: bool = Field(False, description="true 才加水印 (计费)")
    actor: str = Field("web", description="审计记录操作者")


class UnderstandRequest(BaseModel):
    image_b64: str = Field(..., min_length=10, max_length=8 * 1024 * 1024)
    prompt: str = Field(..., min_length=1, max_length=2000)
    actor: str = Field("web")


@router.post("/generate")
async def generate_image(body: GenerateRequest):
    svc = ImageGenerationService()
    try:
        result = await svc.generate(
            body.prompt, size=body.size, n=body.n, watermark=body.watermark,
        )
        _audit("image.generate", body.actor, {"ok": True, "model": result["model"]})
        return result
    except ImageGenerationError as e:
        _audit("image.generate", body.actor, {"ok": False, "error": str(e)[:200]})
        return {"ok": False, "error": str(e)[:300]}


@router.post("/understand")
async def understand_image(body: UnderstandRequest):
    svc = ImageGenerationService()
    try:
        result = await svc.understand(body.image_b64, body.prompt)
        _audit("image.understand", body.actor, {"ok": True, "model": result["model"]})
        return result
    except ImageGenerationError as e:
        _audit("image.understand", body.actor, {"ok": False, "error": str(e)[:200]})
        return {"ok": False, "error": str(e)[:300]}


def _audit(action: str, actor: str, detail: dict) -> None:
    """审计写入 — 复用 observability_records.record_audit 模板, 异常 swallow 不阻塞业务."""
    try:
        from backend.observability_records import record_audit
        record_audit(actor=actor, action=action, detail=detail)
    except Exception:
        pass


__all__ = ["router"]
