"""Repository layer: SQLite access + migrations.

Phase 2 data layer reorg. All DB I/O lives here.

``__all__`` 显式为空 — 调用方应直接 ``from backend.repository.X import Y``
而不是 ``from backend.repository import Y``; 此包不充当 re-export facade。
"""
__all__: list[str] = []