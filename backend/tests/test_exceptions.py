"""异常体系单元测试

验证：
  - 5 个异常类的 code / http_status
  - register_exception_handlers 把异常转换为统一 JSON 响应
  - 响应中包含 trace_id
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.exceptions import (
    HotspotException,
    InternalException,
    InvalidParamException,
    NotFoundException,
    RateLimitedException,
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

    @app.get("/raise/http/{status}")
    def raise_http(status: int):
        raise HTTPException(status_code=status, detail="http detail msg")

    @app.get("/raise/http-dict")
    def raise_http_dict():
        raise HTTPException(
            status_code=404, detail={"code": "E_NOT_FOUND", "message": "dict detail"}
        )

    @app.get("/raise/http-conflict")
    def raise_http_conflict():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": "stale revision",
                "current_revision": 3,
            },
        )

    @app.get("/raise/http-no-detail")
    def raise_http_no_detail():
        raise HTTPException(status_code=404)

    @app.post("/validate")
    def validate(q: int):
        return {"q": q}

    # raise_server_exceptions=False 让 unhandled exception 被 exception handler 捕获
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_param_response(client):
    r = client.get("/raise/invalid")
    assert r.status_code == 400
    data = r.json()
    assert data["code"] == "INVALID_PARAM"
    assert data["message"] == "bad param"
    assert data.get("trace_id")


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


# ---------------------------------------------------------------------------
# D13: HTTPException / RequestValidationError → 扁平 envelope
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (401, "E_AUTH"),
        (403, "E_FORBIDDEN"),
        (404, "E_NOT_FOUND"),
        (409, "E_CONFLICT"),
        (422, "E_VALIDATION"),
        (429, "E_RATE_LIMIT"),
        (503, "E_INTERNAL"),  # 未映射状态码兜底
    ],
)
def test_http_exception_flat_envelope(client, status, expected_code):
    r = client.get(f"/raise/http/{status}")
    assert r.status_code == status
    data = r.json()
    # 扁平结构: 无嵌套 detail
    assert "detail" not in data
    assert data["code"] == expected_code
    assert data["message"] == "http detail msg"
    assert data["trace_id"]
    assert data["version"]


def test_http_exception_dict_detail_prefers_code(client):
    """detail 为 dict 且含 code 时优先用其值。"""
    r = client.get("/raise/http-dict")
    assert r.status_code == 404
    data = r.json()
    assert data["code"] == "E_NOT_FOUND"
    assert data["message"] == "dict detail"
    assert "detail" not in data


def test_http_exception_dict_detail_merges_extras(client):
    """detail dict 的附加结构化字段平铺到顶层 (信息不丢失)。"""
    r = client.get("/raise/http-conflict")
    assert r.status_code == 409
    data = r.json()
    assert data["code"] == "E_CONFLICT"
    assert data["message"] == "stale revision"
    assert data["current_revision"] == 3
    assert "detail" not in data


def test_http_exception_no_detail(client):
    r = client.get("/raise/http-no-detail")
    assert r.status_code == 404
    data = r.json()
    assert data["code"] == "E_NOT_FOUND"
    assert data["message"]  # 兜底非空 (回退为 code 本身)


def test_request_validation_flat_envelope(client):
    """pydantic 422 校验错误同样输出扁平 E_VALIDATION envelope。"""
    r = client.post("/validate", json={"q": "not-an-int"})
    assert r.status_code == 422
    data = r.json()
    assert "detail" not in data
    assert data["code"] == "E_VALIDATION"
    assert data["trace_id"]
    assert data["version"]
