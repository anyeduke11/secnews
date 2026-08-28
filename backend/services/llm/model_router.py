"""Model router — 模型分层路由 (S4-1)。

按 ``task_type`` → ``ModelTier`` → ``(provider, model)`` 路由。
两种调用路径:

1. **注入 config** (推荐, ai_hub 走这条): ``route_model(task, config=cfg)`` —
   复用 ai_hub 已持有的 LLMConfig, 不二次 IO; 优先 ``task_overrides[override_key]``
   再退 ``fallback_order[0]`` 的 ``models.{score|summary}``。
2. **自行 yaml 解析** (无注入时回退): 直接读 ``config/llm.yaml``, 旧行为不变。

设计取舍 (S4-1 commit 1):
- **零破坏**: ai_hub 现有 5 个生产 task (score/summarize/ner/evaluate/gate_detect) 行为不变;
  router 推荐的 provider 仅作为"优先尝试项", fallback_order 仍完整遍历兜底。
- **task_overrides 激活**: 之前 ``LLMConfig.task_overrides`` 是死配置 (ai_hub 不读),
  router 接入后真正生效, 体现"flash → t3_chunk_summary"等覆盖意图。
- **TASK_TIER_MAP 补缺**: ai_hub 用的 ``ner`` / ``generate`` 原本不在 router 任务表里,
  默认走 STANDARD/FLASH, 行为安全降级而非报错。
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from backend.logging_config import logger

if TYPE_CHECKING:
    from backend.config.llm_schema import LLMConfig


class ModelTier(str, Enum):
    FLASH = "flash"          # 轻分析: refine / classify / tag / summary / brief
    STANDARD = "standard"    # 标准分析: evaluate / compare / score / ner
    HEAVY = "heavy"          # 重分析: deep_read / assess / compliance / report
    EMBED = "embed"          # 向量: embed / rerank (P3+)


# 任务类型 → 档位映射 (与 dsh-SecNews cap registry 对齐)
TASK_TIER_MAP: dict[str, ModelTier] = {
    # flash 档 — 高频轻量
    "refine": ModelTier.FLASH,
    "classify": ModelTier.FLASH,
    "tag": ModelTier.FLASH,
    "summarize": ModelTier.FLASH,
    "summary": ModelTier.FLASH,
    "brief": ModelTier.FLASH,
    "generate": ModelTier.FLASH,
    "chunk_summary": ModelTier.FLASH,
    # standard 档 — 中等复杂度
    "evaluate": ModelTier.STANDARD,
    "compare": ModelTier.STANDARD,
    "score": ModelTier.STANDARD,
    "ner": ModelTier.STANDARD,
    # heavy 档 — 点击触发
    "deep_read": ModelTier.HEAVY,
    "assess": ModelTier.HEAVY,
    "compliance": ModelTier.HEAVY,
    "report": ModelTier.HEAVY,
}


# tier → task_overrides 键的映射 (S4-1: 激活原死配置)
# task_overrides 是 LLMConfig.task_overrides 的语义层 key, 与触发阶段一一对应
TIER_TO_OVERRIDE_KEY: dict[ModelTier, str] = {
    ModelTier.FLASH: "t3_chunk_summary",
    ModelTier.STANDARD: "t1_score",
    ModelTier.HEAVY: "t3_summary",
    ModelTier.EMBED: "t3_chunk_summary",
}


# tier → ProviderModels 字段名 (兼容旧 yaml 用 score/summary 命名)
TIER_TO_MODEL_ATTR: dict[ModelTier, str] = {
    ModelTier.FLASH: "summary",
    ModelTier.STANDARD: "score",
    ModelTier.HEAVY: "summary",
    ModelTier.EMBED: "summary",
}


def get_tier(task_type: str) -> ModelTier:
    """获取任务对应的模型档位 (未知任务默认 STANDARD)。"""
    return TASK_TIER_MAP.get(task_type, ModelTier.STANDARD)


def route_model(
    task_type: str,
    config: LLMConfig | None = None,
) -> tuple[str, str]:
    """按任务类型路由到 (provider, model)。

    优先使用传入的 LLMConfig (ai_hub 持有, 避免二次 IO), 否则回退到自行 yaml 解析。
    全部失败时返回硬编码兜底 ``_fallback(tier)``。
    """
    tier = get_tier(task_type)

    if config is not None:
        try:
            return _route_from_config(config, tier)
        except Exception as e:
            logger.warning(f"route_model(_route_from_config) failed: {e}")
            return _fallback(tier)

    return _route_from_yaml(tier)


def _route_from_config(cfg: LLMConfig, tier: ModelTier) -> tuple[str, str]:
    """从注入的 LLMConfig 路由。

    优先级:
    1. ``task_overrides[TIER_TO_OVERRIDE_KEY[tier]]`` (S4-1 激活)
    2. ``fallback_order[0]`` 对应 provider 的 ``models.{TIER_TO_MODEL_ATTR[tier]}``
    3. 全失败 → ``_fallback(tier)``
    """
    override_key = TIER_TO_OVERRIDE_KEY[tier]
    if cfg.task_overrides and override_key in cfg.task_overrides:
        ov = cfg.task_overrides[override_key]
        return ov.provider, ov.model

    for pname in cfg.fallback_order or list(cfg.providers.keys()):
        p = cfg.providers.get(pname)
        if p is None:
            continue
        attr = TIER_TO_MODEL_ATTR[tier]
        model = getattr(p.models, attr, "") or ""
        if model:
            return pname, model

    return _fallback(tier)


def _route_from_yaml(tier: ModelTier) -> tuple[str, str]:
    """旧 yaml 解析路径 — 无 config 注入时使用 (向后兼容)。"""
    try:
        from pathlib import Path

        import yaml
        # S4-1 修复: 本文件在 backend/services/llm/model_router.py,
        # parent.parent 是 backend/services, 需再上一层 backend, 然后进 ../config/llm.yaml
        # 此前 parent.parent.parent 解析到 backend/services/services (不存在),
        # _route_from_yaml 静默走 _fallback(tier) → 返回 openai/gpt-4o-mini (硬编码默认值),
        # 与真实 yaml 内容无关。Phase 6 之前 model_router 是 dead code, 此 bug 一直隐藏。
        yaml_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "config"
            / "llm.yaml"
        )
        if not yaml_path.exists():
            return _fallback(tier)
        cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        providers = cfg.get("providers", {})
        if not providers:
            return _fallback(tier)

        order = cfg.get("fallback_order", list(providers.keys()))
        attr = TIER_TO_MODEL_ATTR[tier]
        for pname in order:
            p = providers.get(pname)
            if not p or not isinstance(p, dict):
                continue
            models = p.get("models", {})
            if attr in models:
                return pname, models[attr]
            if "default" in models:
                return pname, models["default"]

        first = next(iter(providers), None)
        if first:
            return first, ""
        return _fallback(tier)
    except Exception as e:
        logger.warning(f"route_model(_route_from_yaml) failed: {e}")
        return _fallback(tier)


def _fallback(tier: ModelTier) -> tuple[str, str]:
    """llm.yaml 不可用时的硬编码兜底。"""
    defaults = {
        ModelTier.FLASH: ("ollama", "qwen2.5:7b"),
        ModelTier.STANDARD: ("openai", "gpt-4o-mini"),
        ModelTier.HEAVY: ("openai", "gpt-4o"),
        ModelTier.EMBED: ("ollama", "nomic-embed-text"),
    }
    return defaults.get(tier, ("openai", ""))


__all__ = [
    "TASK_TIER_MAP",
    "TIER_TO_MODEL_ATTR",
    "TIER_TO_OVERRIDE_KEY",
    "ModelTier",
    "get_tier",
    "route_model",
]