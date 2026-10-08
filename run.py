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

from backend.config import config, resolve_bind_host
from backend.utils.instance_lock import refuse_if_locked


def main() -> None:
    # 优先 HOTSPOT_* (pydantic settings),兼容旧的 HOST/PORT
    host = os.getenv("HOTSPOT_HOST") or os.getenv("HOST", config.host)
    port = int(os.getenv("HOTSPOT_PORT") or os.getenv("PORT", str(config.port)))

    # P0-B: 回环守卫抽到 backend.config.resolve_bind_host, 与
    # backend.main.__main__ 共用同一实现 (勿在此复制逻辑)。
    host = resolve_bind_host(host)

    # dev即生产 单实例闸 (DEV-0293 教训): 同进程组残留 (含 uvicorn 子进程)
    # 即拒绝启动 — 端口检查测不出不持 socket 的僵尸调度器。
    refuse_if_locked(port=port)

    workers = int(os.getenv("WORKERS", "1"))
    # DEV-0301 根因修复: SIGTERM「盲区」真因 = timeout_graceful_shutdown
    # 默认 None → 连接排空无限等待 (SSE /mcp/sse、/api/events 长连接永不
    # 完成)。加有界超时: 到期 uvicorn cancel 残余任务后继续 lifespan 关闭。
    # 与 lifespan 内 drain (HOTSPOT_GRACEFUL_TIMEOUT, 默认 30s) 分段有界。
    shutdown_timeout = float(os.getenv("HOTSPOT_SHUTDOWN_TIMEOUT", "15"))
    # DEV-0302 R1: 信号前置哨兵 — uvicorn 的排空阶段发生在 lifespan shutdown
    # 之前, 应用层想「排空前终结 SSE」必须在 uvicorn handler 之外并行置位。
    # daemon 线程用 signal.signal 注册 (主线程 signal 通道已被 uvicorn 的
    # loop.add_signal_handler 使用, 两者互不干扰: 线程内注册只影响本线程
    # 视角的 handler 表, 而 Python 只允许主线程 signal.signal — 这里在
    # 主线程 uvicorn.run 之前抢先注册, uvicorn 的 loop handler 仍会执行)。
    from backend.utils.sigterm_sentinel import arm_sigterm_sentinel

    arm_sigterm_sentinel()
    # DEV-0303 R2: 退出尾闸 — uvicorn.run 返回 (或异常) 后立即硬退出,
    # 跳过解释器 join 非守护线程阶段 (STIX 图谱点火等后台线程可挂死退出)。
    exit_code = 0
    try:
        uvicorn.run(
            "backend.main:app",
            host=host,
            port=port,
            workers=workers,
            reload=False,
            log_level="info",
            timeout_graceful_shutdown=shutdown_timeout,
        )
    except BaseException:
        import traceback

        traceback.print_exc()
        exit_code = 1
        raise
    finally:
        from backend.utils.shutdown import guaranteed_exit

        guaranteed_exit(exit_code)


if __name__ == "__main__":
    main()
