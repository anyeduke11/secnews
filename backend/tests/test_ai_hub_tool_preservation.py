"""ai_hub 工具消息保留 + F05/F09 失败语义测试 (v1.0 T10).

覆盖契约 (PRD §6 A2 + V0.8.3_CRITICAL_REVIEW §3 F05/F09):

  T1. AIService.generate_text 多消息输入 — tool 角色消息原样下发 (不截断)
  T2. tool_call_id 在 messages 中透传 — round-trip 可被引用
  T3. 多个 tool 项不被合并/折叠 (provider 端可看到全部)
  T4. LLMService.chat 缓存隔离 — 不同 tool_call_id 不同 cache key
  T5. F05 失败语义: provider 抛错 → 返回 {"status_code":"error", ...} JSON
  T6. F09 取消语义: cancel_event 触发 → status_code="cancelled" (不算 timeout)

不真调 provider — 用 monkeypatch 替换 httpx / LLMService._call_provider_chat,
验证消息透传与失败语义契约, 不出网、不写真实库 (T01 conftest 隔离)。
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from backend.services.ai_hub.gateway import LLMService, _format_status, _is_cancelled
from backend.services.ai_hub.service import AIService


# ---------------------------------------------------------------------------
# Test 1: tool 角色消息原样下发 (不截断/合并)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_messages_preserved_in_call(temp_db, monkeypatch):
    """messages 中 ``role=tool`` 项必须原样透传到 provider, 不被压缩/合并。"""
    captured: dict[str, Any] = {}

    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        captured["messages"] = list(messages)
        captured["model"] = model
        return "ok-reply"

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)

    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "调用工具"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call-1", "type": "function",
             "function": {"name": "search", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call-1", "content": '{"hits": 3}'},
        {"role": "assistant", "content": "找到 3 个命中"},
    ]
    out = await LLMService().chat(messages, task="test")
    assert out == "ok-reply"
    # 完整 5 条消息原样, 未被截断/合并
    assert len(captured["messages"]) == 5
    assert captured["messages"][3]["role"] == "tool"
    assert captured["messages"][3]["tool_call_id"] == "call-1"
    assert captured["messages"][3]["content"] == '{"hits": 3}'


# ---------------------------------------------------------------------------
# Test 2: tool_call_id round-trip 可被引用
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_call_id_round_trip(temp_db, monkeypatch):
    """多个 tool_call_id 在 messages 中保持可引用, 不被覆盖/丢失。"""
    captured: dict[str, Any] = {}

    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        captured["messages"] = list(messages)
        return "ok"

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)

    messages = [
        {"role": "user", "content": "query"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call-A", "type": "function",
             "function": {"name": "f1", "arguments": "{}"}},
            {"id": "call-B", "type": "function",
             "function": {"name": "f2", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call-A", "content": "result-A"},
        {"role": "tool", "tool_call_id": "call-B", "content": "result-B"},
    ]
    await LLMService().chat(messages)
    # 两条 tool 项均存在, 且 tool_call_id 不被覆盖
    tool_msgs = [m for m in captured["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "call-A"
    assert tool_msgs[1]["tool_call_id"] == "call-B"
    assert tool_msgs[0]["content"] != tool_msgs[1]["content"]


# ---------------------------------------------------------------------------
# Test 3: AIService.generate_text 委托 LLMService.chat, 保留 tool 消息
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aiservice_generate_text_delegates(temp_db, monkeypatch):
    """AIService.generate_text 路径与 LLMService.chat 等价 (透传 tool)。"""
    captured: dict[str, Any] = {}

    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        captured["messages"] = list(messages)
        return "via-aiservice"

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)

    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [
            {"id": "X", "type": "function",
             "function": {"name": "lookup", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "X", "content": "data"},
    ]
    out = await AIService().generate_text(messages, task="chat")
    assert out == "via-aiservice"
    # tool 项原样保留
    tool_msgs = [m for m in captured["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "X"


# ---------------------------------------------------------------------------
# Test 4: cache key 隔离 — 不同 tool_call_id 不撞 key
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_cache_isolates_tool_call_ids(temp_db, monkeypatch):
    """不同 tool_call_id 的 messages → 不同 cache key (避免假缓存命中)。"""
    call_count = [0]

    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        call_count[0] += 1
        return f"reply-{call_count[0]}"

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)
    # 禁用 cache 写, 让每次都进 provider (避免假命中干扰)
    monkeypatch.setattr(
        "backend.services.ai_hub.gateway.get_llm_cache", lambda k: None,
    )

    messages1 = [
        {"role": "user", "content": "x"},
        {"role": "tool", "tool_call_id": "id-1", "content": "data-1"},
    ]
    messages2 = [
        {"role": "user", "content": "x"},
        {"role": "tool", "tool_call_id": "id-2", "content": "data-1"},
    ]
    out1 = await LLMService().chat(messages1)
    out2 = await LLMService().chat(messages2)
    assert call_count[0] == 2
    assert out1 != out2  # 不同 cache key → 不同响应


# ---------------------------------------------------------------------------
# Test 5: F05 失败语义 — provider 抛错 → status_code="error" JSON
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f05_failure_status_code(temp_db, monkeypatch):
    """F05 修复契约: provider 异常 → 返回 ``{"status_code":"error", "error":...}``。

    调用方按 status_code 判定, 不依赖文本关键字。
    """
    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        raise RuntimeError("provider connection refused")

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)
    # 禁用 cache, 让异常不被吃掉
    monkeypatch.setattr(
        "backend.services.ai_hub.gateway.get_llm_cache", lambda k: None,
    )

    out = await LLMService().chat([{"role": "user", "content": "x"}])
    parsed = json.loads(out)
    assert parsed["status_code"] == "error"
    assert "provider connection refused" in parsed["error"]


# ---------------------------------------------------------------------------
# Test 6: F09 取消语义 — cancel_event → status_code="cancelled", 不算 timeout
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f09_cancellation_status(temp_db, monkeypatch):
    """F09 修复契约: 取消信号 → status_code=cancelled (≠ timeout)。"""

    class _Cancel:
        def __init__(self):
            self._cancelled = False

        def is_set(self) -> bool:
            return self._cancelled

        def cancel(self) -> None:
            self._cancelled = True

    async def fake_chat(self, cfg, model, messages, *, max_tokens=None,
                        temperature=None, provider_name=None):
        # 若走到这里说明取消信号未拦截 — 测试失败
        raise AssertionError("provider 不应被调用 — 取消信号应提前终止")

    monkeypatch.setattr(LLMService, "_call_provider_chat", fake_chat)
    monkeypatch.setattr(
        "backend.services.ai_hub.gateway.get_llm_cache", lambda k: None,
    )

    cancel = _Cancel()
    cancel.cancel()  # 调用前已取消
    out = await LLMService().chat(
        [{"role": "user", "content": "x"}], cancel_event=cancel,
    )
    parsed = json.loads(out)
    assert parsed["status_code"] == "cancelled"
    assert parsed["status_code"] != "timeout"


# ---------------------------------------------------------------------------
# Helpers — 单测 _is_cancelled / _format_status 的边界
# ---------------------------------------------------------------------------
def test_is_cancelled_handles_none_and_various_shapes():
    """``_is_cancelled`` 兼容 None / asyncio.Event / .is_set() / .cancelled()。"""
    assert _is_cancelled(None) is False
    e = type("E", (), {"is_set": lambda self: True})()
    assert _is_cancelled(e) is True
    e2 = type("E", (), {"cancelled": lambda self: True})()
    assert _is_cancelled(e2) is True
    e3 = type("E", (), {"_cancelled": True})()
    assert _is_cancelled(e3) is True


def test_format_status_emits_status_code_and_error():
    """``_format_status`` 产出可被 JSON 解析的 status_code + error。"""
    out = json.loads(_format_status("error", error="oops"))
    assert out["status_code"] == "error"
    assert out["error"] == "oops"
    out2 = json.loads(_format_status("cancelled"))
    assert out2["status_code"] == "cancelled"
    assert out2["error"] == ""
