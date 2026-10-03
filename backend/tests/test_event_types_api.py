"""event_types_api._http_exc 异常映射回归 — v0.8.6 P0-8 / 审计 E9。

E9 根因: ``_http_exc`` 引用了未导入的 ``ConflictException`` (ruff F821
已捕获但未阻断) — 409 路径实际抛 ``NameError`` → 客户端收到 500。
本测试直接锁定 4 类映射, Conflict 分支在修复前必炸 (NameError)。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.event_types_api import _http_exc
from backend.exceptions import (
    ConflictException,
    InvalidParamException,
    NotFoundException,
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (NotFoundException("gone"), 404),
        (InvalidParamException("bad"), 400),
        (ConflictException("dup"), 409),  # E9: 修复前此处 NameError
        (RuntimeError("boom"), 500),
    ],
)
def test_http_exc_maps_project_exceptions(exc: Exception, expected: int) -> None:
    """项目异常 → HTTP 状态码; Conflict 必须 409 而非 NameError→500。"""
    out = _http_exc(exc)
    assert isinstance(out, HTTPException)
    assert out.status_code == expected
