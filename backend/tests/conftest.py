"""
Shared fixtures for hotspot backend tests.

Every test uses ``tmp_path``-isolated SQLite so no test ever touches
the real ``backend/hotspot.db``.

Two fixture families
--------------------
1. **temp_db** — replaces ``config.db_path`` with a temporary path and
   calls ``db.init_db()`` to create the full schema.  Ideal for repository
   and service-layer tests that need ``backend.repository.db.get_connection()``
   to work normally.

2. **e2e_app(router, migrations, ...)** — creates a standalone ``FastAPI``
   instance + ``TestClient`` without launching the lifespan.  Used by e2e
   tests that need a specific subset of routers and migrations.

Usage
-----
.. code-block:: python

    # In any test file under backend/tests/:
    def test_something(temp_db):
        from backend.repository.hotspot_repo import HotspotRepository
        repo = HotspotRepository()
        # ... uses temp_db via config.db_path monkeypatch

    # Or for e2e:
    def test_api_flow(e2e_api_client):
        resp = e2e_api_client.get("/api/health")
        assert resp.status_code == 200

Markers
-------
- ``pytest.mark.unit`` — pure unit, no DB or network
- ``pytest.mark.integration`` — DB + multiple layers
- ``pytest.mark.e2e`` — full workflow across routers + DB
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect config.db_path to a temporary SQLite file with full schema.

    Replaces ``backend.config.config.db_path``, closes any previously
    cached thread-local connection, then runs ``init_db()``.
    """
    from backend.config import config
    from backend.repository import db

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", str(test_db))
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def e2e_api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Standalone FastAPI + TestClient with an isolated temp DB.

    Injects the full set of API routers but does **not** start the
    lifespan (no scheduler / collector).  The DB at ``tmp_path/test.db``
    has all migrations applied via ``init_db()``.
    """
    from backend.config import config
    from backend.repository import db
    from backend.api import register_routers
    from backend.api.middleware import TraceIDMiddleware
    from backend.exceptions import register_exception_handlers

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", str(test_db))

    db.close_db()
    db.init_db()

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)

    yield TestClient(app)

    db.close_db()
