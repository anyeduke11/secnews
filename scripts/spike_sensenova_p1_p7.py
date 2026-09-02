"""spike: sensenova OpenAI 兼容范围深探 (P1-P7) + 切换路径压力测试。

设计要点 (v0.7.x gateway S2 黑盒广度探针):
- 不引入 pytest 框架 (与测试隔离; spike 是临时验证, 不进 CI)
- 不写死 key 字面量 (从 .env 读 SENSENOVA_API_KEY, 进程内不打印)
- 长超时 (30s) + 串行重试 3 次 (避免网络 flake 误判)
- 探测 7 个能力: response_format / function_calling / streaming / multimodal / logprobs
- 输出 JSON verdict, 便于脚本消费 (人/AI 都可解析)
- 跑完即用, 不修改 db / 不引入迁移

用法
----
::

    .venv/bin/python scripts/spike_sensenova_p1_p7.py
    .venv/bin/python scripts/spike_sensenova_p1_p7.py --target streaming  # 只跑 P5
    .venv/bin/python scripts/spike_sensenova_p1_p7.py --retries 5         # 5 次重试

依据: docs/crawler-aihub-gateway.md §3.2 + memory hotspot-gateway-s1-s4-spike-flow
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import sys
import time
from typing import Any

import httpx


def _key() -> str:
    """从 env 或 .env 读 SENSENOVA_API_KEY, 不打印字面量。"""
    val = os.environ.get("SENSENOVA_API_KEY", "")
    if not val:
        try:
            for line in open("/Users/duke/Documents/hotspot/.env"):
                if line.startswith("SENSENOVA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            pass
    return val


BASE = "https://token.sensenova.cn/v1"
MODEL = "sensenova-6.8-flash-lite"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3


def _retry(fn, name: str, retries: int = DEFAULT_RETRIES) -> dict:
    """串行重试 — 探针内失败 (ReadTimeout/ConnectError) 时重试; 4xx 业务错不重试 (持续性问题)。"""
    last = None
    for attempt in range(1, retries + 1):
        result = fn()
        last = result
        if result.get("ok"):
            result["attempts"] = attempt
            return result
        # 业务错 (4xx) 不重试
        status = result.get("status", 0)
        if 400 <= status < 500:
            result["attempts"] = attempt
            result["verdict"] = "BUSINESS_4XX_NO_RETRY"
            return result
        # 5xx 或网络错 → 重试
        if attempt < retries:
            time.sleep(1.5 * attempt)  # 1.5s/3s 退避
    last["attempts"] = retries
    last["verdict"] = "FAILED_AFTER_RETRIES"
    return last


def probe(name: str, payload: dict, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """发一个最小请求, 记录 status + latency + 关键 body 字段。"""
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(
                f"{BASE}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {_key()}",
                    "Content-Type": "application/json",
                },
            )
        dt = (time.time() - t0) * 1000
        ok = 200 <= r.status_code < 300
        body: dict[str, Any] = {}
        try:
            body = r.json()
        except Exception:
            body = {"_raw": r.text[:300]}
        return {
            "name": name,
            "status": r.status_code,
            "ok": ok,
            "latency_ms": round(dt, 1),
            "body_keys": list(body.keys()) if isinstance(body, dict) else [],
            "error_type": (body.get("error") or {}).get("type") if isinstance(body, dict) else None,
            "error_msg": ((body.get("error") or {}).get("message") or "")[:200] if isinstance(body, dict) else "",
            "content_preview": (
                ((body.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")[:120]
                if isinstance(body, dict) else ""
            ),
            "finish_reason": ((body.get("choices") or [{}])[0].get("finish_reason")) if isinstance(body, dict) else None,
            "tool_calls": (
                ((body.get("choices") or [{}])[0].get("message", {}) or {}).get("tool_calls")
                if isinstance(body, dict) else None
            ),
        }
    except Exception as e:
        return {
            "name": name,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


def probe_streaming(name: str, payload: dict, *, timeout: float = 30.0) -> dict:
    """streaming 探针 — 用 httpx.stream() 读第一个 SSE chunk。"""
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            with c.stream(
                "POST",
                f"{BASE}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
            ) as r:
                ct = r.headers.get("content-type", "")
                first_chunk = ""
                chunk_count = 0
                for chunk in r.iter_text(chunk_size=128):
                    first_chunk = chunk[:120]
                    chunk_count += 1
                    if chunk_count >= 3:
                        break
        dt = (time.time() - t0) * 1000
        return {
            "name": name,
            "status": r.status_code,
            "ok": r.status_code == 200,
            "latency_ms": round(dt, 1),
            "content_type": ct,
            "first_chunk_preview": first_chunk,
            "chunk_count_sampled": chunk_count,
        }
    except Exception as e:
        return {"name": name, "ok": False, "error": f"{type(e).__name__}: {e}"}


def make_valid_png_b64() -> str:
    """用 PIL 生成 valid 2x2 PNG (字节序列必须可被 sensenova image 解码)。"""
    try:
        from PIL import Image
        from io import BytesIO

        buf = BytesIO()
        Image.new("RGB", (2, 2), color=(255, 0, 0)).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        # 退路 — 用最小可解码 1x1 PNG (字节序列已通过先前 spike 验证可解码)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc```\x00\x00\x00\x06\x00\x03"
            b"\x00\x01\x0e\xf3\x9a\xc4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return base64.b64encode(png_bytes).decode()


def main():
    parser = argparse.ArgumentParser(description="sensenova OpenAI 兼容范围探针")
    parser.add_argument("--target", choices=["all", "p1", "p2", "p3", "p4", "p5", "p6", "p7"], default="all")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="失败重试次数 (默认 3)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次超时 (默认 30s)")
    args = parser.parse_args()

    if not _key():
        print(json.dumps({"fatal": "SENSENOVA_API_KEY missing in env/.env"}, indent=2), file=sys.stderr)
        sys.exit(2)

    base = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "max_tokens": 256,  # 必须 ≥128 否则 flash-lite 触发 length-limit (sp2 经验)
    }

    probes: dict[str, callable] = {
        "p1": lambda: probe(
            "P1_baseline_ping",
            {**base, "temperature": 0},
            timeout=args.timeout,
        ),
        "p2": lambda: probe(
            "P2_response_format_json",
            {**base, "temperature": 0,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": 'reply {"v":1}'}]},
            timeout=args.timeout,
        ),
        "p3": lambda: probe(
            "P3_tools_function_calling",
            {**base, "temperature": 0,
             "tools": [{
                 "type": "function",
                 "function": {
                     "name": "ping",
                     "description": "echo back",
                     "parameters": {"type": "object", "properties": {"msg": {"type": "string"}}, "required": []},
                 },
             }],
             "messages": [{"role": "user", "content": "say hi"}]},
            timeout=args.timeout,
        ),
        "p4": lambda: probe(
            "P4_tool_choice_required",
            {**base, "temperature": 0,
             "tools": [{
                 "type": "function",
                 "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}},
             }],
             "tool_choice": {"type": "function", "function": {"name": "ping"}},
             "messages": [{"role": "user", "content": "call ping"}]},
            timeout=args.timeout,
        ),
        "p5": lambda: probe_streaming(
            "P5_streaming",
            {**base, "stream": True, "temperature": 0},
            timeout=args.timeout,
        ),
        "p6": lambda: probe(
            "P6_multimodal_image",
            {**base, "temperature": 0,
             "messages": [{
                 "role": "user",
                 "content": [
                     {"type": "text", "text": "描述这张图"},
                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{make_valid_png_b64()}"}},
                 ],
             }],
             "max_tokens": 128},
            timeout=args.timeout,
        ),
        "p7": lambda: probe(
            "P7_logprobs",
            {**base, "temperature": 0, "logprobs": True, "top_logprobs": 1},
            timeout=args.timeout,
        ),
    }

    if args.target == "all":
        run_order = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
    else:
        run_order = [args.target]

    results = []
    for k in run_order:
        result = _retry(probes[k], k, retries=args.retries)
        results.append(result)

    summary = {
        "base_url": BASE,
        "model": MODEL,
        "n_probes": len(results),
        "passed": sum(1 for r in results if r.get("ok")),
        "retries": args.retries,
        "timeout_s": args.timeout,
        "results": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    # 退出码: 全部通过 = 0, 有失败 = 1 (CI 友好)
    sys.exit(0 if summary["passed"] == summary["n_probes"] else 1)


if __name__ == "__main__":
    main()