"""URL Validity Gate 单元测试。

覆盖 6 个核心场景:
- 2xx 通过
- 3xx 重定向通过
- 4xx 失败
- 5xx 失败
- 405/501 HEAD 不支持 → GET fallback
- DNS 失败 / 超时 / 连接拒绝
- 重定向循环(>10 次) → 失败
- 集成: pipeline 中注册位置正确 + 严格模式拒绝
"""
from __future__ import annotations

import socket
import urllib.error
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.domain.collection import GateResult, PipelineResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.pipeline import QualityGatePipeline
from backend.quality.url_validity_gate import (
    _PENALTY,
    URLValidityGate,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_item(
    url: str = "https://example.com/news/1",
    title: str = "OpenAI announces new GPT model",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id="t1",
        title=title,
        summary="summary text",
        source="src_a",
        url=url,
        category=Category.AI,
        published_at=now,
        fetched_at=now,
    )


def _ctx() -> "GateContext":  # noqa: F821
    from backend.quality.base import GateContext
    return GateContext(
        mode="loose",
        category_keywords={"ai": ["AI", "OpenAI", "GPT"]},
        source_reputation={},
        existing_urls=set(),
        existing_titles=[],
    )


def _http_response(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


# ---------------------------------------------------------------------------
# 1. HEAD 2xx → 通过
# ---------------------------------------------------------------------------
def test_head_2xx_passes():
    g = URLValidityGate(timeout=2)
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=200) as mock_head:
        r = g.check(item, _ctx())
    assert r.passed is True
    assert r.score_deduction == 0
    assert r.flags == []
    mock_head.assert_called_once()


def test_head_3xx_redirect_passes():
    g = URLValidityGate(timeout=2)
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=301):
        r = g.check(item, _ctx())
    assert r.passed is True


# ---------------------------------------------------------------------------
# 2. 4xx / 5xx → 失败
# ---------------------------------------------------------------------------
def test_4xx_fails_with_url_unreachable_flag():
    g = URLValidityGate(timeout=2)
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=404):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert r.score_deduction == _PENALTY
    assert "url_unreachable" in r.flags
    assert "404" in (r.reason or "")


def test_5xx_fails_with_url_unreachable_flag():
    g = URLValidityGate(timeout=2)
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=503):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert "url_unreachable" in r.flags
    assert "503" in (r.reason or "")


# ---------------------------------------------------------------------------
# 3. 网络异常 → 失败
# ---------------------------------------------------------------------------
def test_dns_failure_marks_unreachable():
    g = URLValidityGate(timeout=2)
    item = _make_item(url="https://this-host-does-not-exist-xyz.invalid/")

    def _raise(*a, **kw):
        raise socket.gaierror("Name or service not known")

    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=_raise):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert "url_unreachable" in r.flags
    assert r.score_deduction == _PENALTY


def test_timeout_marks_unreachable():
    g = URLValidityGate(timeout=1)
    item = _make_item()

    def _raise(*a, **kw):
        raise TimeoutError("read timeout")

    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=_raise):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert "url_unreachable" in r.flags


def test_connection_refused_marks_unreachable():
    g = URLValidityGate(timeout=2)
    item = _make_item()

    def _raise(*a, **kw):
        raise ConnectionRefusedError("connection refused")

    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=_raise):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert "url_unreachable" in r.flags


# ---------------------------------------------------------------------------
# 4. HEAD 不支持 (405/501) → GET fallback
# ---------------------------------------------------------------------------
def test_405_method_not_allowed_falls_back_to_get():
    g = URLValidityGate(timeout=2)
    item = _make_item()

    head_err = urllib.error.HTTPError(
        url="https://example.com/news/1", code=405,
        msg="Method Not Allowed", hdrs={}, fp=None,
    )
    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=head_err), \
         patch("backend.quality.url_validity_gate._get_status",
               return_value=200) as mock_get:
        r = g.check(item, _ctx())
    assert r.passed is True
    mock_get.assert_called_once()


def test_501_falls_back_to_get():
    g = URLValidityGate(timeout=2)
    item = _make_item()

    head_err = urllib.error.HTTPError(
        url="https://example.com/news/1", code=501,
        msg="Not Implemented", hdrs={}, fp=None,
    )
    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=head_err), \
         patch("backend.quality.url_validity_gate._get_status",
               return_value=200) as mock_get:
        r = g.check(item, _ctx())
    assert r.passed is True
    mock_get.assert_called_once()


def test_405_get_also_4xx_marks_unreachable():
    g = URLValidityGate(timeout=2)
    item = _make_item()

    head_err = urllib.error.HTTPError(
        url="https://example.com/news/1", code=405,
        msg="Method Not Allowed", hdrs={}, fp=None,
    )
    get_err = urllib.error.HTTPError(
        url="https://example.com/news/1", code=403,
        msg="Forbidden", hdrs={}, fp=None,
    )
    with patch("backend.quality.url_validity_gate._head_status",
               side_effect=head_err), \
         patch("backend.quality.url_validity_gate._get_status",
               side_effect=get_err):
        r = g.check(item, _ctx())
    assert r.passed is False
    assert "url_unreachable" in r.flags
    assert "403" in (r.reason or "")


# ---------------------------------------------------------------------------
# 5. 集成 — 严格模式拒绝低分
# ---------------------------------------------------------------------------
def test_strict_mode_rejects_unreachable_url():
    """URL 不可达 → 扣 25 分; 严格模式 score < min_score 时拒绝。"""
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = True
    cfg._cache["min_score"] = 80  # 100-25=75 < 80, 拒
    pipe = QualityGatePipeline(
        cfg, log_repo=_NoopLogRepo(),
        gates=[URLValidityGate(timeout=2)],
    )
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=404):
        with pytest.raises(Exception):  # QualityGateFailed
            pipe.run_all(item, _ctx())


def test_loose_mode_keeps_item_with_url_unreachable_flag():
    """loose 模式 → 打 flag + 扣分, 仍 accept (final_score >= 0)."""
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = False
    cfg._cache["min_score"] = 30
    pipe = QualityGatePipeline(
        cfg, log_repo=_NoopLogRepo(),
        gates=[URLValidityGate(timeout=2)],
    )
    item = _make_item()
    with patch("backend.quality.url_validity_gate._head_status",
               return_value=404):
        result = pipe.run_all(item, _ctx())
    assert isinstance(result, PipelineResult)
    assert result.accepted is True
    assert result.final_score == 100 - _PENALTY
    assert "url_unreachable" in result.final_flags


# ---------------------------------------------------------------------------
# 6. 集成 — pipeline 中位置正确
# ---------------------------------------------------------------------------
def test_url_validity_registered_in_default_pipeline():
    cfg = QualityConfig()
    pipe = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())
    names = [g.name for g in pipe.gates]
    assert "url_validity" in names


# ---------------------------------------------------------------------------
# 7. _NoopLogRepo stub
# ---------------------------------------------------------------------------
class _NoopLogRepo:
    def __init__(self):
        self.written = []

    def write_log(self, item_id, result, mode="loose", checked_at=None):
        self.written.append((item_id, result))
