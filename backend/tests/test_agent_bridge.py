"""Agent 桥接测试 — pi 等 CLI runner 的执行路径 (v0.6.3, M4 T15b 落地)。"""
from __future__ import annotations

import sys

import pytest

from backend.config.agent_runner_schema import AgentRunner, AgentsConfig
from backend.services import agent_bridge


@pytest.fixture()
def cfg() -> AgentsConfig:
    """确定性配置: builtin + 假 jsonl runner (python -c 打 NDJSON)。"""
    return AgentsConfig(
        agents={
            "builtin": AgentRunner(command=[], protocol="acp", task_types=["chat", "classify"]),
            "pi": AgentRunner(
                command=[sys.executable, "-c", _FAKE_PI_SCRIPT],
                protocol="jsonl",
                task_types=["execute"],
                timeout_seconds=30,
            ),
            "slow": AgentRunner(
                command=[sys.executable, "-c", "import time; time.sleep(30)"],
                protocol="jsonl",
                task_types=["never_route"],
                timeout_seconds=1,
            ),
        },
        default_agent="builtin",
    )


_FAKE_PI_SCRIPT = (
    "import json\n"
    "print(json.dumps({'type': 'session', 'id': 's1'}))\n"
    "print(json.dumps({'type': 'message_end', 'message': {'content': "
    "[{'type': 'text', 'text': '任务完成: 3 个文件已修改'}]}}))\n"
)


# ---------------------------------------------------------------------------
# 可用性面板
# ---------------------------------------------------------------------------
def test_available_agents_shape(cfg):
    panel = agent_bridge.available_agents(cfg)
    names = {a["name"] for a in panel["agents"]}
    assert names == {"builtin", "pi", "slow"}
    assert panel["default_agent"] == "builtin"
    builtin = next(a for a in panel["agents"] if a["name"] == "builtin")
    assert builtin["external"] is False
    assert builtin["available"] is True


def test_route_execute_prefers_available_cli(cfg):
    # 本机 sys.executable 必然存在 → pi available → execute 路由到 pi
    agent = agent_bridge.run_agent_task("execute", "noop", config=cfg)
    assert agent["agent"] == "pi"


def test_route_unavailable_cli_falls_back_to_default():
    cfg2 = AgentsConfig(
        agents={
            "builtin": AgentRunner(command=[], protocol="acp", task_types=[]),
            "ghost": AgentRunner(command=["definitely-not-installed-cli"], protocol="jsonl", task_types=["execute"]),
        },
        default_agent="builtin",
    )
    assert agent_bridge.run_agent_task("execute", "x", config=cfg2)["agent"] == "builtin"


# ---------------------------------------------------------------------------
# jsonl 协议解析 (pi 契约: message_end.content[] 文本段)
# ---------------------------------------------------------------------------
def test_run_jsonl_parses_message_end_text(cfg):
    result = agent_bridge.run_agent_task("execute", "做点事", config=cfg)
    assert result["ok"] is True
    assert result["agent"] == "pi"
    assert result["result"] == "任务完成: 3 个文件已修改"
    assert result["duration_ms"] is not None


# ---------------------------------------------------------------------------
# jsonl 协议 — pi 0.84.4 live 实测契约 (2026-09-05, V0.8.1 D-d)
# 样本取自真机 `pi -p --mode json` 实捕 (精简), 见 scripts/soaktest/pi_live_probe.py
# ---------------------------------------------------------------------------
def test_jsonl_skips_user_echo_takes_assistant_text():
    """实测缺口①: user 消息也发 message_end 且带 text — 必须取 assistant 的。"""
    stdout = "\n".join([
        '{"type":"session","version":3,"id":"x"}',
        '{"type":"agent_start"}',
        '{"type":"turn_start"}',
        '{"type":"message_end","message":{"role":"user","content":'
        '[{"type":"text","text":"Reply with exactly one word: PONG"}]}}',
        '{"type":"message_end","message":{"role":"assistant","content":'
        '[{"type":"text","text":"PONG"}]}}',
        '{"type":"turn_end"}',
    ])
    assert agent_bridge._parse_jsonl_events(stdout) == "PONG"


def test_jsonl_user_echo_only_returns_fallback_json():
    """只有 user 回显 (无 assistant turn) → 退化为最后一条 JSON 行 (旧行为)。"""
    stdout = "\n".join([
        '{"type":"session","version":3,"id":"x"}',
        '{"type":"message_end","message":{"role":"user","content":'
        '[{"type":"text","text":"hi"}]}}',
    ])
    result = agent_bridge._parse_jsonl_events(stdout)
    assert result is not None and '"type":"message_end"' in result


