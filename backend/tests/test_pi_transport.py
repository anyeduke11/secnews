"""pi_transport 单测 — NDJSON 解析契约 (与 agent_bridge 2026-09-05 实测对齐) + print 子进程。"""
import asyncio
import subprocess

import pytest
from pydantic import ValidationError

from backend.config.llm_schema import LLMConfig, ProviderConfig, ProviderModels
from backend.services.ai_hub.gateway import LLMService
from backend.services.ai_hub.pi_transport import parse_pi_jsonl_events, run_pi_print


class TestParsePiJsonlEvents:
    def test_message_end_assistant_text(self):
        stdout = "\n".join([
            '{"type":"session","id":"s1"}',
            '{"type":"agent_start"}',
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"你好"}]}}',
        ])
        assert parse_pi_jsonl_events(stdout) == "你好"

    def test_user_message_end_skipped(self):
        """实测缺口①: user 消息也发 message_end — 不算结果。"""
        stdout = "\n".join([
            '{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"问题"}]}}',
            '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"答案"}]}}',
        ])
        assert parse_pi_jsonl_events(stdout) == "答案"

    def test_stop_reason_error_returns_none(self):
        """实测缺口②: 上游 429 时 pi rc=0 但 stopReason=error — 显式失败。"""
        stdout = '{"type":"message_end","message":{"role":"assistant","stopReason":"error","content":[]}}'
        assert parse_pi_jsonl_events(stdout) is None

    def test_non_json_lines_fallback_to_last_json(self):
        assert parse_pi_jsonl_events('garbage\n{"result":"x"}') == '{"result":"x"}'

    def test_empty_stdout(self):
        assert parse_pi_jsonl_events("") is None


class TestRunPiPrint:
    def test_model_empty_omits_flag(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout='{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}', stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        out = run_pi_print("提示词", "", 60)
        assert out == "ok"
        assert captured["cmd"] == ["pi", "-p", "--mode", "json"]

    def test_model_passed(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout='{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}', stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        run_pi_print("p", "claude-sonnet-4-5", 30)
        assert captured["cmd"] == ["pi", "-p", "--mode", "json", "--model", "claude-sonnet-4-5"]

    def test_nonzero_exit_raises(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"),
        )
        with pytest.raises(RuntimeError, match="rc=1"):
            run_pi_print("p", "", 10)

    def test_error_stop_reason_raises(self, monkeypatch):
        """stopReason=error (pi rc=0) 必须抛错 — 让 gateway 健康窗口记账。"""
        monkeypatch.setattr(
            subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(
                cmd, 0,
                stdout='{"type":"message_end","message":{"role":"assistant","stopReason":"error","content":[]}}',
                stderr=""),
        )
        with pytest.raises(RuntimeError, match="无有效输出"):
            run_pi_print("p", "", 10)


def test_llm_schema_accepts_pi_type():
    cfg = ProviderConfig(type="pi", models=ProviderModels(score="", ner="", summary=""))
    assert cfg.type == "pi"


def test_llm_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ProviderConfig(type="pi_dev", models=ProviderModels())


def test_llm_config_full_yaml_pi(tmp_path):
    yaml_file = tmp_path / "llm.yaml"
    yaml_file.write_text(
        """
enabled: true
default_provider: pi
fallback_order: [pi]
providers:
  pi:
    type: pi
    models: {score: "", ner: "", summary: ""}
    timeout_seconds: 60
    max_concurrent: 2
""",
        encoding="utf-8",
    )
    cfg = LLMConfig.model_validate(
        __import__("yaml").safe_load(yaml_file.read_text(encoding="utf-8"))
    )
    assert cfg.providers["pi"].type == "pi"
    assert cfg.providers["pi"].max_concurrent == 2


def _pi_cfg():
    return ProviderConfig(
        type="pi", models=ProviderModels(score="", ner="", summary=""),
        timeout_seconds=15, max_concurrent=1,
    )


def test_gateway_call_provider_pi(monkeypatch):
    calls = {}

    def fake_run_pi_print(prompt, model, timeout_seconds):
        calls.update(prompt=prompt, model=model, timeout_seconds=timeout_seconds)
        return "pi 回答"

    monkeypatch.setattr(
        "backend.services.ai_hub.pi_transport.run_pi_print", fake_run_pi_print
    )
    out = asyncio.run(LLMService()._call_provider(
        _pi_cfg(), "", "你好", provider_name="pi_test",
    ))
    assert out == "pi 回答"
    assert calls == {"prompt": "你好", "model": "", "timeout_seconds": 15}


def test_gateway_call_provider_pi_error_propagates(monkeypatch):
    """pi 失败必须上抛 — _call_provider 异常路径记健康窗口后抛给 fallback 循环。"""
    def fake_fail(prompt, model, timeout_seconds):
        raise RuntimeError("pi exit rc=1: boom")

    monkeypatch.setattr(
        "backend.services.ai_hub.pi_transport.run_pi_print", fake_fail
    )
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(LLMService()._call_provider(
            _pi_cfg(), "", "你好", provider_name="pi_test",
        ))


def test_gateway_chat_unsupported_pi():
    """_call_provider_chat 不支持 pi → ValueError → fallback 链跳下一 provider (spec §3.2 明确不做)。"""
    with pytest.raises(ValueError, match="Unsupported provider type for chat: pi"):
        asyncio.run(LLMService()._call_provider_chat(
            _pi_cfg(), "", [{"role": "user", "content": "x"}],
        ))
