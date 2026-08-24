"""Domain layer: enums, models, business rules.

Phase 2 data layer reorg: this package holds pure data classes / enums
that the repository and service layers depend on. No I/O, no logging.

``__all__`` 显式为空 — 调用方应直接 ``from backend.domain.X import Y``
(枚举/模型散布在子模块下, 不在根级 re-export)。
"""
__all__: list[str] = []