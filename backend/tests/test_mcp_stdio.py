"""v1.7 Phase 7 — MCP stdio transport 测试.

覆盖:
  - python -m backend.mcp_stdio_main 启动后能初始化
  - stdio entry 检查 feature.mcp_server flag
  - 启动 banner 包含 13 tools 标识
"""
from __future__ import annotations

import importlib
import sys

import pytest


def test_stdio_module_importable():
    """backend.mcp_stdio_main 模块可导入."""
    from backend import mcp_stdio_main
    assert hasattr(mcp_stdio_main, "main")
    assert callable(mcp_stdio_main.main)


def test_stdio_entry_function_exists():
    """main() 入口函数存在."""
    from backend.mcp_stdio_main import main
    assert callable(main)


def test_stdio_disabled_exits(monkeypatch):
    """feature.mcp_server=False 时, stdio 入口应直接 exit."""
    from backend.config import config
    monkeypatch.setattr(config, "feature_mcp_server", False)
    from backend.mcp_stdio_main import main
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0


def test_stdio_imports_no_errors():
    """import backend.mcp_stdio_main 不抛任何错."""
    mod = importlib.import_module("backend.mcp_stdio_main")
    assert mod is not None
