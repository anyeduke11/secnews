"""项目根目录启动脚本 — 一行启动后端服务。

等价于
------
    $ python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

环境变量
--------
- ``HOTSPOT_HOST``   默认 ``0.0.0.0``（pydantic settings 前缀）
- ``HOTSPOT_PORT``   默认 ``8000``
- ``WORKERS``        默认 ``1``（SQLite WAL 模式下多 worker 会有锁竞争）

兼容旧变量:``HOST`` / ``PORT`` 仍然有效,优先级低于 HOTSPOT_*。

用法
----
    $ python run.py                       # 默认 0.0.0.0:8000
    $ HOTSPOT_PORT=8999 python run.py     # 自定义端口
"""
from __future__ import annotations

import os

import uvicorn

from backend.config import config


def main() -> None:
    # 优先 HOTSPOT_* (pydantic settings),兼容旧的 HOST/PORT
    host = os.getenv("HOTSPOT_HOST") or os.getenv("HOST", config.host)
    port = int(os.getenv("HOTSPOT_PORT") or os.getenv("PORT", str(config.port)))
    workers = int(os.getenv("WORKERS", "1"))
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
