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

if is_enabled("agent"):
    # 启动 Agent 双向环
    ...
```

注意: feature flag 控制是「全有/全无」开关, 复杂的灰度发布请使用 ``feature_*.ratio``
(本版本不实现, 留待 Phase 2c AI 协作功能).
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.config import config
from backend.logging_config import logger


def is_enabled(name: str) -> bool:
    """读取 feature flag.

    Args:
        name: 不含 ``feature_`` 前缀, 例如 ``"agent"`` 映射到 ``config.feature_agent``.

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


def enabled_names(names: Optional[Iterable[str]] = None) -> list[str]:
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
    """运行时关闭某 flag (返回是否成功, 仅影响本进程的 config 单例).

    注意: 这是单进程行为, 不会持久化到 .env.
    """
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, False)
    return True


def enable(name: str) -> bool:
    """运行时启用某 flag (返回是否成功, 仅影响本进程的 config 单例)."""
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        return False
    setattr(config, attr, True)
    return True


__all__ = ["is_enabled", "enabled_names", "enable", "disable"]
