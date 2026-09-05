#!/usr/bin/env python3
"""pi live 探针 — V0.8.1 D-d (PRD §4.3.A Phase A: 协议实测, 真机验证)。

用途
----
真机跑 ``pi -p --mode json`` 抓 NDJSON 流, 验证 agent_bridge 的解析契约,
并走 bridge 全链验证 transcript 落库。**仅本地手动执行** (不进 pytest/CI —
依赖本机 pi CLI 与上游 LLM 配额, 零 skip 硬要求下 live 用例不入套件)。

用法
----
    .venv/bin/python scripts/soaktest/pi_live_probe.py [prompt]

2026-09-05 首次实测结论 (pi 0.84.4, provider=sensenova deepseek-v4-flash):
- 事件序列 session/agent_start/turn_start/message_start+message_end×N/turn_end
- message_end.message.content[] type=="text" 段 = 文本 ✓ 契约吻合
- 缺口①: user 消息也发 message_end 且带 text (已修: role=="user" 过滤)
- 缺口②: 上游 429 时 pi rc=0 + assistant stopReason=="error" content=[]
  (已修: 无成功文本返 None → bridge 失败信封, 杜绝用户输入假阳性)
- 当日 sensenova 配额 429 → 成功流样本待配额恢复后重跑本脚本补验
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.agent_bridge import (  # noqa: E402
    _parse_jsonl_events,
    run_agent_task,
)

PROMPT = sys.argv[1] if len(sys.argv) > 1 else "Reply with exactly one word: PONG"


def main() -> int:
    print(f"[probe] pi -p --mode json {PROMPT!r}")
    proc = subprocess.run(
        ["pi", "-p", "--mode", "json", PROMPT],
        capture_output=True, text=True, timeout=180, cwd="/tmp",
    )
    print(f"[probe] rc={proc.returncode} stdout_lines={len(proc.stdout.splitlines())}")
    if proc.stderr.strip():
        print(f"[probe] stderr: {proc.stderr.strip()[:300]}")

    events: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
            events[ev.get("type", "?")] = events.get(ev.get("type", "?"), 0) + 1
        except json.JSONDecodeError:
            print(f"[probe] 非 JSON 行: {line[:120]}")
    print(f"[probe] 事件分布: {events}")

    parsed = _parse_jsonl_events(proc.stdout)
    print(f"[probe] bridge 解析结果: {str(parsed)[:200]!r}")

    # 全链: bridge 走真 pi (含 start/finish_agent_run transcript 落库)
    envelope = run_agent_task("execute", PROMPT, preferred_agent="pi")
    print(f"[probe] run_agent_task: ok={envelope['ok']} "
          f"result={str(envelope.get('result'))[:200]!r} error={envelope.get('error')}")

    # 判定: 上游失败时期望 ok=False 且 error 为干净信封 (非用户输入假阳性)
    stop_reasons = [
        json.loads(l).get("message", {}).get("stopReason")
        for l in proc.stdout.splitlines()
        if l.strip().startswith("{") and '"message_end"' in l
           and json.loads(l).get("message", {}).get("role") == "assistant"
    ]
    upstream_failed = "error" in stop_reasons
    if upstream_failed:
        ok_probe = envelope["ok"] is False
        print(f"[probe] 上游失败路径: 期望 ok=False → {'PASS' if ok_probe else 'FAIL'}")
    else:
        ok_probe = envelope["ok"] is True and parsed
        print(f"[probe] 成功路径: 期望 ok=True + 解析文本 → {'PASS' if ok_probe else 'FAIL'}")
    return 0 if ok_probe else 1


if __name__ == "__main__":
    sys.exit(main())
