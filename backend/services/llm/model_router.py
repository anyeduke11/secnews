"""Model router — 模型分层路由 (S4-1)。

将任务类型映射到模型档位 (flash/standard/heavy/embed),
从 config/llm.yaml 读取 provider/model 配置。
"""
from __future__ import annotations

from enum import Enum

from backend.logging_config import logger


class ModelTier(str, Enum):
    FLASH = "flash"          # 轻分析: refine / classify / tag / summary
    STANDARD = "standard"    # 标准分析: evaluate / compare
    HEAVY = "heavy"          # 重分析: deep_read / assess / compliance
    EMBED = "embed"          # 向量: embed / rerank (P3)


# 任务类型 → 档位映射 (与 dsh-SecNews cap registry 对齐)
TASK_TIER_MAP: dict[str, ModelTier] = {
    # flash 档 — 高频轻量
    "refine": ModelTier.FLASH,
    "classify": ModelTier.FLASH,
    "tag": ModelTier.FLASH,
    "summarize": ModelTier.FLASH,
    "brief": ModelTier.FLASH,
    # standard 档 — 中等复杂度
    "evaluate": ModelTier.STANDARD,
    "compare": ModelTier.STANDARD,
    "score": ModelTier.STANDARD,
    # heavy 档 — 点击触发
    "deep_read": ModelTier.HEAVY,
    "assess": ModelTier.HEAVY,
    "compliance": ModelTier.HEAVY,
    "report": ModelTier.HEAVY,
}


def route_model(task_type: str) -> tuple[str, str]:
    """按任务类型路由到 (provider, model)。

    从 config/llm.yaml 的 providers 配置解析;
    找不到匹配时回退到 default_provider 的默认模型。

    Returns:
        (provider_name, model_name)
    """
    tier = get_tier(task_type)

    try:
        from pathlib import Path

        import yaml
        yaml_path = Path(__file__).resolve().parent.parent / "config" / "llm.yaml"
        if not yaml_path.exists():
            return _fallback(tier)
        cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        providers = cfg.get("providers", {})
        if not providers:
            return _fallback(tier)

        # 按 fallback_order 尝试
        order = cfg.get("fallback_order", list(providers.keys()))
        for pname in order:
            p = providers.get(pname)
            if not p or not isinstance(p, dict):
                continue
            models = p.get("models", {})
            if tier.value in models:
                return pname, models[tier.value]
            if "default" in models:
                return pname, models["default"]

        # 全部未命中 → 取第一个可用 provider
        first = next(iter(providers), None)
        if first:
            return first, ""
        return _fallback(tier)
    except Exception as e:
        logger.warning(f"route_model failed: {e}")
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


def get_tier(task_type: str) -> ModelTier:
    """获取任务对应的模型档位。"""
    return TASK_TIER_MAP.get(task_type, ModelTier.STANDARD)


__all__ = ["TASK_TIER_MAP", "ModelTier", "get_tier", "route_model"]
