"""S5 验证 — model_router IMAGE 档 (v0.7.4-image).

- image_generation task → IMAGE tier
- image_understand task → IMAGE tier
- 路由命中 yaml task_overrides.image_generation
- 兜底 → (sensenova, sensenova-u1.5-lite)
"""
from __future__ import annotations

from backend.config.llm_schema import load_llm_config
from backend.services.llm.model_router import (
    ModelTier,
    TASK_TIER_MAP,
    TIER_TO_MODEL_ATTR,
    TIER_TO_OVERRIDE_KEY,
    _fallback,
    get_tier,
    route_model,
)


def test_image_generation_task_maps_to_image_tier():
    assert TASK_TIER_MAP["image_generation"] == ModelTier.IMAGE
    assert TASK_TIER_MAP["image_understand"] == ModelTier.IMAGE
    assert get_tier("image_generation") == ModelTier.IMAGE
    assert get_tier("image_understand") == ModelTier.IMAGE


def test_image_tier_routes_via_yaml_override():
    """有 yaml 时: task_overrides.image_generation → (sensenova, sensenova-u1.5-lite)."""
    cfg = load_llm_config()
    assert cfg is not None and cfg.task_overrides is not None
    routed = route_model("image_generation", config=cfg)
    assert routed == ("sensenova", "sensenova-u1.5-lite"), (
        f"期望 yaml override, 实际 {routed}"
    )
    routed_u = route_model("image_understand", config=cfg)
    assert routed_u == ("sensenova", "sensenova-u1.5-lite"), (
        f"image_understand 应同 image_generation, 实际 {routed_u}"
    )


def test_image_tier_fallback_when_no_yaml():
    """无 yaml: 兜底 → (sensenova, sensenova-u1.5-lite)."""
    assert TIER_TO_OVERRIDE_KEY[ModelTier.IMAGE] == "image_generation"
    assert TIER_TO_MODEL_ATTR[ModelTier.IMAGE] == "image"
    assert _fallback(ModelTier.IMAGE) == ("sensenova", "sensenova-u1.5-lite")
