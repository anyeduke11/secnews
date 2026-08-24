"""Service layer: orchestrates collectors / repositories / scheduler.

Phase 3 introduces ``backend.services.collection_service.CollectionService``
which is the canonical entry point for running a full collection cycle.
This package is intentionally empty in Phase 3 Task 1; subsequent
sub-tasks (Task 4) populate it.

``__all__`` 显式为空 — 调用方应直接 ``from backend.services.X import Y``
(86 个 service 子模块按职责分布在 :mod:`backend.services.*` 下, 不在根级
re-export; 测试与生产代码已统一此约定, 见 ruff 配置 F401 对 ``__init__.py`` 豁免)。
"""
__all__: list[str] = []