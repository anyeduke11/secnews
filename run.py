"""项目根目录启动脚本 — 一行启动后端服务。

等价于
------
    $ python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

环境变量
--------
- ``HOTSPOT_HOST``   默认 ``127.0.0.1``（无认证，个人工作站默认仅回环）
- ``HOTSPOT_ALLOW_LAN``  设为 ``1`` 才允许 ``HOTSPOT_HOST`` 绑定非回环地址
- ``HOTSPOT_PORT``   默认 ``8000``
- ``WORKERS``        默认 ``1``（SQLite WAL 模式下多 worker 会有锁竞争）

兼容旧变量:``HOST`` / ``PORT`` 仍然有效,优先级低于 HOTSPOT_*。

用法
----
    $ python run.py                       # 默认 127.0.0.1:8000
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

    # SecNews 定位是单人本地工作站, 而全 API 无认证 —— 绑非回环等于把写接口开放
    # 给整个局域网。历史实况是启动器导出了 HOTSPOT_HOST=0.0.0.0 (注意: 代码不加载
    # .env, 所以那是环境覆盖而非 .env 生效)。默认收紧到回环, 确需局域网访问时
    # 必须显式 HOTSPOT_ALLOW_LAN=1。
    if host not in ("127.0.0.1", "localhost", "::1") and os.getenv("HOTSPOT_ALLOW_LAN") != "1":
        print(
            f"[warn] 忽略 HOTSPOT_HOST={host!r}: 个人工作站默认仅监听回环; "
            "确需局域网访问请设 HOTSPOT_ALLOW_LAN=1 (并先给 API 加鉴权)。",
            flush=True,
        )
        host = "127.0.0.1"

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
