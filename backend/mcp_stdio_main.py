"""v1.7 Phase 7 — MCP Server stdio 入口.

启动方式 (供 Claude Desktop / Trae / Cursor / Workbuddy 配置):

```json
{
  "mcpServers": {
    "hotspot": {
      "command": "python",
      "args": ["-m", "backend.mcp_stdio_main"],
      "cwd": "/Users/duke/Documents/hotspot"
    }
  }
}
```

设计
----
- 不复用 FastAPI lifespan (stdio 模式下 HTTP 服务无需启动)
- 直接调 fastapi-mcp.run(transport="stdio")
- feature.mcp_server=False 时 print 警告并 exit 1
"""
from __future__ import annotations

import asyncio
import logging
import sys

from backend.logging_config import logger, setup


def main() -> None:
    setup()
    log = logger.bind(component="mcp_stdio")

    from backend.api.mcp_config import is_mcp_enabled, build_mcp_server
    from backend.repository.db import init_db
    from backend.api.mcp_config import mcp_tool_registry_seed

    # Banner
    print("=" * 60, file=sys.stderr)
    print("Hotspot MCP Server (stdio transport)", file=sys.stderr)
    print("Phase 7 / v1.7.6 Option A", file=sys.stderr)
    print("MCP spec version: 2025-06-18", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    if not is_mcp_enabled():
        print(
            "ERROR: feature.mcp_server=False; MCP server is disabled",
            file=sys.stderr,
        )
        log.error("mcp_stdio_main: feature.mcp_server disabled, exiting")
        sys.exit(1)

    # 初始化 DB + seeding 13 tool 元数据
    try:
        init_db()
        inserted = mcp_tool_registry_seed()
        log.info(f"mcp_stdio_main: db ready, {inserted} tools seeded")
        print(
            f"Database initialized, {inserted} tools registered to mcp_tool_registry",
            file=sys.stderr,
        )
    except Exception as e:
        log.error(f"mcp_stdio_main: db init failed: {e}")
        print(f"ERROR: db init failed: {e}", file=sys.stderr)
        sys.exit(2)

    # 构造 FastAPI app + FastApiMCP
    from backend.main import app  # 复用 main.py 完整 app
    mcp = build_mcp_server(app)
    if mcp is None:
        print("ERROR: failed to build MCP server", file=sys.stderr)
        sys.exit(3)

    print(
        "MCP server starting on stdio transport...\n"
        "Listening for JSON-RPC requests on stdin (write responses to stdout).",
        file=sys.stderr,
    )
    log.info("mcp_stdio_main: starting stdio transport")

    try:
        # fastapi-mcp 提供 run() 方法, transport="stdio" 用 stdin/stdout
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        log.info("mcp_stdio_main: interrupted, shutting down")
    except Exception as e:
        log.error(f"mcp_stdio_main crashed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
