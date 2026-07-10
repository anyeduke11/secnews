"""Phase 3.5 quality gate package.

Public API
----------
- :class:`BaseGate`         gate 抽象基类
- :class:`QualityGatePipeline` 8 门禁编排
- :class:`QualityConfig`    严格/宽松 + 关键词配置
- :func:`compute_final_score`, :func:`merge_flags`, :func:`is_acceptable`
  — 评分工具
- 8 个门禁实现
- :func:`run_url_content_check`  异步抽样验证
"""
from __future__ import annotations

from backend.quality.base import BaseGate, GateContext
from backend.quality.config import (
    QualityConfig,
    QualityMode,
    default_category_keywords,
    get_category_keywords,
)
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.scorer import (
    compute_final_score,
    is_acceptable,
    merge_flags,
)

__all__ = [
    "BaseGate",
    "GateContext",
    "QualityConfig",
    "QualityMode",
    "QualityGatePipeline",
    "compute_final_score",
    "is_acceptable",
    "merge_flags",
    "default_category_keywords",
    "get_category_keywords",
]
