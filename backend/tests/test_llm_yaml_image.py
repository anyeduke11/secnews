"""S1 验证 — llm.yaml image_generation override 解析 (v0.7.4-image).

不依赖 _route_model: 直接断言 config schema + yaml 解析字段,
保证 yaml 是单一真相源,代码侧不需要二次硬编码。
"""
from __future__ import annotations

from backend.config.llm_schema import load_llm_config


def test_sensenova_image_field_resolves_to_u1_5_lite():
    """sensenova.models.image = sensenova-u1.5-lite (本批新增字段)."""
    cfg = load_llm_config()
    assert cfg is not None, "llm.yaml 缺失, 走 v1.7 兼容模式"
    sensenova = cfg.providers["sensenova"]
    assert sensenova.models.image == "sensenova-u1.5-lite", (
        f"image 字段应为 sensenova-u1.5-lite, 实际 {sensenova.models.image!r}"
    )


def test_image_generation_task_override_resolves():
    """task_overrides.image_generation.provider=sensenova, model=u1.5-lite."""
    cfg = load_llm_config()
    assert cfg is not None
    assert cfg.task_overrides is not None
    img = cfg.task_overrides.get("image_generation")
    assert img is not None, "image_generation override 缺失"
    assert img.provider == "sensenova"
    assert img.model == "sensenova-u1.5-lite"
    assert img.watermark is False, "公测期 watermark 默认 false"
    assert img.size == "1024x1024"
    assert img.n == 1


def test_t3_summary_override_upgraded_to_deepseek_v4_pro():
    """S1: t3_summary.model 由 flash-lite 升 deepseek-v4-pro (yaml-only, deep_read 自动升级)."""
    cfg = load_llm_config()
    assert cfg is not None
    assert cfg.task_overrides is not None
    t3 = cfg.task_overrides.get("t3_summary")
    assert t3 is not None
    assert t3.provider == "sensenova"
    assert t3.model == "deepseek-v4-pro", (
        f"t3_summary.model 应为 deepseek-v4-pro, 实际 {t3.model!r}"
    )
