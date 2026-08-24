"""Core 层 — 核心管道聚合（软分层 re-export，物理不搬代码）。

core 路由永远注册，不受 feature_gates 扩展开关影响。

``__all__`` 显式为空 — 调用方应直接 ``from backend.core.X import Y``。
"""
__all__: list[str] = []