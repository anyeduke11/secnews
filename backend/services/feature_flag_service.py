"""v1.7 Phase 6 Task 6.2 — Feature Flag 读取服务.

设计
----
- 单一职责: 解析 ``config.feature_<name>`` 字段, 返回 bool
- 默认安全: 未知 flag 返回 ``False`` (防未授权启用)
- 可由环境变量覆盖: ``HOTSPOT_FEATURE_<NAME>`` (Pydantic 解析)

用法
----
```python
from backend.services.feature_flag_service import is_enabled

if is_enabled("mcp"):
    # 启动 MCP Server (Phase 7)
    ...
```

注意: feature flag 控制是「全有/全无」开关, 复杂的灰度发布请使用 ``feature_*.ratio``
(本版本不实现, 留待 Phase 2c AI 协作功能).

Phase 7 历史: 原 ``agent`` flag 已废弃, 由 ``mcp_server`` 取代 (Option A 简化).
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.config import config
from backend.logging_config import logger


def is_enabled(name: str) -> bool:
    """读取 feature flag.

    Args:
        name: 不含 ``feature_`` 前缀, 例如 ``"mcp"`` 映射到 ``config.feature_mcp``.

    Returns:
        bool: flag 状态, 未知 flag 返回 ``False``.
    """
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        logger.warning(
            "unknown feature flag '%s' (attr=%s); defaulting to False", name, attr
        )
        return False
    return bool(getattr(config, attr))


def enabled_names(names: Iterable[str] | None = None) -> list[str]:
    """返回所有 enabled flag 名称列表.

    Args:
        names: 待检查的 flag 列表; 默认检查全部 feature_* 字段.

    Returns:
        list[str]: enabled flag 名 (不含 ``feature_`` 前缀).
    """
    if names is None:
        names = [
            k[len("feature_"):]
            for k in dir(config)
            if k.startswith("feature_") and not k.startswith("feature__")
        ]
    return [n for n in names if is_enabled(n)]


def disable(name: str) -> bool:
    """运行时关闭某 flag: config 单例立即生效 + settings kv 持久化 (重启回读)。"""
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, False)
    _persist(name, False)
    return True


def enable(name: str) -> bool:
    """运行时启用某 flag: config 单例立即生效 + settings kv 持久化 (重启回读)。"""
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, True)
    _persist(name, True)
    return True


def _persist(name: str, value: bool) -> None:
    """写 settings kv ``feature.<name>`` (config.feature_<name> 的 kv 镜像, main.py 启动回读)。

    经 SettingsService().set — 写入即审计 (audit_log) + namespace 契约
    (``feature.`` 前缀已在 _ALLOWED_PREFIXES), 不直连 repo 绕过审计。
    失败仅告警 — 即时生效不因持久化失败回滚。
    """
    try:
        from backend.services.settings_service import SettingsService

        SettingsService().set(f"feature.{name}", value)
    except Exception as e:  # pragma: no cover
        logger.warning("feature flag persist failed for %s: %s", name, e)


__all__ = ["disable", "enable", "enabled_names", "is_enabled"]
