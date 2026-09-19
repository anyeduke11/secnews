"""pi 传输层 — NDJSON 解析共享纯函数 + print 模式子进程 (2026-09-18 方案 B)。

NDJSON 解析自 agent_bridge._parse_jsonl_events 提取为单点实现:
ai_hub pi provider (gateway type=="pi") 与 agent_bridge jsonl 协议共用,
禁止两处实现。协议契约来自 2026-09-05 pi 0.84.4 live 实测 (V0.8.1 D-d):
- user 消息也发 message_end → role=="user" 跳过;
- 上游 429 时 pi 仍 rc=0, assistant message_end 带 stopReason=="error"
  且 content=[] → 解析返回 None (调用方视为失败)。

认证: ``~/.pi/agent/auth.json`` 由 pi 自管, 本模块不触碰任何密钥。
prompt 经 stdin 传入 (防 ARG_MAX / 命令注入), 不走 argv。
"""
from __future__ import annotations

import json
import subprocess


def parse_pi_jsonl_events(stdout: str) -> str | None:
    """pi `--mode json` NDJSON 事件流 → 最终文本 (None = 失败/空流)。"""
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


def run_pi_print(prompt: str, model: str, timeout_seconds: int = 60) -> str:
    """同步执行 `pi -p --mode json [--model M]`, prompt 走 stdin, 返回最终文本。

    任何失败 (非零退出 / stopReason=error / 空流 / 超时) 都抛异常 —
    gateway._call_provider 的健康窗口 / 熔断记账依赖异常路径。
    """
    cmd = ["pi", "-p", "--mode", "json"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"pi timeout after {timeout_seconds}s") from e
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        raise RuntimeError(f"pi exit rc={proc.returncode}: {tail}")
    result = parse_pi_jsonl_events(proc.stdout)
    if result is None:
        raise RuntimeError("pi 无有效输出 (上游失败或空流)")
    return result


__all__ = ["parse_pi_jsonl_events", "run_pi_print"]
