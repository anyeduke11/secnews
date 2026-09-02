"""S1-S3 spike — gateway 方案第 2 步前置验证 (一次性脚本, 不入测试).

S3 黑盒: litellm → 本地 mock server, 收包看 path / model 原样 / extra_headers 注入
S1 黑盒: AsyncWebCrawler + LLMExtractionStrategy (mock 延迟 2s) + loop-lag 探针
S2 黑盒: sensenova 原生 response_format=json_object 支持度 (真实出站 1 条)

安全: 凭据仅从 env 读取, 不打印; mock server 只绑 127.0.0.1 随机端口。
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

captured: list[dict] = []


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        captured.append(
            {
                "path": self.path,
                "model_raw": body.get("model"),
                "has_response_format": "response_format" in body,
                "response_format": body.get("response_format"),
                "trace_header": self.headers.get("X-Trace-Id"),
                "num_messages": len(body.get("messages", [])),
            }
        )
        # S1 用: mock 延迟 2s, 观察 loop 是否被阻塞
        time.sleep(2.0)
        resp = {
            "id": "chatcmpl-spike",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '[{"title": "spike", "url": "https://x"}]'},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # 静默
        pass


def start_mock() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}/v1"


# ── S3: litellm 前缀 / headers / response_format 透传 ─────────────────


async def s3_litellm_blackbox(mock_url: str) -> dict:
    from litellm import acompletion

    captured.clear()
    await acompletion(
        model="openai/test-spike-model",
        messages=[{"role": "user", "content": "ping"}],
        api_key="dummy-not-a-real-key",
        base_url=mock_url,
        extra_headers={"X-Trace-Id": "trace-from-collector-123"},
        extra_body={},
    )
    c = captured[0] if captured else {}
    return {
        "path": c.get("path"),
        "model_raw": c.get("model_raw"),
        "trace_header_injected": c.get("trace_header"),
        "has_response_format": c.get("has_response_format"),
    }


async def s3b_crawl4ai_response_format(mock_url: str) -> dict:
    """crawl4ai force_json_response=True 时是否发 response_format + prompt 形态."""
    from crawl4ai import LLMConfig
    from crawl4ai.extraction_strategy import LLMExtractionStrategy

    captured.clear()
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="openai/spike-model",
            api_token="dummy-not-a-real-key",
            base_url=mock_url,
        ),
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
        force_json_response=True,
        apply_chunking=False,
        verbose=False,
        extra_args={"timeout": 30},
    )
    await strategy.arun("https://example.com/spike", ["<html>spike content</html>"])
    c = captured[0] if captured else {}
    return {
        "model_raw": c.get("model_raw"),
        "response_format": c.get("response_format"),
        "num_messages": c.get("num_messages"),
    }


# ── S1: loop-lag 探针 × AsyncWebCrawler + LLMExtractionStrategy ────────


async def s1_loop_lag(mock_url: str) -> dict:
    """同 loop 直测 strategy.arun() × loop-lag 探针.

    白盒已确认 crawler 走 arun (async_webcrawler.py:932) → aextract →
    litellm acompletion; 本测把 lag 探针与 strategy.arun 放同一事件循环,
    mock 延迟 2s — 若 acompletion 阻塞 loop, lag 会飙到 ~2000ms。
    (不启 Chromium: 生产路径的 loop 归属与直接 await strategy.arun 等价)
    """
    from crawl4ai import LLMConfig
    from crawl4ai.extraction_strategy import LLMExtractionStrategy

    captured.clear()
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="openai/spike-model",
            api_token="dummy-not-a-real-key",
            base_url=mock_url,
        ),
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
        force_json_response=True,
        apply_chunking=False,
        verbose=False,
        extra_args={"timeout": 30},
    )

    lags: list[float] = []
    stop = asyncio.Event()

    async def lag_probe():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.05)
            now = time.monotonic()
            lags.append((now - last - 0.05) * 1000)
            last = now

    probe = asyncio.create_task(lag_probe())
    t0 = time.monotonic()
    blocks = await strategy.arun(
        "https://example.com/spike", ["<html>spike content for extraction</html>"]
    )
    elapsed = time.monotonic() - t0
    stop.set()
    await probe

    lags_sorted = sorted(lags)
    mx = lags_sorted[-1] if lags_sorted else 0.0
    return {
        "elapsed_s": round(elapsed, 2),
        "blocks": len(blocks) if isinstance(blocks, list) else "?",
        "llm_calls": len(captured),
        "lag_max_ms": round(mx, 1),
        "verdict": "NOT-BLOCKED" if mx < 500 else "BLOCKED",
    }


# ── S2: sensenova response_format 探针 (真实出站 1 条) ────────────────


async def s2_sensenova() -> dict:
    import httpx

    key = os.environ.get("SENSENOVA_API_KEY")
    if not key:
        # 从 .env 读 (仅进程内, 不打印值)
        for line in open(".env"):
            if line.startswith("SENSENOVA_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    if not key:
        return {"error": "SENSENOVA_API_KEY not found"}

    base = "https://token.sensenova.cn/v1"  # 仓库 AIService._base_url('sensenova') 实测值
    url = f"{base}/chat/completions"
    out: dict = {}
    for label, extra in (
        ("with_response_format", {"response_format": {"type": "json_object"}}),
        ("without_response_format", {}),
    ):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": "sensenova-6.8-flash-lite",
                        "messages": [{"role": "user", "content": '输出 JSON: {"ok": true}'}],
                        "max_tokens": 32,
                        **extra,
                    },
                )
            out[label] = {
                "status": r.status_code,
                "content_type": r.headers.get("content-type", "")[:30],
                "body_head": r.text[:200] if r.status_code != 200 else "(ok)",
            }
        except Exception as e:
            out[label] = {"error": f"{type(e).__name__}: {e}"}
    return out


async def main():
    srv, mock_url = start_mock()
    print(f"mock server: {mock_url}\n")

    print("=== S3a: litellm → mock (前缀/headers) ===")
    print(json.dumps(await s3_litellm_blackbox(mock_url), ensure_ascii=False, indent=2))

    print("\n=== S3b: crawl4ai strategy → mock (response_format) ===")
    print(json.dumps(await s3b_crawl4ai_response_format(mock_url), ensure_ascii=False, indent=2))

    print("\n=== S1: loop-lag × AsyncWebCrawler + LLMExtractionStrategy ===")
    try:
        print(json.dumps(await s1_loop_lag(mock_url), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"S1 ERROR: {type(e).__name__}: {str(e)[:300]}")

    srv.shutdown()

    print("\n=== S2: sensenova response_format 探针 (真实出站) ===")
    print(json.dumps(await s2_sensenova(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
