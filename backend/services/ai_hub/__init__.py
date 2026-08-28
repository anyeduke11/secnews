"""ai_hub — LLM 单出口 + 知识写回唯一门面 (v0.5 M5 Task19)。

重构说明 (v0.6.2)
------------------
原 ``backend/services/ai_hub.py`` (1030 行) 拆分为包:

- ``gateway.py``  — ``LLMService`` (score/summarize/extract_entities/generate)
- ``cache.py``    — LLM/AI 缓存统一操作 (``llm_cache`` 表)
- ``usage.py``    — LLM/AI 用量日志统一操作 (``llm_usage_log`` 表)
- ``tasks.py``    — ``AIService`` (evaluate/gate_detect) + ``evaluate_article``
                    + ``write_score`` + ``write_item`` / ``update_frontmatter``

向后兼容: 所有原有 ``from backend.services.ai_hub import ...`` 保持不变。
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
from backend.repository.db import get_connection

# ── AIService + 辅助 ────────────────────────────────────────────
from .tasks import (
    AIService,
    ai_service,
    evaluate_article,
    write_score,
    write_item,
    update_frontmatter,
    _DETECT_SYSTEM,
    _eval_prompt,
    _parse_eval_json,
    _parse_score01,
    _est_tokens,
)

# ── 公开 API ────────────────────────────────────────────────────
__all__ = [
    "COST_PER_1M_TOKENS",
    "DEFAULT_SCORE",
    "AIService",
    "LLMService",
    "_est_tokens",
    "_parse_eval_json",
    "ai_service",
    "evaluate_article",
    "llm_service",
    "update_frontmatter",
    "write_item",
    "write_score",
]
