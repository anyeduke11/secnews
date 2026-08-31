"""evaluate_article 测试 (v4.4 → v0.5 基线修复)。

覆盖:
- _parse_eval_json: 解析模型 JSON 输出（含容错），M5 合并后位于 ai_hub
- evaluate_article: ai_hub 统一委托 ai_service（mock HTTP）
- sensenova / ollama 两条路径

基线修复说明（v0.5 T0）：原测试从 llm_service 导入 _parse_eval_json（该函数
v4.4 后位于 ai_service），且 mock 的是 httpx.AsyncClient，而实际调用路径是
llm_service.evaluate_article → asyncio.to_thread → ai_service 内同步 httpx.Client。
本文件按实际契约重写，测试意图不变。M5 T19 双出口合并后全部从 ai_hub 导入。
"""
import pytest

from backend.services.ai_hub import _parse_eval_json, evaluate_article


@pytest.mark.parametrize("raw,expected_score", [
    ('{"score": 8.5,"verdict":"好","summary":"s","key_points":["a","b"]}', 8.5),
    ('模型输出：{"score": 7,"verdict":"ok","summary":"sum","key_points":["p1","p2","p3"]}', 7.0),
    ('"score": 6.2', 6.2),
    ('no json at all', 5.0),
])
def test_parse_eval_json(raw, expected_score):
    r = _parse_eval_json(raw, provider="test")
    assert isinstance(r, dict)
    assert "quality_score" in r
    assert abs(r["quality_score"] - expected_score) < 1e-6


def test_parse_eval_json_extracts_key_points():
    raw = '{"score":9,"verdict":"优秀","summary":"好文","key_points":["要点1","要点2"]}'
    r = _parse_eval_json(raw, provider="test")
    assert r["key_points"] == ["要点1", "要点2"]
    assert r["verdict"] == "优秀"


@pytest.mark.asyncio
async def test_evaluate_sensenova_path(monkeypatch):
    """sensenova 路径：调商汤 + Bearer 鉴权 + 解析结果。"""
    captured = {}

    EVAL = '{"score":8,"verdict":"技术深度高","summary":"介绍了新方法","key_points":["方法A","结果B"]}'

    class _Resp:
        def json(self):
            return {"choices": [{"message": {"content": EVAL}}]}
        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, timeout=None):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["has_auth"] = bool(
                headers and headers.get("Authorization", "").startswith("Bearer")
            )
            return _Resp()

    import backend.services.ai_hub as ai_mod
    import backend.services.ai_hub.service as ai_service_mod
    # v0.7 拆分后 httpx 改由 service.py 直接使用；patch 其实际 import 路径，
    # 而非包入口 re-export，否则 pytest 进程内引用不传播。
    monkeypatch.setattr(ai_service_mod.httpx, "Client", _Client)
    # 绕开 DB 缓存/用量副作用，锁定 HTTP 路径（conftest 测试库隔离外的双保险）
    monkeypatch.setattr(ai_mod.ai_service, "_cache_get", lambda key: None)
    monkeypatch.setattr(ai_mod.ai_service, "_cache_set", lambda key, value: None)
    # v0.7 Batch 1: AIService 改用 _record (新统一入口), 测试同步跟到 _record。
    # 记录 (provider, model, task, ok) 四元组足够判读 (tokens/cost 由 record_llm_call
    # 自己算并落 llm_usage_log, 单测层不重复断言)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        ai_mod.ai_service, "_record",
        lambda provider, model, task, *, ok, **_: record_calls.append(
            (provider, model, task, ok)
        ),
    )

    result = await evaluate_article(
        "一段文章内容-sensenova-用例", title="测试", provider="sensenova",
        api_key="sk-test",
    )
    assert result["ok"] is True
    assert result["provider"] == "sensenova"
    assert abs(result["quality_score"] - 8.0) < 1e-6
    # 成功路径必须记录一次用量 (修复前 _record/_usage 抛 TypeError, 用量从未落表)
    assert len(record_calls) == 1, f"期望记录 1 次用量, 实得 {record_calls}"
    prov, model, task, ok = record_calls[0]
    assert prov == "sensenova" and task == "evaluate" and ok is True
    assert model
    assert result["key_points"] == ["方法A", "结果B"]
    assert captured["has_auth"] is True
    assert captured["url"].startswith("https://token.sensenova.cn")


@pytest.mark.asyncio
async def test_evaluate_ollama_path(monkeypatch):
    """ollama 路径调用 http://127.0.0.1:11434。"""
    class _Resp:
        def json(self):
            return {"message": {"content":
                '{"score":6,"verdict":"尚可","summary":"s","key_points":["k1"]}'}}
        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, timeout=None):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, json=None, headers=None, timeout=None):
            assert url.startswith("http://127.0.0.1:11434")
            return _Resp()

    import backend.services.ai_hub as ai_mod
    import backend.services.ai_hub.service as ai_service_mod
    monkeypatch.setattr(ai_service_mod.httpx, "Client", _Client)
    monkeypatch.setattr(ai_mod.ai_service, "_cache_get", lambda key: None)
    monkeypatch.setattr(ai_mod.ai_service, "_cache_set", lambda key, value: None)
    # v0.7 Batch 1: 改 patch _record (替代 _usage)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        ai_mod.ai_service, "_record",
        lambda provider, model, task, *, ok, **_: record_calls.append(
            (provider, model, task, ok)
        ),
    )

    result = await evaluate_article("一段文章-ollama-用例", provider="ollama")
    assert result["ok"] is True
    assert result["provider"] == "ollama"
    assert abs(result["quality_score"] - 6.0) < 1e-6
    assert len(record_calls) == 1, f"期望记录 1 次用量, 实得 {record_calls}"
    prov, model, task, ok = record_calls[0]
    assert prov == "ollama" and task == "evaluate" and ok is True
    assert model


def test_provider_failure_returns_ok_false_and_records_usage(monkeypatch):
    """provider 抛错 → ok=False + error, 且用量记录一次 (ok=False, error 透传)。

    v0.7 Batch 1: AIService 失败路径改走 _record (替代 _usage), 同样必须落
    llm_usage_log 一行 (ok=0); 此测试守住契约不漂移。
    """
    from backend.services.ai_hub import service as svc_mod

    def _boom(*a, **k):
        raise RuntimeError("provider down")

    record_calls: list[tuple] = []
    monkeypatch.setattr(svc_mod.ai_service, "available", lambda p=None: True)
    monkeypatch.setattr(svc_mod.ai_service, "_cache_get", lambda key: None)
    monkeypatch.setattr(svc_mod.ai_service, "_cache_set", lambda key, value: None)
    monkeypatch.setattr(svc_mod.ai_service, "_call_ollama_eval", _boom)
    monkeypatch.setattr(
        svc_mod.ai_service, "_record",
        lambda provider, model, task, *, ok, **_: record_calls.append(
            (provider, model, task, ok)
        ),
    )

    result = svc_mod.ai_service.evaluate("一段会失败的正文", title="标题", provider="ollama")

    assert result["ok"] is False
    assert result["provider"] == "ollama"
    assert "RuntimeError" in result["error"] and "provider down" in result["error"]
    assert len(record_calls) == 1, f"失败路径也应记录用量, 实得 {record_calls}"
    assert record_calls[0][0] == "ollama" and record_calls[0][2] == "evaluate"
    assert record_calls[0][3] is False
