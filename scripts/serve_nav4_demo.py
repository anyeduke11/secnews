#!/usr/bin/env python3
"""serve_nav4_demo — NAV4 交互 demo 本地服务器 (演示类, 无状态).

作用: 静态伺服 docs/demos/NAV4_IA_DEMO.html 并把 /api/* 反向代理到本机
后端 (固定 http://127.0.0.1:8000), 使 demo 页面同源取真实数据 —
绕开后端 CORS 白名单 (仅允许 8898/8899/8000)。

用法:
  .venv/bin/python scripts/serve_nav4_demo.py                 # 默认 127.0.0.1:8792

零依赖 (仅 stdlib), 无写操作; 上游 host/port 为常量字面量 (http.client
固定连接, 无动态 URL 构造 — Mimosa triage 同源策略); 后端未启动时代理
返回 502 + 启动提示。
"""
from __future__ import annotations

import argparse
import http.client
import http.server
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_ROOT / "docs" / "demos" / "NAV4_IA_DEMO.html"
UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8000


class DemoHandler(http.server.BaseHTTPRequestHandler):
    # ── 路由 ──
    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy("GET")
        else:
            self._serve_html()

    def do_POST(self) -> None:
        self._proxy("POST")

    # ── 反向代理: http.client 固定上游字面量, 仅转发 /api/ 路径 ──
    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        headers = {}
        if self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers["Content-Type"]
        try:
            conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=30)
            conn.request(method, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            ctype = resp.getheader("Content-Type", "application/json")
            status = resp.status
            conn.close()
            self._respond(status, data, ctype)
        except OSError as e:  # 后端未启动 / 连接拒绝
            payload = json.dumps({
                "detail": (
                    f"后端不可达 ({UPSTREAM_HOST}:{UPSTREAM_PORT}): {e} — "
                    "请先启动 .venv/bin/python run.py"
                )
            }).encode()
            self._respond(502, payload, "application/json")

    def _respond(self, status: int, data: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── 静态 HTML ──
    def _serve_html(self) -> None:
        data = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # 静默
        pass


def main() -> int:
    import sys

    ap = argparse.ArgumentParser(description="NAV4 demo 本地服务器 (静态 + /api 反代)")
    ap.add_argument("--port", type=int, default=8792)
    args = ap.parse_args()
    if not HTML_PATH.exists():
        print(f"ERROR: demo html not found: {HTML_PATH}", file=sys.stderr)
        return 1
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"NAV4 demo: http://127.0.0.1:{args.port}  (api → {UPSTREAM_HOST}:{UPSTREAM_PORT})")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
