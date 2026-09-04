"""DSH 运行时模式切换 — mock / 真子进程调度层 (v0.8 Phase B B4).

职责定位
--------
本模块是 bridge.py (HTTP 客户端) 与 supervisor.py (进程生命周期) 之上的
**调度层**: 决定一次任务派发走 mock 还是真子进程, 并在真子进程失败时
自动回退 mock。它**不**改变 supervisor 的生命周期语义, 也不直接持有
DSHClient — invoke_subprocess / invoke_mock 由调用方注入。

配置契约 (settings KV, 与 supervisor 同源):
- ``dsh.runtime_mode``: ``"mock"`` | ``"subprocess"`` | ``"auto"`` (默认
  ``auto``, 非法值回退 auto 并 warning)。经 ``set_mode()`` 写入后跨重启
  保留 (settings 表持久化)。
- ``dsh.command``: 启动命令 (supervisor.get_dsh_config 读取), auto 模式
  下据此判定 subprocess 可用性 — 未配置 = ``not_configured`` 语义沿用。

回退语义 (B4 红线, 见 V0.8_REFACTOR_PLAN.md §11 风险表):
- subprocess 路径任何异常 (启动失败/超时/非零退出) → 立即回退
  invoke_mock, ``fallback_happened=True``, 写 ``audit_log``
  (action=``dsh.runtime_fallback``, 沿用 observability_records.record_audit)。
- 连续回退 >= ``_MAX_CONSECUTIVE_FALLBACKS`` (3, 对齐 ProcessSupervisor
  max_restarts=3 语义) 后, 本实例内缓存 "subprocess 不健康", 后续直接走
  mock 不再撞墙; ``reset_health()`` 供控制面板手动重试。
- invoke_mock 自身异常**上抛不吞** (mock 是最后兜底, 兜底也坏必须暴露)。

用法示例::

    runtime = DshRuntime()          # 或用模块级单例 dsh_runtime
    runtime.set_mode("auto")         # settings.kv 持久化, 默认即 auto
    effective, reason = runtime.resolve_effective()
    # → ("subprocess" | "mock" | "not_configured", reason)
    result, mode_used, fallback = runtime.execute_with_fallback(
        task,
        invoke_subprocess=dsh_client.send_task,   # 失败自动回退 mock
        invoke_mock=mock_dispatch,
    )
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from enum import Enum
from typing import Any

from backend.logging_config import logger
from backend.observability_records import record_audit
from backend.repository.settings_repo import SettingsRepository
from backend.services.dsh import supervisor as _dsh_supervisor

_MODE_KEY = "dsh.runtime_mode"
#: 连续回退熔断阈值 — 与 ProcessSupervisor(max_restarts=3) 语义对齐
_MAX_CONSECUTIVE_FALLBACKS = 3


class DshRuntimeMode(str, Enum):
    """dsh 运行时模式 (settings.kv ``dsh.runtime_mode`` 的合法值域).

    继承 ``str`` 使枚举成员可直接与字符串比较/JSON 序列化
    (``DshRuntimeMode.AUTO == "auto"`` 为 True), 方便 API 层透传。
    """

    MOCK = "mock"
    SUBPROCESS = "subprocess"
    #: auto (默认): 有可用启动命令走 subprocess, 失败回退 mock;
    #: 无命令 = not_configured 降级语义沿用 (直接 mock, 不算回退)
    AUTO = "auto"


def _default_command_source() -> dict[str, Any]:
    """默认命令配置源 — 间接经 supervisor 模块取 get_dsh_config()。

    经模块属性引用 (而非 ``from ... import get_dsh_config``) 是刻意的:
    调用时才解析属性, 测试可 monkeypatch supervisor.get_dsh_config 生效。
    """
    return _dsh_supervisor.get_dsh_config()


class DshRuntime:
    """mock / 真子进程运行时切换器。

    状态分两层:
    - **持久层** (settings KV ``dsh.runtime_mode``): 模式选择, 跨重启
      保留, 由 get_mode/set_mode 读写。
    - **易失层** (实例字段): 连续回退计数与 "subprocess 不健康" 熔断
      缓存 — 只在本进程生命周期内有效, 重启即自然复位; 控制面板可用
      ``reset_health()`` 手动清除以重试真子进程。
    """

    def __init__(
        self, *, command_source: Callable[[], dict[str, Any]] | None = None
    ) -> None:
        self._command_source = command_source or _default_command_source
        self._lock = threading.Lock()
        self._consecutive_fallbacks = 0
        self._subprocess_unhealthy = False

    # ------------------------------------------------------------------
    # 模式读写 (settings KV 持久化)
    # ------------------------------------------------------------------
    def get_mode(self) -> DshRuntimeMode:
        """读 ``dsh.runtime_mode`` (默认 auto; 非法值回退 auto + warning)。"""
        raw = SettingsRepository().get(_MODE_KEY)
        if raw is None:
            return DshRuntimeMode.AUTO
        try:
            return DshRuntimeMode(raw)
        except ValueError:
            logger.warning(
                "dsh.runtime_mode 非法值 %r, 回退 auto (合法值: mock/subprocess/auto)", raw
            )
            return DshRuntimeMode.AUTO

    def set_mode(self, mode: DshRuntimeMode | str) -> DshRuntimeMode:
        """持久化运行时模式 (settings KV, 重启保留)。

        接受 DshRuntimeMode 或其字符串值; 非法值抛 ValueError (fail loud,
        与 get_mode 的"存量脏数据宽容"形成对照 — 写入口必须拦住脏值)。
        """
        try:
            resolved = DshRuntimeMode(mode)
        except ValueError as e:
            raise ValueError(
                f"非法 dsh runtime mode: {mode!r} "
                f"(合法值: mock/subprocess/auto)"
            ) from e
        SettingsRepository().set(_MODE_KEY, resolved.value)
        logger.info("dsh runtime mode set to %s (persisted)", resolved.value)
        return resolved

    # ------------------------------------------------------------------
    # auto 解析
    # ------------------------------------------------------------------
    def resolve_effective(self) -> tuple[str, str]:
        """解析当前生效路径 → ``("mock"|"subprocess"|"not_configured", reason)``。

        - 显式 mock → mock (即使配置了启动命令)
        - 显式 subprocess → subprocess
        - auto + 已配置启动命令 → subprocess
        - auto + 未配置 → not_configured

        注意: 这里只反映**配置层**意图; 实例级 "subprocess 不健康" 熔断
        是派发期决策, 只在 execute_with_fallback 内生效, 不影响本方法。
        """
        mode = self.get_mode()
        if mode is DshRuntimeMode.MOCK:
            return "mock", "explicit mock mode (dsh.runtime_mode=mock)"
        if mode is DshRuntimeMode.SUBPROCESS:
            return "subprocess", "explicit subprocess mode (dsh.runtime_mode=subprocess)"
        cfg = self._command_source()
        if cfg.get("command"):
            return "subprocess", "auto: startup command configured (dsh.command)"
        return "not_configured", "auto: no startup command (dsh.command empty)"

    # ------------------------------------------------------------------
    # 派发 + 回退
    # ------------------------------------------------------------------
    def execute_with_fallback(
        self,
        task: dict[str, Any],
        *,
        invoke_subprocess: Callable[[dict[str, Any]], Any],
        invoke_mock: Callable[[dict[str, Any]], Any],
    ) -> tuple[Any, str, bool]:
        """按解析结果派发任务, subprocess 失败自动回退 mock。

        Parameters
        ----------
        task:
            任务描述 (约定含 ``task_type`` 等字段, 仅透传给两个 invoke)。
        invoke_subprocess:
            真子进程执行器; 启动失败/超时/非零退出应以异常形式抛出
            (本方法据此触发回退)。
        invoke_mock:
            mock 执行器 (最后兜底); 其异常**上抛不吞**。

        Returns
        -------
        (result, mode_used, fallback_happened):
            mode_used ∈ {"mock", "subprocess"} — 实际产出结果的路径;
            fallback_happened — 解析为 subprocess 却由 mock 兜底时为 True
            (含熔断短路, 均记一条 dsh.runtime_fallback 审计)。
        """
        effective, reason = self.resolve_effective()

        if effective in ("mock", "not_configured"):
            # 显式 mock / auto 无命令: mock 是第一选择而非兜底, 不算回退。
            if effective == "not_configured":
                logger.info("dsh runtime not_configured, serving via mock: %s", reason)
            return invoke_mock(task), "mock", False

        # effective == "subprocess": 先查实例级健康熔断缓存
        with self._lock:
            unhealthy = self._subprocess_unhealthy
        if unhealthy:
            logger.warning("dsh subprocess unhealthy (cached), skip to mock")
            self._record_fallback_audit(task, trigger="unhealthy_cache", error=None)
            return invoke_mock(task), "mock", True

        try:
            result = invoke_subprocess(task)
        except Exception as exc:
            with self._lock:
                self._consecutive_fallbacks += 1
                newly_unhealthy = (
                    not self._subprocess_unhealthy
                    and self._consecutive_fallbacks >= _MAX_CONSECUTIVE_FALLBACKS
                )
                if newly_unhealthy:
                    self._subprocess_unhealthy = True
                streak = self._consecutive_fallbacks
            logger.warning(
                "dsh subprocess failed (%s: %s), fallback to mock (streak %d/%d)",
                type(exc).__name__, exc, streak, _MAX_CONSECUTIVE_FALLBACKS,
            )
            # 审计先于 mock 执行 — 即使 mock 随后异常, 失败事实也已落账。
            self._record_fallback_audit(task, trigger="subprocess_error", error=str(exc))
            return invoke_mock(task), "mock", True

        with self._lock:
            self._consecutive_fallbacks = 0
        return result, "subprocess", False

    # ------------------------------------------------------------------
    # 健康熔断复位 (控制面板手动重试入口)
    # ------------------------------------------------------------------
    def reset_health(self) -> None:
        """清除 "subprocess 不健康" 熔断状态, 恢复对真子进程的尝试。"""
        with self._lock:
            self._consecutive_fallbacks = 0
            self._subprocess_unhealthy = False
        logger.info("dsh runtime health reset — subprocess attempts restored")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _record_fallback_audit(
        self, task: dict[str, Any], *, trigger: str, error: str | None
    ) -> None:
        """落一条 ``dsh.runtime_fallback`` 审计 (record_audit 自吞异常, 不阻塞派发)。"""
        task_type = str(task.get("task_type", "") or "")[:100] or None
        with self._lock:
            streak = self._consecutive_fallbacks
        detail: dict[str, Any] = {
            "resolved": "subprocess",
            "mode_used": "mock",
            "trigger": trigger,
            "consecutive_fallbacks": streak,
        }
        if error:
            detail["error"] = str(error)[:300]
        record_audit(
            actor="system",
            action="dsh.runtime_fallback",
            target=task_type,
            detail=detail,
        )


# 模块级单例 — 与 supervisor.py 的模块级 supervisor 生命周期约定一致
dsh_runtime = DshRuntime()

__all__ = [
    "DshRuntime",
    "DshRuntimeMode",
    "dsh_runtime",
]
