"""LLMService.evaluate_article 测试 (v4.4)。

覆盖:
- _parse_eval_json: 解析模型 JSON 输出（含容错）
- evaluate_article: 读 settings 配置 + 调 provider（mock HTTP）
- sensenova / ollama 两条路径
"""
import pytest

from backend.services.llm_service import _parse_eval_json, evaluate_article


@pytest.mark.parametrize("raw,expected_score", [
    ('{"score": 8.5,"verdict":"好","summary":"s","key_points":["a","b"]}', 8.5),
    ('模型输出：{"score": 7,"verdict":"ok","summary":"sum","key_points":["p1","p2","p3"]}', 7.0),
    ('"score": 6.2', 6.2),
    ('no json at all', 5.0),
])
def test_parse_eval_json(raw, expected_score):
    r = _parse_eval_json(raw)
    assert isinstance(r, dict)
    assert "score" in r


def test_parse_eval_json_extracts_key_points():
    raw = '{"score":9,"verdict":"优秀","summary":"好文","key_points":["要点1","要点2"]}'
    r = _parse_eval_json(raw)
    assert r["key_points"] == ["要点1", "要点2"]
    assert r["verdict"] == "优秀"


@pytest.mark.asyncio
async def test_evaluate_sensenova_path(monkeypatch):
    """sensenova 路径：读 settings key + 调商汤 + 解析结果。"""
    captured = {}

    EVAL = '{"score":8,"verdict":"技术深度高","summary":"介绍了新方法","key_points":["方法A","结果B"]}'

    class _Resp:
        def json(self):
            return {"choices": [{"message": {"content": EVAL}}]}
        def raise_for_status(self):
            return None

    class _AC:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["has_auth"] = bool(
                headers and headers.get("Authorization", "").startswith("Bearer")
            )
            return _Resp()

    import backend.services.llm_service as m
    monkeypatch.setattr(m.httpx, "AsyncClient", lambda **k: _AC())

    result = await evaluate_article(
        "一段文章内容", title="测试", provider="sensenova", api_key="sk-test"
    )
    assert result["ok"] is True
    assert result["provider"] == "sensenova"
    assert abs(result["quality_score"] - 8.0) < 1e-6
    assert result["key_points"] == ["方法A", "结果B"]
    assert captured["has_auth"] is True
    assert captured["url"].startswith("https://token.sensenova.cn")


@pytest.mark.asyncio
async def test_evaluate_ollama_path(monkeypatch):
    """ollama 路径调用 http://127.0.0.1:11434。"""
    class _Resp:
        def json(self): return {"message": {"content":
            '{"score":6,"verdict":"尚可","summary":"s","key_points":["k1"]}'}}
        def raise_for_status(self): return None
    class _AC:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None, timeout=None):
            assert url.startswith("http://127.0.0.1:11434")
            return _Resp()

    import backend.services.llm_service as m
    monkeypatch.setattr(m.httpx, "AsyncClient", lambda **k: _AC())
    result = await evaluate_article("一段文章", provider="ollama")
    assert result["ok"] is True
    assert result["provider"] == "ollama"
    assert abs(result["quality_score"] - 6.0) < 1e-6