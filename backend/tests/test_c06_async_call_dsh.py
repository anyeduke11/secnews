"""v1.0 C06 反例测试 — 4 service _call_dsh 异步边界 (R07).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §7 C06] + [REVIEW_2026-09-07.md R07]

范围 (本测试): 4 业务 service 的 ``_call_dsh`` 同步 ctx 异步边界.
  - judgment_service._call_dsh
  - action_service._call_dsh
  - knowledge_service._call_dsh
  - sk01_daily_priority.DailyPriorityIntelService._call_dsh

反例:
  旧实现 ``_call_dsh`` 直调 ``ai_service.generate_text`` (async 函数) 当 sync
  调用 — 实际返 coroutine 对象, 后续 ``parse_cve_impact_brief_response(coro)``
  抛异常或返空字符串. 本测试固化反例: 在未注入 ``dsh_caller`` 时, 调用方
  拿到的应是字符串 (走 ``run_dsh_sync`` 强制 asyncio.run 路径, 不返 coroutine).

修复断言:
  1. 注入路径 → 直返注入值 (字符串, 不返 coroutine)
  2. 默认路径 (注入=None) → 走 DSHVendorUnavailableError → ai_hub fallback
     (真 vendor 不可用时), ai_hub 也失败时上抛对应业务 ValidationError
  3. 永不静默降级: DSHVendorUnavailableError 必须显式抛出, 调用方显式 fallback

纪律:
  - 不写真实库 (T01 conftest 隔离);
  - 注入 mock ai_hub.generate_text (避免真模型调用);
  - 反例测试在旧实现必失败 (因为旧 ``_call_dsh`` 静默吞或返 coroutine).
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# 通用: 注入 fake_dsh_caller + fake ai_hub.generate_text
# ---------------------------------------------------------------------------
@pytest.fixture()
def fake_dsh_caller():
    """单服务 ``_dsh_caller`` 字段注入 — 模拟 mock / 真 vendor."""
    def _fake(prompt: str) -> str:
        return f"fake-vendor-ok:{prompt[:24]}"

    return _fake


@pytest.fixture()
def fake_ai_hub_async(monkeypatch):
    """ai_service.generate_text 注入 (async coroutine → 走 asyncio.run).

    不走真 LLM provider, 返可控字符串 — 验证 C06 R07 异步 await 路径.
    """

    async def _fake_generate_text(messages, *, task="chat", **kwargs) -> str:
        # 校验 messages 真传入 (而不是直接被 await bypass)
        assert isinstance(messages, list), f"messages 应为 list, 实际={type(messages)}"
        user_msg = next((m for m in messages if m.get("role") == "user"), None)
        assert user_msg is not None, "messages 应含 role=user 项"
        return json.dumps({
            "claim_type": "configuration_vulnerability",
            "claim": "fake ai_hub reply for testing R07 fix",
            "conditions": "",
            "confidence": "medium",
            "evidence_refs": [],
            "counter_evidence_refs": [],
            "unknowns": [],
        })

    # 用 monkeypatch 替换 async 函数本身 (不是 .generate_text), 因为
    # _call_dsh 直接 import `ai_service` 然后 .generate_text.
    monkeypatch.setattr(
        "backend.services.ai_hub.service.ai_service.generate_text",
        _fake_generate_text,
    )
    return _fake_generate_text


# ---------------------------------------------------------------------------
# 反例 1: 旧实现必返 coroutine — 修复断言必返 str
# ---------------------------------------------------------------------------
def test_judgment_call_dsh_returns_string_not_corobject(fake_dsh_caller, fake_ai_hub_async):
    """R07 反例基线: judgment._call_dsh() 必返字符串.

    旧实现 ``return ai_service.generate_text(...)`` 把 async 函数当 sync 调用,
    实际返的是 coroutine 对象 (不报错, 因为 async 函数被"懒执行"). 测试
    ``assert isinstance(out, str)`` 旧实现必失败, 新实现 (asyncio.run 强制
    event loop) 通过.
    """
    from backend.services.judgment_service import JudgmentService
    svc = JudgmentService(dsh_caller=fake_dsh_caller)
    out = svc._call_dsh("test prompt for judgment R07")
    assert isinstance(out, str), (
        f"R07 修复断言: _call_dsh 应返 str, 实际 type={type(out).__name__}; "
        f"旧实现隐藏返 coroutine"
    )
    assert out.startswith("fake-vendor-ok:"), (
        f"注入路径应直返 fake_dsh_caller (前缀), 实际={out!r}"
    )
    assert "judgment" in out, f"注入应保留原 prompt 内容: {out!r}"


def test_action_call_dsh_returns_string_not_corobject(fake_dsh_caller, fake_ai_hub_async):
    """R07 反例基线: action._call_dsh() 必返字符串."""
    from backend.services.action_service import ActionService
    svc = ActionService(dsh_caller=fake_dsh_caller)
    out = svc._call_dsh("test prompt for action R07")
    assert isinstance(out, str), (
        f"R07 修复断言: _call_dsh 应返 str, 实际 type={type(out).__name__}"
    )
    assert out.startswith("fake-vendor-ok:") and "action" in out


def test_knowledge_call_dsh_returns_string_not_corobject(fake_dsh_caller, fake_ai_hub_async):
    """R07 反例基线: knowledge._call_dsh() 必返字符串."""
    from backend.services.knowledge_service import KnowledgeService
    svc = KnowledgeService(dsh_caller=fake_dsh_caller)
    out = svc._call_dsh("test prompt for knowledge R07")
    assert isinstance(out, str), (
        f"R07 修复断言: _call_dsh 应返 str, 实际 type={type(out).__name__}"
    )
    assert out.startswith("fake-vendor-ok:") and "knowledg" in out


def test_sk01_call_dsh_returns_string_not_corobject(fake_dsh_caller, fake_ai_hub_async):
    """R07 反例基线: sk01._call_dsh() 必返字符串."""
    from backend.services.skill_registry.sk01_daily_priority import (
        DailyPriorityIntelService,
    )
    svc = DailyPriorityIntelService(dsh_caller=fake_dsh_caller)
    out = svc._call_dsh("test prompt for sk01 R07")
    assert isinstance(out, str), (
        f"R07 修复断言: sk01._call_dsh 应返 str, 实际 type={type(out).__name__}"
    )
    assert out.startswith("fake-vendor-ok:") and "sk01" in out


# ---------------------------------------------------------------------------
# 修复断言 2: 默认路径 — DSHVendorUnavailableError → ai_hub 显式 fallback
# ---------------------------------------------------------------------------
def test_judgment_call_dsh_default_falls_back_to_ai_hub_explicitly(monkeypatch, fake_ai_hub_async):
    """R07+R06 修复断言: judgment 默认路径 — vendor blocked → ai_hub fallback.

    旧实现: 静默 fallback ai_hub.generate_text (直接 await bypass), 不显式标注
    exit_criteria, 违反 user/PRD "不静默降级".

    新实现:
      1. run_dsh_sync 探测 vendor → DSHVendorUnavailableError;
      2. judgment 捕获 → 显式 warning log (含 commit_sha) → 走 ai_hub fallback;
      3. ai_hub.generate_text 必走 asyncio.run (避免隐藏 coroutine);
      4. 整个流程显式, 不静默.
    """
    from backend.services.dsh_adapter import DSHVendorUnavailableError
    from backend.services.judgment_service import JudgmentService

    # 强制 probe 返 DSHVendorUnavailableError (模拟真 vendor 不可用)
    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )

    svc = JudgmentService()  # 不注入 dsh_caller
    # 调用 _call_dsh: 真 vendor 不可用 → DSHVendorUnavailableError → 捕获 →
    # 走 ai_hub fallback (fake_ai_hub_async 返回 fake JSON).
    out = svc._call_dsh("judgment default path test")
    assert isinstance(out, str), (
        f"默认路径应走 ai_hub fallback 返字符串, 实际 type={type(out).__name__}"
    )
    parsed = json.loads(out)
    assert parsed["claim"] == "fake ai_hub reply for testing R07 fix", (
        f"ai_hub fallback 响应未被 asyncio.run await, 实际={out!r}"
    )


def test_action_call_dsh_default_falls_back_to_ai_hub_explicitly(monkeypatch, fake_ai_hub_async):
    """R07+R06 修复断言: action 默认路径 — vendor blocked → ai_hub fallback."""
    from backend.services.action_service import ActionService
    from backend.services.dsh_adapter import DSHVendorUnavailableError

    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )
    svc = ActionService()
    out = svc._call_dsh("action default path test")
    assert isinstance(out, str), (
        f"action 默认路径应走 ai_hub fallback 返字符串, 实际 type={type(out).__name__}"
    )


def test_knowledge_call_dsh_default_falls_back_to_ai_hub_explicitly(monkeypatch, fake_ai_hub_async):
    """R07+R06 修复断言: knowledge 默认路径 — vendor blocked → ai_hub fallback."""
    from backend.services.dsh_adapter import DSHVendorUnavailableError
    from backend.services.knowledge_service import KnowledgeService

    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )
    svc = KnowledgeService()
    out = svc._call_dsh("knowledge default path test")
    assert isinstance(out, str), (
        f"knowledge 默认路径应走 ai_hub fallback 返字符串, 实际 type={type(out).__name__}"
    )


def test_sk01_call_dsh_default_falls_back_to_ai_hub_explicitly(monkeypatch, fake_ai_hub_async):
    """R07+R06 修复断言: sk01 默认路径 — vendor blocked → ai_hub fallback."""
    from backend.services.dsh_adapter import DSHVendorUnavailableError
    from backend.services.skill_registry.sk01_daily_priority import (
        DailyPriorityIntelService,
    )

    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )
    svc = DailyPriorityIntelService()
    out = svc._call_dsh("sk01 default path test")
    assert isinstance(out, str), (
        f"sk01 默认路径应走 ai_hub fallback 返字符串, 实际 type={type(out).__name__}"
    )


# ---------------------------------------------------------------------------
# 修复断言 3: 永不静默降级 — DSHVendorUnavailableError 必显式抛出 (不吞)
# ---------------------------------------------------------------------------
def test_judgment_call_dsh_does_not_silently_swallow_d3(monkeypatch):
    """R06 修复断言: DSHVendorUnavailableError 不被 judgment 静默吞 — audit 双写.

    验证方式: 强制 vendor 不可用 + ai_hub 也抛异常 → 上抛业务 ValidationError
    (含 D3 exit_criteria 描述), 不允许 ``except Exception: pass`` 吞.
    """
    from backend.services.dsh_adapter import DSHVendorUnavailableError
    from backend.services.judgment_service import JudgmentService, JudgmentValidationError

    # vendor 不可用 + ai_hub 必抛
    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )

    async def _fail_ai_hub(messages, *, task="chat", **kwargs):
        raise RuntimeError("simulated ai_hub failure")

    monkeypatch.setattr(
        "backend.services.ai_hub.service.ai_service.generate_text",
        _fail_ai_hub,
    )

    svc = JudgmentService()
    with pytest.raises(JudgmentValidationError) as excinfo:
        svc._call_dsh("trigger d3 + ai_hub fail")
    err_msg = str(excinfo.value)
    assert "D3" in err_msg or "exit_criteria" in err_msg or "both failed" in err_msg, (
        f"R06 修复断言: 上抛应显式标注 D3 exit_criteria, 实际={err_msg!r}; "
        f"旧实现可能静默吞"
    )


# ---------------------------------------------------------------------------
# F821 修复断言: dsh_caller 字段类型为 Callable[[str], str], 不再是 Any
# ---------------------------------------------------------------------------
def test_dsh_caller_field_type_is_callable_not_any():
    """F821 修复断言: JudgmentService.dsh_caller 类型注解是 Callable, 不再 Any.

    旧实现 ``dsh_caller: Any = None`` 让 ruff F821 (Any 类型) 错; 新实现
    用 ``Callable[[str], str] | None`` 具体化 — 静态类型检查工具 (mypy/ruff)
    能识别这是合法的 prompt→str 函数签名.
    """
    import inspect

    from backend.services.judgment_service import JudgmentService

    sig = inspect.signature(JudgmentService.__init__)
    dsh_param = sig.parameters.get("dsh_caller")
    assert dsh_param is not None, "JudgmentService.__init__ 缺 dsh_caller 参数"
    assert dsh_param.annotation != inspect.Parameter.empty, (
        "dsh_caller 缺类型注解 (F821)"
    )
    # 检查 annotation 是 Callable[[str], str] (或 str | Callable 形式)
    ann_str = str(dsh_param.annotation)
    assert "Callable" in ann_str, (
        f"F821 修复断言: dsh_caller 应为 Callable[[str], str], 实际={ann_str!r}"
    )


def test_action_dsh_caller_field_type_is_callable_not_any():
    """F821 修复断言: ActionService.dsh_caller 是 Callable."""
    import inspect

    from backend.services.action_service import ActionService

    sig = inspect.signature(ActionService.__init__)
    dsh_param = sig.parameters.get("dsh_caller")
    assert dsh_param is not None and dsh_param.annotation != inspect.Parameter.empty
    assert "Callable" in str(dsh_param.annotation), (
        f"F821 修复断言: action dsh_caller 应为 Callable, 实际={dsh_param.annotation!r}"
    )


def test_knowledge_dsh_caller_field_type_is_callable_not_any():
    """F821 修复断言: KnowledgeService.dsh_caller 是 Callable."""
    import inspect

    from backend.services.knowledge_service import KnowledgeService

    sig = inspect.signature(KnowledgeService.__init__)
    dsh_param = sig.parameters.get("dsh_caller")
    assert dsh_param is not None and dsh_param.annotation != inspect.Parameter.empty
    assert "Callable" in str(dsh_param.annotation), (
        f"F821 修复断言: knowledge dsh_caller 应为 Callable, 实际={dsh_param.annotation!r}"
    )


def test_sk01_dsh_caller_field_type_is_callable_not_any():
    """F821 修复断言: DailyPriorityIntelService.dsh_caller 是 Callable."""
    import inspect

    from backend.services.skill_registry.sk01_daily_priority import (
        DailyPriorityIntelService,
    )

    sig = inspect.signature(DailyPriorityIntelService.__init__)
    dsh_param = sig.parameters.get("dsh_caller")
    assert dsh_param is not None and dsh_param.annotation != inspect.Parameter.empty
    assert "Callable" in str(dsh_param.annotation), (
        f"F821 修复断言: sk01 dsh_caller 应为 Callable, 实际={dsh_param.annotation!r}"
    )