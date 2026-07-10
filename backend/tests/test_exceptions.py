"""异常体系单元测试

验证：
  - 5 个异常类的 code / http_status
  - register_exception_handlers 把异常转换为统一 JSON 响应
  - 响应中包含 trace_id
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.exceptions import (
    HotspotException,
    InvalidParamException,
    NotFoundException,
    RateLimitedException,
    InternalException,
    SourceUnavailableException,
    register_exception_handlers,
)


@pytest.fixture
def client():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/invalid")
    def raise_invalid():
        raise InvalidParamException("bad param")

    @app.get("/raise/notfound")
    def raise_notfound():
        raise NotFoundException("missing")

    @app.get("/raise/rate")
    def raise_rate():
        raise RateLimitedException("slow down")

    @app.get("/raise/internal")
    def raise_internal():
        raise InternalException("oops")

    @app.get("/raise/source")
    def raise_source():
        raise SourceUnavailableException("down")

    @app.get("/raise/general")
    def raise_general():
        raise RuntimeError("unexpected")

    # raise_server_exceptions=False 让 unhandled exception 被 exception handler 捕获
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_param_response(client):
    r = client.get("/raise/invalid")
    assert r.status_code == 400
    data = r.json()
    assert data["code"] == "INVALID_PARAM"
    assert data["message"] == "bad param"
    assert "trace_id" in data and data["trace_id"]


def test_notfound_response(client):
    r = client.get("/raise/notfound")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_rate_limited_response(client):
    r = client.get("/raise/rate")
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"


def test_internal_response(client):
    r = client.get("/raise/internal")
    assert r.status_code == 500
    assert r.json()["code"] == "INTERNAL"


def test_source_unavailable_response(client):
    r = client.get("/raise/source")
    assert r.status_code == 503
    assert r.json()["code"] == "SOURCE_UNAVAILABLE"


def test_unhandled_exception_response(client):
    r = client.get("/raise/general")
    assert r.status_code == 500
    data = r.json()
    assert data["code"] == "INTERNAL"
    assert "trace_id" in data


def test_exception_classes_fields():
    assert InvalidParamException("x").http_status == 400
    assert InvalidParamException("x").code == "INVALID_PARAM"
    assert NotFoundException("x").http_status == 404
    assert RateLimitedException("x").http_status == 429
    assert InternalException("x").http_status == 500
    assert SourceUnavailableException("x").http_status == 503
    # 基类
    e = HotspotException("MY_CODE", "msg", 418)
    assert e.code == "MY_CODE"
    assert e.http_status == 418
    assert isinstance(e, Exception)
