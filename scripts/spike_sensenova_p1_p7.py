"""spike: sensenova OpenAI 兼容范围深探 (P1-P8) + 切换路径压力测试。

设计要点 (v0.7.x gateway S2 黑盒广度探针):
- 不引入 pytest 框架 (与测试隔离; spike 是临时验证, 不进 CI)
- 不写死 key 字面量 (从 .env 读 SENSENOVA_API_KEY, 进程内不打印)
- 长超时 (30s) + 串行重试 3 次 (避免网络 flake 误判)
- 探测 8 个能力: response_format / function_calling / streaming / multimodal / logprobs / image_generation
- 输出 JSON verdict, 便于脚本消费 (人/AI 都可解析)
- 跑完即用, 不修改 db / 不引入迁移

用法
----
::

    .venv/bin/python scripts/spike_sensenova_p1_p7.py
    .venv/bin/python scripts/spike_sensenova_p1_p7.py --target p8        # 只跑 P8 image generation
    .venv/bin/python scripts/spike_sensenova_p1_p7.py --retries 5        # 5 次重试

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
IMAGE_MODEL = "sensenova-u1.5-lite"  # image generation 模型 (与文本 chat 模型不同)
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3

# 3 场景路由 (2026-09-02 用户裁决 + GET /v1/models 官方清单实证)
# 依据: https://platform.sensenova.cn/docs (模型总览) + 实测 8 个 model ID 可调用
# 深度场景 (复杂 Agent / 推理 / 长上下文): deepseek-v4-pro (1M 上下文 + 思考模式)
# 轻度场景 (日常问答 / 代码辅助 / 规模化):   deepseek-v4-flash / sensenova-6.8-flash-lite
# 图片场景 (生成 / 编辑):                   sensenova-u1.5-lite / sensenova-u1-fast
DEEP_MODEL = "deepseek-v4-pro"      # 思考深度高的场景
LIGHT_MODEL = "deepseek-v4-flash"   # 轻度场景
LIGHT_MODEL_ALT = "sensenova-6.8-flash-lite"  # sensenova 原生轻度场景备选
IMAGE_GEN_MODEL = "sensenova-u1.5-lite"  # 图片场景 (与 IMAGE_MODEL 同名)


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


def probe_image(name: str, payload: dict, *, timeout: float = 60.0) -> dict:
    """image generation 探针 — POST /v1/images/generations (OpenAI 同构端点)。

    与 chat 路径不同: 端点不是 /chat/completions 而是 /images/generations;
    模型是 sensenova-u1.5-lite (不是 sensenova-6.8-flash-lite);
    response_format 仅支持 'b64_json' (没有 'url' 选项, 推测为版权保护);
    watermark=false 公测期间免费去水印。
    """
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(
                f"{BASE}/images/generations",
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
        # image generation 响应结构: {created, data:[{b64_json}], usage}
        data_list = body.get("data") if isinstance(body, dict) else None
        b64_preview = ""
        if isinstance(data_list, list) and data_list:
            first = data_list[0] if isinstance(data_list[0], dict) else {}
            b64 = first.get("b64_json") or ""
            b64_preview = f"<{len(b64)} chars>" if b64 else ""
        return {
            "name": name,
            "status": r.status_code,
            "ok": ok,
            "latency_ms": round(dt, 1),
            "body_keys": list(body.keys()) if isinstance(body, dict) else [],
            "error_type": (body.get("error") or {}).get("type") if isinstance(body, dict) else None,
            "error_msg": ((body.get("error") or {}).get("message") or "")[:200] if isinstance(body, dict) else "",
            "data_count": len(data_list) if isinstance(data_list, list) else 0,
            "b64_json_preview": b64_preview,
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
    parser.add_argument("--target", choices=["all", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11"], default="all")
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
        # P8 image generation — 独立端点 /v1/images/generations, 模型 sensenova-u1.5-lite
        "p8": lambda: probe_image(
            "P8_image_generation",
            {
                "model": IMAGE_MODEL,
                "prompt": "a baby otter floating on calm sea at dawn, soft morning light, photorealistic",
                "n": 1,
                "size": "1024x1024",
                "output_format": "png",
                "response_format": "b64_json",
                "watermark": True,
            },
            timeout=args.timeout,
        ),
        # P9 deep 场景 — deepseek-v4-pro (1M 上下文 + 思考模式)
        # 用 complex reasoning 提示验证深度推理能力
        "p9": lambda: probe(
            "P9_deep_reasoning_deepseek_v4_pro",
            {
                "model": DEEP_MODEL,
                "messages": [{"role": "user", "content": (
                    "A train leaves Beijing at 09:00 at 120 km/h. Another leaves Shanghai at 10:00 "
                    "at 150 km/h toward Beijing on the same line (1312 km). At what time do they meet? "
                    "Reply with a JSON object {time, distance_from_beijing_km, distance_from_shanghai_km}."
                )}],
                "temperature": 0,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
            },
            timeout=args.timeout,
        ),
        # P10 light 场景 — deepseek-v4-flash (日常问答, 经济型)
        "p10": lambda: probe(
            "P10_light_qa_deepseek_v4_flash",
            {
                "model": LIGHT_MODEL,
                "messages": [{"role": "user", "content": "用一句话解释什么是 HTTP 状态码 404?"}],
                "temperature": 0,
                "max_tokens": 128,
            },
            timeout=args.timeout,
        ),
        # P11 轻量 alt — sensenova-6.8-flash-lite (sensenova 原生轻度模型, 已大量生产)
        "p11": lambda: probe(
            "P11_light_alt_sensenova_flash_lite",
            {
                "model": LIGHT_MODEL_ALT,
                "messages": [{"role": "user", "content": "用一句话解释什么是 HTTP 状态码 404?"}],
                "temperature": 0,
                "max_tokens": 128,
            },
            timeout=args.timeout,
        ),
    }

    if args.target == "all":
        run_order = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11"]
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