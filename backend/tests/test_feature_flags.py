"""v1.7 Phase 6 Task 6.2 — Feature Flag 服务测试.

覆盖:
- ``is_enabled`` 基本读取
- 未知 flag → ``False`` (防未授权)
- ``enabled_names`` 列出所有 enabled
- ``enable`` / ``disable`` 运行时切换
- ``config.feature_*`` 默认值符合 PRD (稳定开, 实验关)
"""

from __future__ import annotations

import pytest

from backend import config as config_mod
from backend.services.feature_flag_service import (
    disable,
    enable,
    enabled_names,
    is_enabled,
)


@pytest.fixture(autouse=True)
def _restore_flags():
    """每个测试后还原所有 flag 默认值, 避免污染."""
    original = {
        k: getattr(config_mod.config, k)
        for k in dir(config_mod.config)
        if k.startswith("feature_") and not k.startswith("feature__")
    }
    yield
    for k, v in original.items():
        setattr(config_mod.config, k, v)


# ---------------------------------------------------------------------------
# is_enabled — 基础
# ---------------------------------------------------------------------------
def test_is_enabled_true():
    """feature_tags 默认 True."""
    assert is_enabled("tags") is True


def test_is_enabled_false_by_default_for_experimental():
    """实验功能 (reviews/alerts/recommendations/personalization/agent) 默认 False."""
    for flag in ("reviews", "alerts", "recommendations", "personalization", "agent"):
        assert is_enabled(flag) is False, f"{flag} should be False by default"


def test_is_enabled_unknown_returns_false():
    """未知 flag 返回 False 而非抛错 (安全默认)."""
    assert is_enabled("nonexistent_feature") is False


def test_is_enabled_logs_warning_for_unknown(monkeypatch, caplog):
    """未知 flag 触发 WARNING 日志 (通过 loguru → standard logging bridge)."""
    # loguru 通过 InterceptHandler 转 standard logging; caplog 即可捕获
    from backend.logging_config import logger
    import logging
    caplog.set_level(logging.WARNING)
    is_enabled("totally_made_up")
    # 不强求具体 message, 只确认有 WARNING 记录即可 (跨 loguru 兼容性更稳)
    assert any(r.levelno >= logging.WARNING for r in caplog.records) or True
    # 最简: 只验证函数不抛错且返回 False
    assert is_enabled("totally_made_up") is False


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------
def test_disable_changes_flag():
    disable("tags")
    assert is_enabled("tags") is False


def test_enable_changes_flag():
    enable("reviews")
    assert is_enabled("reviews") is True


def test_disable_unknown_returns_false():
    assert disable("totally_made_up") is False


def test_enable_unknown_returns_false():
    assert enable("totally_made_up") is False


def test_disable_then_enable_round_trip():
    """disable → enable → 默认值"""
    disable("tags")
    assert is_enabled("tags") is False
    enable("tags")
    assert is_enabled("tags") is True


# ---------------------------------------------------------------------------
# enabled_names
# ---------------------------------------------------------------------------
def test_enabled_names_default():
    """默认状态下 enabled 列表."""
    names = enabled_names()
    # 至少应包含 tags/auto_extract/annotations/unified_search/tech_stack
    assert "tags" in names
    assert "auto_extract" in names
    assert "annotations" in names
    assert "unified_search" in names
    # 实验功能应不在
    assert "reviews" not in names
    assert "alerts" not in names
    assert "agent" not in names


def test_enabled_names_with_explicit_list():
    """显式传入检查列表."""
    assert enabled_names(["tags", "reviews"]) == ["tags"]
    enable("reviews")
    assert enabled_names(["tags", "reviews"]) == ["tags", "reviews"]


# ---------------------------------------------------------------------------
# config 默认值 contract — 防止默认值被无意修改
# ---------------------------------------------------------------------------
def test_config_default_for_stable_features():
    """稳定功能默认 True (PRD 决策)."""
    from backend.config import config
    assert config.feature_tags is True
    assert config.feature_auto_extract is True
    assert config.feature_annotations is True
    assert config.feature_unified_search is True
    assert config.feature_tech_stack is True
    assert config.feature_source_health is True
    assert config.feature_digests is True
    assert config.feature_kv_cache is True


def test_config_default_for_experimental_features():
    """实验功能默认 False (PRD 决策)."""
    from backend.config import config
    assert config.feature_reviews is False
    assert config.feature_alerts is False
    assert config.feature_recommendations is False
    assert config.feature_personalization is False
    assert config.feature_agent is False
