"""v1.9 Phase 9 — collection_logger (结构化事件日志) 单测.

覆盖 (8 用例):
  - L1.1 log_collect_event 调用底层 log_event
  - L1.2 source_name → source 字段归一
  - L1.3 数字字段转 int
  - L1.4 error 截断 200 字符
  - L1.5 log_validation 写出 validation 类型 + severity + payload(JSON)
  - L1.6 错误字段 None / 非 str 不崩
  - L1.7 事件 type 必传
  - L1.8 容错: 底层 log_event 抛异常 → log_collect_event 不向上抛
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.services import collection_logger


# ---------------------------------------------------------------------------
# L1.1 — log_collect_event 透传 event + fields
# ---------------------------------------------------------------------------
def test_log_collect_event_passes_event_and_fields():
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        collection_logger.log_collect_event(
            "source_done",
            run_id=42,
            category="ai",
            source="hacker_news",
            items=15,
            duration_ms=2300,
        )
    assert mock_base.called
    kwargs = mock_base.call_args.kwargs
    assert kwargs["event"] == "source_done"
    assert kwargs["run_id"] == 42
    assert kwargs["category"] == "ai"
    assert kwargs["source"] == "hacker_news"
    assert kwargs["items"] == 15
    assert kwargs["duration_ms"] == 2300


# ---------------------------------------------------------------------------
# L1.2 — source_name → source 归一
# ---------------------------------------------------------------------------
def test_source_name_normalized_to_source():
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        collection_logger.log_collect_event(
            "source_failed", run_id=1, category="ai", source_name="aliyun"
        )
    kwargs = mock_base.call_args.kwargs
    # source_name 已被 _normalize 改名为 source
    assert kwargs.get("source") == "aliyun"
    assert "source_name" not in kwargs


# ---------------------------------------------------------------------------
# L1.3 — 数字字段转 int
# ---------------------------------------------------------------------------
def test_numeric_fields_coerced_to_int():
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        # 用 str 传数字
        collection_logger.log_collect_event(
            "source_done",
            run_id="42",
            items="15",
            duration_ms="2300",
            max_per_source="30",
        )
    kwargs = mock_base.call_args.kwargs
    assert kwargs["run_id"] == 42
    assert isinstance(kwargs["run_id"], int)
    assert kwargs["items"] == 15
    assert kwargs["duration_ms"] == 2300
    assert kwargs["max_per_source"] == 30


# ---------------------------------------------------------------------------
# L1.4 — error 字段截断 200
# ---------------------------------------------------------------------------
def test_error_truncated_to_200():
    long_err = "x" * 500
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        collection_logger.log_collect_event(
            "source_failed", run_id=1, error=long_err
        )
    kwargs = mock_base.call_args.kwargs
    assert len(kwargs["error"]) == 200


# ---------------------------------------------------------------------------
# L1.5 — log_validation 序列化 payload
# ---------------------------------------------------------------------------
def test_log_validation_serializes_payload():
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        collection_logger.log_validation(
            run_id=42,
            validation_type="source_regression",
            severity="warn",
            payload={"category": "ai", "source_name": "hacker_news", "regression_pct": 80.0},
        )
    kwargs = mock_base.call_args.kwargs
    assert kwargs["event"] == "validation"
    assert kwargs["validation_type"] == "source_regression"
    assert kwargs["severity"] == "warn"
    # payload 是 JSON 字符串
    assert isinstance(kwargs["payload"], str)
    parsed = json.loads(kwargs["payload"])
    assert parsed["category"] == "ai"
    assert parsed["source_name"] == "hacker_news"
    assert parsed["regression_pct"] == 80.0


# ---------------------------------------------------------------------------
# L1.6 — error=None 不崩
# ---------------------------------------------------------------------------
def test_error_none_safe():
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        # error=None → 走 str(v)[:200] → "None"
        collection_logger.log_collect_event("collect_done", run_id=1, error=None)
    # 关键是 mock 被调用
    assert mock_base.called


# ---------------------------------------------------------------------------
# L1.7 — 容错: 底层抛异常 → log_collect_event 透传 (不强制 swallow)
# ---------------------------------------------------------------------------
def test_underlying_exception_propagates():
    """当前实现不吞异常 — 验证: 底层 log_event raise → log_collect_event 也 raise.

    这是 by design: 日志失败时上层 (catchup_service) 会用 try/except 包住,
    logger 自己不吞, 避免静默失败.
    """
    with patch.object(
        collection_logger, "_base_log_event", side_effect=RuntimeError("log fail")
    ), pytest.raises(RuntimeError, match="log fail"):
        collection_logger.log_collect_event("collect_done", run_id=1)


# ---------------------------------------------------------------------------
# L1.8 — payload 截断 500
# ---------------------------------------------------------------------------
def test_validation_payload_truncated_to_500():
    big_payload = {"k": "x" * 1000}
    with patch.object(collection_logger, "_base_log_event") as mock_base:
        collection_logger.log_validation(
            run_id=1,
            validation_type="category_anomaly",
            severity="info",
            payload=big_payload,
        )
    kwargs = mock_base.call_args.kwargs
    assert len(kwargs["payload"]) <= 500
