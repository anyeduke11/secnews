"""MCP tool 输入模型 — v1 执行域只读导出 (v0.8.7 P3-B)。

外部 agent 只读观测面 (提案/run/产物/案件账本), 不产提案 — 人主律边界。
字段镜像对应 FastAPI 端点查询参数 (ge/le 对齐); 注册表见 mcp_types.MCP_TOOLS。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ListProposalsInput(BaseModel):
    """list_proposals — 列出提案账本 (人主律: 提案 ≠ 事实, 只读)."""

    status: str | None = Field(None, description="done | failed | cancelled | timeout | needs_human")
    kind: str | None = Field(None, description="提案 kind 过滤")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ListRunsInput(BaseModel):
    """list_runs — 按 action 列出执行 run (run 账本)."""

    action_id: str = Field(..., min_length=1, max_length=40, description="所属 action ID")
    status: str | None = Field(None, description="按状态过滤 (如 done/failed)")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ListArtifactsInput(BaseModel):
    """list_artifacts — 按 run 列出产物 (done 必有产物的对账面)."""

    run_id: str = Field(..., min_length=1, max_length=40, description="所属 run ID")
    status: str | None = Field(None, description="按产物状态过滤")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ListCasesInput(BaseModel):
    """list_cases — 列出案件队列."""

    status: list[str] | None = Field(None, description="状态过滤 (可多值)")
    priority: list[str] | None = Field(None, description="优先级过滤 (可多值)")
    owner_role: str | None = Field(None, description="负责人角色")
    subject_id: str | None = Field(None, description="按主体过滤")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
