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

import sys

from backend.logging_config import logger, setup


def main() -> None:
    setup()
    log = logger.bind(component="mcp_stdio")

    from backend.api.mcp_config import build_mcp_server, is_mcp_enabled, mcp_tool_registry_seed
    from backend.repository.db import init_db
    from backend.version import APP_VERSION

    # Banner
    print("=" * 60, file=sys.stderr)
    print("Hotspot MCP Server (stdio transport)", file=sys.stderr)
    print(f"v{APP_VERSION}", file=sys.stderr)
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

    # v1.8: 与 main.py lifespan 对齐 —— 尝试从 OS keychain 自动恢复 unlock
    # 状态, 否则 stdio 模式下依赖 secrets 的工具 (如 codegarden GitHub 同步)
    # 会因未解锁而不可用。失败仅告警, 不阻断启动。
    try:
        from backend.services.secrets_service import try_auto_unlock
        if try_auto_unlock():
            print("Secrets auto-unlock: OK (restored from keychain)", file=sys.stderr)
        else:
            print(
                "Secrets auto-unlock: skipped (no persisted master key)",
                file=sys.stderr,
            )
    except Exception as e:
        log.warning(f"mcp_stdio_main: auto-unlock failed (ignored): {e}")
        print(f"WARNING: secrets auto-unlock failed (ignored): {e}", file=sys.stderr)

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
        # fastapi-mcp 0.4.x 的 FastApiMCP 只提供 mount_sse/mount_http, 不提供
        # stdio 运行 (mcp.run(transport="stdio") 不存在)。stdio 的正确引导:
        # 1) setup_server() 把 OpenAPI 工具注册到内部 MCP SDK Server (self.server)
        # 2) 用 mcp.server 的 stdio_server() + run() 走 stdin/stdout JSON-RPC
        import anyio

        async def _run_stdio() -> None:
            from mcp.server.lowlevel.server import NotificationOptions
            from mcp.server.models import InitializationOptions
            from mcp.server.stdio import stdio_server

            mcp.setup_server()
            server = mcp.server  # mcp.server.Server (MCP SDK lowlevel)
            async with stdio_server() as (read_stream, write_stream):
                init_opts = InitializationOptions(
                    server_name="hotspot",
                    server_version=APP_VERSION,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                )
                await server.run(read_stream, write_stream, init_opts)

        anyio.run(_run_stdio)
    except KeyboardInterrupt:
        log.info("mcp_stdio_main: interrupted, shutting down")
    except Exception as e:
        log.error(f"mcp_stdio_main crashed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
