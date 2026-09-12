"""ai_hub — LLM 单出口 (v0.5 M5 Task19)。

重构说明 (v0.7.0-step1)
------------------------
原 ``backend/services/ai_hub.py`` (1030 行) 拆分为包:

- ``gateway.py``    — ``LLMService`` (score/summarize/extract_entities/generate)
- ``cache.py``      — LLM/AI 缓存统一操作 (``llm_cache`` 表)
- ``usage.py``      — LLM/AI 用量日志统一操作 (``llm_usage_log`` 表)
- ``service.py``    — v0.7 拆分: ``AIService`` (evaluate/gate_detect/限频/缓存/用量) + ``_DETECT_SYSTEM``
- ``tasks.py``      — 评价辅助 (``_cache_key/_eval_prompt/_parse_*``) + ``evaluate_article`` 入口

外移说明 (2026-09-13)
---------------------
知识写回唯一门面 (v0.5 §18.2 强约束 1: ``write_score`` / ``write_item`` /
``update_frontmatter``) 已外移至 ``backend/services/ai_write_back.py``。
它是本包内唯一指向知识域 (knowledge_sync) 的 import 边 — 外移后
「知识域 ↔ ai_hub 包」域级环解开, 消费方 import 已同步迁移, 本包不再
re-export 写回符号。

向后兼容: 其余原有 ``from backend.services.ai_hub import ...`` 保持不变。
"""

from __future__ import annotations

# ── LLMService ──────────────────────────────────────────────────
from .gateway import (
    DEFAULT_SCORE,
    COST_PER_1M_TOKENS,
    LLMService,
    llm_service,
    _estimate_cost,
    _make_cache_key,
    load_llm_config,
    httpx,
)
# ── AIService (v0.7 拆分到 .service) + 评价辅助 ─────────────────
from .service import (
    AIService,
    ai_service,
    _DETECT_SYSTEM,
)
from .tasks import (
    evaluate_article,
    _eval_prompt,
    _parse_eval_json,
    _parse_score01,
    _est_tokens,
)

# ── v0.7.4-image: 三场景路由 (deep/light/image) ──────────────────
from .scenarios import (
    SCENARIO_DEFAULT_MODEL,
    SCENARIO_ENDPOINT,
    SCENARIO_MAX_TOKENS,
    Scenario,
    ScenarioRoute,
    get_tier_for,
    resolve_scenario_model,
)
from .image_service import (
    ImageGenerationError,
    ImageGenerationService,
)

# ── 公开 API ────────────────────────────────────────────────────
__all__ = [
    "COST_PER_1M_TOKENS",
    "DEFAULT_SCORE",
    "SCENARIO_DEFAULT_MODEL",
    "SCENARIO_ENDPOINT",
    "SCENARIO_MAX_TOKENS",
    "AIService",
    "ImageGenerationError",
    "ImageGenerationService",
    "LLMService",
    "Scenario",
    "ScenarioRoute",
    "_est_tokens",
    "_parse_eval_json",
    "ai_service",
    "evaluate_article",
    "get_tier_for",
    "llm_service",
    "resolve_scenario_model",
]
