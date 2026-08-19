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

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def _disable_startup_catchup(monkeypatch: pytest.MonkeyPatch) -> None:
    """v1.8: 全局禁用 lifespan 的启动自动追抓 (真实全网抓取).

    main.py lifespan 在 TestClient(app) 启动时会 enqueue 一次「本周一 → 现在」
    的真实网络抓取, 导致测试挂起/极慢。所有测试一律关闭, 单测 catchup 逻辑请
    直接调用 catchup_service 的函数。
    """
    from backend.config import config
    monkeypatch.setattr(config, "catchup_on_startup", False)


@pytest.fixture(autouse=True)
def _feature_gates_all_on_for_tests() -> None:
    """v0.4.3: 测试环境默认全部扩展开启。

    分层重构后路由/job 注册受 feature_gates.toml 控制, 而生产默认
    codegarden/mcp/tech_stack/security_graph=false。既有功能测试假设这些
    功能在线, 因此测试环境通过 HOTSPOT_FEATURE_GATES env 全开。
    组合矩阵 (core-only / all-on / mixed) 由 test_feature_gates.py
    和 CI backend-core-only job 专门覆盖。
    """
    import os

    from backend.extensions import reset_gates

    prev = os.environ.get("HOTSPOT_FEATURE_GATES")
    os.environ["HOTSPOT_FEATURE_GATES"] = (
        '{"extensions": {"codegarden": true, "mcp": true, "sync": true, '
        '"tech_stack": true, "security_graph": true}}'
    )
    reset_gates()
    yield
    if prev is None:
        os.environ.pop("HOTSPOT_FEATURE_GATES", None)
    else:
        os.environ["HOTSPOT_FEATURE_GATES"] = prev
    reset_gates()


@pytest.fixture(autouse=True)
def _isolate_knowledge_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """P1: 所有测试强制隔离 knowledge/ 目录 — 根治测试污染真实知识库.

    此前全量测试会改写真实 ``knowledge/items/*.md`` 的 ingested_at
    (每次跑完 17+ 个文件被污染) 并重写 ``knowledge/_MAP.md``
    (4008 items → 3), 需要每次手动 git checkout 恢复。本 fixture 把
    11 个 service 模块里的知识库路径常量全部重定向到 tmp_path 下的隔离
    目录树, 测试副作用只落在临时目录。

    被测试自身 monkeypatch 覆盖也安全 (monkeypatch 按 LIFO 回滚)。
    """
    import importlib

    kdir = tmp_path / "knowledge"
    redirect = {
        "KNOWLEDGE_DIR": kdir,
        "ITEMS_DIR": kdir / "items",
        "CONCEPTS_DIR": kdir / "concepts",
        "DRAFTS_DIR": kdir / "content" / "drafts",
        "PENDING_DIR": kdir / "learning" / "tasks" / "pending",
        "DONE_DIR": kdir / "learning" / "tasks" / "done",
        "FAILED_DIR": kdir / "learning" / "tasks" / "failed",
        "MAP_PATH": kdir / "_MAP.md",
        "SOUL_PATH": kdir / "SOUL.md",
    }
    modules = (
        "backend.services.bookmark_sync",
        "backend.services.compiler",
        "backend.services.concept_linker",
        "backend.services.content_service",
        "backend.services.cubox_sync",
        "backend.services.federation_service",
        "backend.services.history_import",
        "backend.services.knowledge_sync",
        "backend.services.learning_service",
        "backend.services.map_updater",
        "backend.services.soul_service",
    )
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        for attr, val in redirect.items():
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, val)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect config.db_path to a temporary SQLite file with full schema.

    Replaces ``backend.config.config.db_path``, closes any previously
    cached thread-local connection, then runs ``init_db()``.
    """
    from backend.config import config
    from backend.repository import db

    test_db = tmp_path / "test.db"
    # P1: db_path 必须是 Path (repository/db.py get_connection 调用
    # db_path.parent.mkdir, str 会 AttributeError — 此前未被触发的隐性 bug)
    monkeypatch.setattr(config, "db_path", test_db)
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
    from backend.api import register_routers
    from backend.api.middleware import TraceIDMiddleware
    from backend.config import config
    from backend.exceptions import register_exception_handlers
    from backend.repository import db

    test_db = tmp_path / "test.db"
    # P1: db_path 必须是 Path (见 temp_db 注释)
    monkeypatch.setattr(config, "db_path", test_db)

    db.close_db()
    db.init_db()

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)

    yield TestClient(app)

    db.close_db()
