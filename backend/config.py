"""Backward-compat re-export of the ``backend.config`` package.

In v1.7 this was the Settings module; it has been merged into
``backend/config/__init__.py`` to resolve a package/module conflict
(Phase 16 Hybrid AI). All existing ``from backend.config import config``
imports continue to work.
"""
from backend.config import BASE_DIR, Settings, config  # noqa: F401