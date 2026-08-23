"""外部 CLI runner 注册表 schema + 路由 (v0.5 §19.3 T15b).

dsh (DeepSeek Harness) agent 网关的前置: ``config/agents.yaml`` 是
runner 元数据唯一事实源, 本模块提供加载/校验/路由三个纯函数。
agent_bridge.py (M4 Task16, dsh ACP 子进程管理器) 落地后复用
``route()`` 做 task → agent 决策; dsh 侧读同一 YAML spawn 进程。

路由策略 (§19.2):
- 对话/提炼/分类 → builtin DeepSeek (默认)
- 代码重构/跨文件修改 → claude-code
- 快速补丁/单文件生成 → codex
- 用户显式指定 → preferred_agent 覆盖

降级 (§19.4): CLI 未安装时回退 default_agent。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "agents.yaml"


class AgentRunner(BaseModel):
    """单个 CLI runner 注册条目。"""

    command: list[str] = []  # builtin 无外部进程
    protocol: Literal["acp", "stream-json", "jsonl"] = "acp"
    cwd: str | None = None            # 模板 {workspace} → codegarden/<project>/
    task_types: list[str] = []
    timeout_seconds: int = 600        # §19.4: >10min kill


class AgentsConfig(BaseModel):
    """agents.yaml 根 schema。"""

    agents: dict[str, AgentRunner]
    default_agent: str = "builtin"

    @model_validator(mode="after")
    def _validate_default_exists(self) -> AgentsConfig:
        if self.default_agent not in self.agents:
            raise ValueError(
                f"default_agent '{self.default_agent}' not in agents"
            )
        return self


def load_agents_config(path: Path | None = None) -> AgentsConfig | None:
    """加载并校验 agents.yaml; 文件不存在时返回 None (优雅降级)。"""
    config_path = path or _CONFIG_PATH
    if not config_path.exists():
        return None

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        return None

    return AgentsConfig(**raw)


def route(
    task_type: str,
    *,
    preferred_agent: str | None = None,
    available_agents: list[str] | None = None,
    config: AgentsConfig | None = None,
) -> str:
    """task_type → agent 名 (§19.2 路由策略, 纯函数可单测)。

    Args:
        task_type: 任务类型 (chat/summarize/classify/refactor/quick_patch/...)
        preferred_agent: 用户显式指定的 agent (AIView 下拉框), 优先级最高
        available_agents: 当前可用 runner 名列表 (CLI 已安装探测结果);
            None 表示全部可用 (跳过可用性过滤)
        config: 注入配置 (None 时从 agents.yaml 加载)

    Returns 解析后的 agent 名; 显式指定 > 按 task_types 命中 > default。

    Raises ValueError: 配置缺失 / preferred_agent 不存在或不可用。
    """
    cfg = config or load_agents_config()
    if cfg is None:
        raise ValueError("agents.yaml not found — T15b runner registry missing")

    if preferred_agent is not None:
        if preferred_agent not in cfg.agents:
            raise ValueError(f"unknown agent: {preferred_agent}")
        if available_agents is not None and preferred_agent not in available_agents:
            raise ValueError(
                f"agent '{preferred_agent}' not installed — "
                f"available: {available_agents}"
            )
        return preferred_agent

    for name, runner in cfg.agents.items():
        if task_type in runner.task_types:
            if available_agents is None or name in available_agents:
                return name
            break  # 命中的 runner 不可用 → 回退 default (§19.4)
    return cfg.default_agent


def detect_available_agents(config: AgentsConfig | None = None) -> list[str]:
    """探测本机可用的 runner (command 非空且首元素在 PATH 中)。"""
    cfg = config or load_agents_config()
    if cfg is None:
        return []
    return [
        name for name, r in cfg.agents.items()
        if not r.command or shutil.which(r.command[0]) is not None
    ]


__all__ = [
    "AgentRunner",
    "AgentsConfig",
    "detect_available_agents",
    "load_agents_config",
    "route",
]