def test_jsonl_upstream_error_returns_none_not_false_positive():
    """实测缺口②: sensenova 429 → pi rc=0, assistant message_end 带
    stopReason=="error" 且 content=[] → 必须 None (失败信封), 不得把
    user 回显或 JSON 行当结果 (修复前假阳性 ok=True)。"""
    stdout = "\n".join([
        '{"type":"session","version":3,"id":"01a070b8"}',
        '{"type":"agent_start"}',
        '{"type":"turn_start"}',
        '{"type":"message_end","message":{"role":"user","content":'
        '[{"type":"text","text":"Reply with exactly one word: PONG"}]}}',
        '{"type":"message_end","message":{"role":"assistant","content":[],'
        '"provider":"sensenova","model":"deepseek-v4-flash",'
        '"stopReason":"error","errorMessage":"429: quota exceeded"}}',
        '{"type":"turn_end"}',
    ])
    assert agent_bridge._parse_jsonl_events(stdout) is None


def test_run_jsonl_upstream_error_returns_failure_envelope():
    """bridge 全链: 上游失败流 → ok=False 信封 (rc=0 但解析为 None)。"""
    fake = (
        "echo '{\"type\":\"message_end\",\"message\":{\"role\":\"user\","
        "\"content\":[{\"type\":\"text\",\"text\":\"PONG\"}]}}'; "
        "echo '{\"type\":\"message_end\",\"message\":{\"role\":\"assistant\","
        "\"content\":[],\"stopReason\":\"error\"}}'"
    )
    cfg2 = AgentsConfig(
        agents={
            "builtin": AgentRunner(command=[], protocol="acp", task_types=[]),
            "pi": AgentRunner(
                command=["sh", "-c", fake],
                protocol="jsonl", task_types=["execute"], timeout_seconds=30,
            ),
        },
        default_agent="builtin",
    )
    result = agent_bridge.run_agent_task("execute", "x", config=cfg2)
    assert result["ok"] is False
    assert "无可解析输出" in result["error"]


def test_run_nonzero_exit_returns_error_envelope():
    cfg2 = AgentsConfig(
        agents={
            "builtin": AgentRunner(command=[], protocol="acp", task_types=[]),
            "bad": AgentRunner(
                command=[sys.executable, "-c", "import sys; print('boom'); sys.exit(2)"],
                protocol="jsonl", task_types=["execute"], timeout_seconds=30,
            ),
        },
        default_agent="builtin",
    )
    result = agent_bridge.run_agent_task("execute", "x", config=cfg2)
    assert result["ok"] is False
    assert "rc=2" in result["error"]


def test_run_timeout_kills_and_reports():
    result = agent_bridge.run_agent_task("never_route", "x", preferred_agent="slow", config=_slow_cfg())
    assert result["ok"] is False
    assert "timeout" in result["error"]


def _slow_cfg() -> AgentsConfig:
    return AgentsConfig(
        agents={
            "builtin": AgentRunner(command=[], protocol="acp", task_types=[]),
            "slow": AgentRunner(
                command=[sys.executable, "-c", "import time; time.sleep(30)"],
                protocol="jsonl", task_types=["never_route"], timeout_seconds=1,
            ),
        },
        default_agent="builtin",
    )


def test_unknown_preferred_agent_rejected(cfg):
    result = agent_bridge.run_agent_task("execute", "x", preferred_agent="nope", config=cfg)
    assert result["ok"] is False
    assert "unknown agent" in result["error"]


# ---------------------------------------------------------------------------
# workspace 安全边界 (§19.3-3: 仅 codegarden/<project>/)
# ---------------------------------------------------------------------------
def test_workspace_outside_codegarden_rejected():
    with pytest.raises(ValueError):
        agent_bridge._resolve_workspace("/etc")
    with pytest.raises(ValueError):
        agent_bridge._resolve_workspace("../escape")
    assert agent_bridge._resolve_workspace("codegarden/myproj") == "codegarden/myproj"
    assert agent_bridge._resolve_workspace(None) is None
    assert agent_bridge._resolve_workspace("") is None


# ---------------------------------------------------------------------------
# builtin → ai_hub (LLM 单出口契约)
# ---------------------------------------------------------------------------
def test_builtin_dispatches_to_ai_hub(cfg, monkeypatch):

    class FakeLLM:
        async def generate(self, prompt, *, task="summary", **kw):
            assert prompt == "分类一下"
            return "security"

    import backend.services.ai_hub as ai_hub_pkg
    monkeypatch.setattr(ai_hub_pkg, "LLMService", FakeLLM)

    result = agent_bridge.run_agent_task("classify", "分类一下", config=cfg)
    assert result["ok"] is True
    assert result["agent"] == "builtin"
    assert result["result"] == "security"


def test_agents_yaml_loads_in_repo():
    """仓库自带 agents.yaml 必须可加载且含 pi (契约防漂移)。"""
    from backend.config.agent_runner_schema import load_agents_config
    cfg = load_agents_config()
    assert cfg is not None
    assert "pi" in cfg.agents
    assert "builtin" in cfg.agents
