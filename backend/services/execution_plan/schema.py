"""ExecutionPlan schema v1 — P10 §2 字段对齐 (D1 继承)。

commands 为 argv 级 (list[list[str]]): 逐条列允许的命令, 首元素 = 可执行名。
enforce 语义 (R-3): 实际执行命令必须逐条命中 commands 白名单 (静态白名单 ∩ plan 子集);
writable/readable 相对 workspace 锁定根; network 默认空 = 全禁 (出站控制底线)。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanOutputArtifact(BaseModel):
    """预期产物声明 (P10 §2 output_artifact)。"""

    kind: str = Field(pattern="^(report|file|data|chart|code_patch|message)$")
    title: str = Field(min_length=1, max_length=200)
    acceptance_notes: str = ""


class ExecutionPlan(BaseModel):
    """审批通过的执行边界 — 冻结后 immutable (改 plan = 新 attempt)。"""

    commands: list[list[str]] = Field(
        min_length=1,
        description="允许执行的命令 (argv 级逐条); 执行期逐条比对, 越界即 fail+告警",
    )
    writable_paths: list[str] = Field(default_factory=list)
    readable_paths: list[str] = Field(default_factory=list)
    network: list[str] = Field(
        default_factory=list,
        description="允许出站目标 (域名/IP); 默认空 = 全禁 (出站控制底线)",
    )
    command_timeout_sec: int = Field(default=60, ge=1, le=3600)
    total_timeout_sec: int = Field(default=600, ge=1, le=86400)
    output_artifact: PlanOutputArtifact
