"""SIGTERM 前置哨兵 (DEV-0302 R1) — 排空阶段之前置位 SSE 停机标志。

时序问题: uvicorn 收 SIGTERM → Server.handle_exit (记录停机意图) → 停收
新连接 → **排空** (timeout_graceful_shutdown) → lifespan shutdown。应用层
(lifespan 里的 request_shutdown) 只能在排空**之后**执行; SSE 流的 30s→5s
keepalive 轮询若等不到哨兵, 排空阶段仍会被流吃满 (实弹 17s)。

实现 (取证 uvicorn 0.50 capture_signals): uvicorn 用主线程
``signal.signal(sig, self.handle_exit)`` 并保存 original_handlers —
后注册者覆盖先注册者, 纯 signal.signal 前置方案死路。故改为**包装
Server.handle_exit**: 原 handler 执行前先置位哨兵 (微秒级, 先于排空),
原停机流程逐字保持。

进程退出时 original_handlers 恢复的是「capture 时」的 handler — 我们在
capture 之前 patch, 恢复语义不受影响 (恢复到的正是「无哨兵」状态, 进程
即将退出无碍)。

DEV-0303 R2 补丁: capture_signals 退出时会把捕获的信号 **re-raise**
(恢复默认 handler 后 ``signal.raise_signal(sig)``, uvicorn/server.py
L335-336) — 进程直接死于信号, ``uvicorn.run`` 不返回, 入口脚本的
``finally: guaranteed_exit`` 尾闸永不执行 (实弹取证: 尾闸日志缺失 +
exit -15)。故包装 handler 在原流程后清空 ``_captured_signals``, 吞掉
重放: uvicorn.run 正常返回 → 统一走 run.py 尾闸 (loguru 刷洗 + 跳过
解释器 join 阶段的 ``os._exit(0)``), 退出码语义也归于 0 而非信号死。
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger


def arm_sigterm_sentinel() -> None:
    """包装 uvicorn Server.handle_exit: 原流程前先置位 SSE 停机哨兵。

    幂等 (重复调用只 patch 一次); uvicorn 未导入/类不存在时静默跳过
    (兜底路径仍有效: 排空超时 15s 有界)。
    """
    try:
        from uvicorn.server import Server
    except Exception as e:  # pragma: no cover
        logger.warning(f"sigterm sentinel: uvicorn unavailable (skipped): {e}")
        return

    if getattr(Server, "_sigterm_sentinel_armed", False):
        return

    original = Server.handle_exit

    def handle_exit_with_sentinel(self: Server, sig: int, frame: Any) -> None:
        try:
            from backend.core.events import request_shutdown
            request_shutdown()
            logger.info(f"sigterm sentinel: signal {sig} → SSE shutdown flag set (pre-drain)")
        except Exception as e:  # 哨兵失败不影响停机链
            logger.warning(f"sigterm sentinel error (ignored): {e}")
        original(self, sig, frame)
        # DEV-0303 R2: 吞掉 capture_signals 退出时的信号重放 (见模块 docstring)。
        # 重复 TERM → handle_exit 再次进入 → 每次都清, force_exit 语义不受影响。
        try:
            self._captured_signals.clear()
        except AttributeError:
            pass  # 旧版 uvicorn 无此属性 → 保持原生重放行为

    Server.handle_exit = handle_exit_with_sentinel  # type: ignore[method-assign]
    Server._sigterm_sentinel_armed = True  # type: ignore[attr-defined]
    logger.info("sigterm sentinel armed (Server.handle_exit wrapped)")


__all__ = ["arm_sigterm_sentinel"]
