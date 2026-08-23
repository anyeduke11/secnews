"""T15b — 外部 CLI runner 注册表测试 (v0.5 §19.3)。

覆盖: config/agents.yaml 加载校验 / route() 路由策略 (§19.2 表) /
CLI 未安装降级 (§19.4)。纯函数无 DB 依赖。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.agent_runner_schema import (
    AgentsConfig,
    AgentRunner,
    detect_available_agents,
    load_agents_config,
    route,
)


class TestLoadAgentsConfig:
    def test_shipped_yaml_valid(self):
        """仓库自带的 agents.yaml 必须通过 schema 校验 — 防配置腐化。"""
        cfg = load_agents_config()
        assert cfg is not None
        assert cfg.default_agent == "builtin"
        # §19.3 规格的两个外部 runner 必须注册
        assert "claude-code" in cfg.agents
        assert "codex" in cfg.agents
        assert cfg.agents["claude-code"].protocol == "stream-json"
        assert cfg.agents["codex"].command[:2] == ["codex", "exec"]

    def test_missing_file_returns_none(self, tmp_path: Path):
        """文件缺失优雅降级返回 None — 不阻塞启动。"""
        assert load_agents_config(tmp_path / "no-such.yaml") is None

    def test_default_agent_must_exist(self):
        """default_agent 指向未注册 agent 必须 raise — 配置错误早暴露。"""
        with pytest.raises(ValueError, match="not in agents"):
            AgentsConfig(
                agents={"a": AgentRunner()},
                default_agent="ghost",
            )


class TestRoute:
    """route() 纯函数 — §19.2 task→agent 映射表的可执行形式。"""

    def test_task_type_mapping(self):
        assert route("refactor") == "claude-code"
        assert route("quick_patch") == "codex"
        assert route("chat") == "builtin"

    def test_unmapped_task_falls_back_to_default(self):
        """未登记的 task_type 走 default_agent — 新任务类型不炸路由。"""
        assert route("unknown_kind") == "builtin"

    def test_preferred_agent_overrides(self):
        """用户显式指定优先级最高 (AIView 下拉框覆盖默认路由)。"""
        assert route(
            "chat", preferred_agent="claude-code") == "claude-code"

    def test_preferred_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown agent"):
            route("chat", preferred_agent="nope")

    def test_preferred_not_installed_raises(self):
        """显式指定的 CLI 未安装必须报错而非静默换人 — 用户意图不可吞掉。"""
        with pytest.raises(ValueError, match="not installed"):
            route("chat", preferred_agent="claude-code",
                  available_agents=["builtin"])

    def test_unavailable_runner_falls_back(self):
        """task_type 命中的 runner 不可用时回退 default (§19.4 降级表)。"""
        assert route(
            "refactor", available_agents=["builtin"]) == "builtin"


def test_detect_available_agents_filters_uninstalled(monkeypatch):
    """PATH 探测: command 为空视为恒可用; 未安装 CLI 被过滤。"""
    import backend.config.agent_runner_schema as m

    cfg = AgentsConfig(agents={
        "builtin": AgentRunner(command=[]),
        "claude-code": AgentRunner(command=["definitely-not-on-path-x9"]),
        "fake": AgentRunner(command=["python3"]),
    })
    monkeypatch.setattr(m, "_CONFIG_PATH", Path("/nonexistent"))
    avail = detect_available_agents(cfg)
    assert "builtin" in avail
    assert "fake" in avail
    assert "claude-code" not in avail
