"""Agent 桥接 — 外部 CLI runner 的执行宿主 (v0.6.3, 落地 M4 T15b/§19.3)。

三层架构裁决 (2026-08-24) 的执行层落地: dsh 出决策 → **pi 等轻量级
CLI agent 落地执行**。``config/agents.yaml`` 是 runner 元数据唯一事实源
(backend/config/agent_runner_schema.py 提供加载/校验/路由纯函数), 本模块
补齐缺失的执行路径:

- ``detect_available_agents()`` — 复用 schema 纯函数探测本机 CLI
- ``run_agent_task(task_type, input, ...)`` — 路由决策 (preferred_agent
  覆盖 > task_types 命中 > default) + 子进程执行 + 协议解析

协议处理 (yaml ``protocol`` 字段):
- ``jsonl``     — stdout 逐行 JSON 事件流 (pi --mode json); 取最后一条
                  ``message_end`` 事件的 content[] 文本段, 退化为最后一条
                  可解析 JSON 行
- ``stream-json`` — claude --print --output-format stream-json; 取最后一条
                  含 ``result`` 键的事件
- ``acp``       — builtin (无外部进程), 直接走 ai_hub LLM 单出口

安全边界 (§19.3-3): ``cwd`` 模板仅允许展开到 ``codegarden/<project>/``;
timeout 到点 kill 并标 failed (§19.4); CLI 未安装时路由回退 default_agent。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from backend.config.agent_runner_schema import (
    AgentsConfig,
    detect_available_agents,
    load_agents_config,
    route,
)
from backend.logging_config import logger
from backend.observability import reset_trace_id, set_trace_id
from backend.observability_records import finish_agent_run, start_agent_run

# {workspace} 模板只允许落在 codegarden/<project>/ 下 (agents.yaml §19.3-3)
_WORKSPACE_ROOT = Path("codegarden")


# ---------------------------------------------------------------------------
# 路由与可用性
# ---------------------------------------------------------------------------
def available_agents(config: AgentsConfig | None = None) -> dict[str, Any]:
    """runner 可用性面板数据 (前端下拉/状态用)。"""
    cfg = config or load_agents_config()
    if cfg is None:
        return {"agents": [], "default_agent": "builtin"}
    installed = set(detect_available_agents(cfg))
    agents = [
        {
            "name": name,
            "protocol": r.protocol,
            "task_types": r.task_types,
            "timeout_seconds": r.timeout_seconds,
            "external": bool(r.command),
            "available": (not r.command) or (name in installed),
        }
        for name, r in cfg.agents.items()
    ]
    return {"agents": agents, "default_agent": cfg.default_agent}


def _resolve_workspace(workspace: str | None) -> str | None:
    """校验 workspace 模板展开目标: 仅允许 codegarden/<project>/ 子路径。"""
    if not workspace or not workspace.strip():
        return None
    ws = Path(workspace.strip())
    if ws.is_absolute() or ".." in ws.parts:
        raise ValueError(f"workspace 必须是 codegarden/<project>/ 相对路径: {workspace}")
    if ws.parts[:1] != _WORKSPACE_ROOT.parts or len(ws.parts) < 2:
        raise ValueError(f"workspace 锁定 codegarden/<project>/: {workspace}")
    return str(ws)


# ---------------------------------------------------------------------------
# 协议解析
# ---------------------------------------------------------------------------
def _parse_jsonl_events(stdout: str) -> str | None:
    """pi `--mode json` NDJSON 事件流: message_end.content[] 文本段优先。

    2026-09-05 pi 0.84.4 live 实测对齐 (V0.8.1 D-d): 事件序列
    session → agent_start → turn_start → (message_start/message_end × N) →
    turn_end; 文本在 ``message.content[]`` 的 ``type=="text"`` 段。
    实测抓到的两个缺口:
    ① **user 消息也发 message_end 且带 text 段** — 不滤会把用户输入当结果
       (role=="user" 跳过; 无 role 的历史样本保持旧行为);
    ② **上游 LLM 失败 (429 等) 时 pi 仍 rc=0**, assistant message_end 带
       ``stopReason=="error"`` 且 content=[] — 标记 errored, 无成功文本时
       返回 None (让 run_agent_task 走失败信封, 而非退化成 JSON 行假阳性)。
    """
    final_text: str | None = None
    last_json_text: str | None = None
    assistant_errored = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        last_json_text = line
        if event.get("type") == "message_end":
            message = event.get("message", {})
            if message.get("role") == "user":
                continue  # 实测缺口①: 用户回显不算结果
            if message.get("stopReason") == "error":
                assistant_errored = True  # 实测缺口②: 上游失败
                continue
            content = message.get("content", [])
            texts = [
                seg.get("text", "") for seg in content
                if isinstance(seg, dict) and seg.get("type") == "text"
            ]
            if texts:
                final_text = "\n".join(t for t in texts if t)
    if final_text:
        return final_text
    if assistant_errored:
        return None  # 上游失败显式失败, 不退化成 JSON 行假阳性
    return last_json_text


def _parse_stream_json(stdout: str) -> str | None:
    """claude stream-json: 最后一条含 result 键的事件。"""
    result: str | None = None
    last_json_text: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        last_json_text = line
        if "result" in event:
            result = str(event["result"])
    return result or last_json_text


def _parse_output(protocol: str, stdout: str) -> str | None:
    if protocol == "stream-json":
        return _parse_stream_json(stdout)
    if protocol == "jsonl":
        return _parse_jsonl_events(stdout)
    # acp / 未知协议: 原样返回非空 stdout
    return stdout.strip() or None


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def run_agent_task(
    task_type: str,
    input_text: str,
    *,
    preferred_agent: str | None = None,
    workspace: str | None = None,
    payload: dict[str, Any] | None = None,
    config: AgentsConfig | None = None,
) -> dict[str, Any]:
    """执行一次 agent 任务, 返回统一结果信封。

    builtin agent → ai_hub generate (LLM 单出口); 外部 CLI → 子进程
    (stdin 喂 JSON 任务书, stdout 按协议解析)。失败不抛异常, 一律
    ``{"ok": False, "error": ...}`` 信封。
    """
    cfg = config or load_agents_config()
    if cfg is None:
        return {"ok": False, "error": "agents.yaml 缺失 — runner 注册表未初始化", "agent": None}

    installed = detect_available_agents(cfg)
    try:
        agent_name = route(
            task_type,
            preferred_agent=preferred_agent,
            available_agents=installed,
            config=cfg,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "agent": None}

    runner = cfg.agents[agent_name]
    started = time.monotonic()
    trace_id = f"agent:{agent_name}:{int(time.time())}"
    token = set_trace_id(trace_id)
    run_rowid = start_agent_run(
        agent=agent_name,
        protocol=runner.protocol,
        task_kind=task_type,
        trigger_source="api",
    )
    try:
        # builtin — 无外部进程, 走 ai_hub LLM 单出口
        if not runner.command:
            builtin_result = _run_builtin(agent_name, task_type, input_text, started)
            finish_agent_run(
                run_rowid,
                ok=bool(builtin_result.get("ok")),
                duration_ms=builtin_result.get("duration_ms") or 0,
                result_excerpt=str(builtin_result.get("result"))[:500]
                    if builtin_result.get("ok") else None,
                error=builtin_result.get("error"),
            )
            return builtin_result

        # 外部 CLI
        cwd = _resolve_workspace(workspace)
        stdin_payload = json.dumps(
            {"task_type": task_type, "input": input_text, "payload": payload or {}},
            ensure_ascii=False,
        )
        try:
            proc = subprocess.run(
                runner.command + [input_text],
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=runner.timeout_seconds,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            logger.warning("agent %s timeout after %ss", agent_name, runner.timeout_seconds)
            result = {
                "ok": False, "agent": agent_name, "protocol": runner.protocol,
                "error": f"timeout after {runner.timeout_seconds}s (§19.4 kill)",
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
            finish_agent_run(
                run_rowid, ok=False, duration_ms=result["duration_ms"],
                error=result["error"],
            )
            return result
        except OSError as e:
            duration_ms = round((time.monotonic() - started) * 1000)
            finish_agent_run(
                run_rowid, ok=False, duration_ms=duration_ms,
                error=f"spawn failed: {e}",
            )
            return {"ok": False, "agent": agent_name, "error": f"spawn failed: {e}",
                    "duration_ms": duration_ms}

        duration_ms = round((time.monotonic() - started) * 1000)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            finish_agent_run(
                run_rowid, ok=False, duration_ms=duration_ms,
                error=f"exit rc={proc.returncode}: {tail}",
            )
            return {
                "ok": False, "agent": agent_name, "protocol": runner.protocol,
                "error": f"exit rc={proc.returncode}: {tail}",
                "duration_ms": duration_ms,
            }

        result = _parse_output(runner.protocol, proc.stdout)
        ok = result is not None
        finish_agent_run(
            run_rowid, ok=ok, duration_ms=duration_ms,
            result_excerpt=str(result)[:500] if ok else None,
            error=None if ok else "stdout 无可解析输出",
        )
        return {
            "ok": ok,
            "agent": agent_name,
            "protocol": runner.protocol,
            "result": result,
            "error": None if ok else "stdout 无可解析输出",
            "duration_ms": duration_ms,
        }
    finally:
        reset_trace_id(token)


def _run_builtin(agent_name: str, task_type: str, input_text: str, started: float) -> dict[str, Any]:
    """builtin runner → ai_hub generate (LLM 单出口契约)。

    仅返回结果信封, 不负责写 agent_runs — 由调用方 run_agent_task 在拿到
    返回值后调 finish_agent_run 落库。trace_id 已被调用方注入, 内层
    ai_hub LLM 调用自动关联。
    """
    import asyncio

    from backend.services.ai_hub import LLMService

    async def _call() -> str:
        return await LLMService().generate(input_text, task="summary")

    try:
        raw = asyncio.run(_call())
    except Exception as e:
        return {"ok": False, "agent": agent_name, "error": f"ai_hub generate failed: {e}"}
    return {
        "ok": bool(raw),
        "agent": agent_name,
        "protocol": "acp",
        "result": raw or None,
        "error": None if raw else "LLM 未启用或返回空",
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


__all__ = ["available_agents", "run_agent_task"]
