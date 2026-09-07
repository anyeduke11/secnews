"""T18 旧 knowledge_items 迁移服务单元测试 (8 个).

端到端走独立 tmp_path + WARM_DB 准备, 同步 config.warm_db_path 与 os.environ['HOTSPOT_WARM_DB_PATH']
(后者在 conftest 顶部固定为 hotspot-test-iso/hotspot-warm.db — 与 fixture 的 tmp_path 隔离 path 不同,
  必须显式 setenv 才能让 sqlite3.connect 写到 ATTACH 的同一个 warm 文件).
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from backend.services.legacy_items_migrate_service import (
    DOMAIN_TO_KIND,
    LIFECYCLE_TO_STATUS,
    LegacyItemsMigrateService,
)


# ---------------------------------------------------------------------------
# 映射字典 (纯函数测试, 不依赖 WARM_DB)
# ---------------------------------------------------------------------------
def test_lifecycle_to_status_mapping() -> None:
    """lifecycle → status 6 态映射 (kl:deduped 排除)."""
    assert LIFECYCLE_TO_STATUS["kl:publish"] == "published"
    assert LIFECYCLE_TO_STATUS["kl:structure"] == "draft"
    assert LIFECYCLE_TO_STATUS["kl:raw"] == "draft"
    assert LIFECYCLE_TO_STATUS["kl:refine"] == "draft"
    assert LIFECYCLE_TO_STATUS["kl:link"] == "draft"
    assert "kl:deduped" not in LIFECYCLE_TO_STATUS  # 排除


def test_domain_to_kind_mapping() -> None:
    """domain → kind 6 域映射 (空 → reference fallback)."""
    assert DOMAIN_TO_KIND["ai"] == "reference"
    assert DOMAIN_TO_KIND["security"] == "playbook"
    assert DOMAIN_TO_KIND["dev"] == "pattern"
    assert DOMAIN_TO_KIND["startup"] == "reference"
    assert DOMAIN_TO_KIND["finance"] == "reference"
    assert DOMAIN_TO_KIND[""] == "reference"  # fallback


# ---------------------------------------------------------------------------
# 端到端 (独立 tmp_path + WARM_DB 准备)
# ---------------------------------------------------------------------------
@pytest.fixture()
def warm_attached(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """独立设置 config.db_path + config.warm_db_path + os.environ (三者必须一致).

    conftest session fixture 把 db_path 固定在 hotspot-test-iso/hotspot.db (所有测试共享),
    若不隔离, 多个测试 apply 的 INSERT 会累积到同一 v1_knowledge 表 — 幂等测试失效。

    本 fixture 用 tmp_path 同时重置 hot + warm, 让每个 warm_attached 测试拿到干净的 db。
    """
    from backend.config import config
    from backend.repository import db as dbm
    db_path = tmp_path / "test.db"
    warm_path = tmp_path / "test-warm.db"
    # 三者同步 (config ATTACH 用 / os.environ 独立 sqlite3.connect 用 / 后续 conftest 不再覆盖)
    monkeypatch.setattr(config, "db_path", db_path)
    monkeypatch.setattr(config, "warm_db_path", warm_path)
    monkeypatch.setenv("HOTSPOT_DB_PATH", str(db_path))
    monkeypatch.setenv("HOTSPOT_WARM_DB_PATH", str(warm_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    warm_path.parent.mkdir(parents=True, exist_ok=True)
    if not warm_path.exists():
        warm_path.touch()
    dbm.close_db()
    dbm.init_db()
    _seed_warm(str(warm_path), [
        {"id": "ki1", "title": "AI Security Note", "domain": "ai", "lifecycle": "kl:publish", "compiled": 1, "type": "analysis", "difficulty": "intro"},
        {"id": "ki2", "title": "Dev Pattern", "domain": "dev", "lifecycle": "kl:structure", "compiled": 0, "type": "tutorial"},
        {"id": "ki3", "title": "Deduped Item", "domain": "ai", "lifecycle": "kl:deduped", "compiled": 1},
        {"id": "ki4", "title": "Security Advisory", "domain": "security", "lifecycle": "kl:publish", "compiled": 1, "type": "advisory"},
    ])
    yield


def _seed_warm(warm_path: str, items: list[dict]) -> None:
    """seed warm.knowledge_items (T18 模拟旧 3800 行).

    真实生产 warm db 是历史 M2-T6 之前就在 warm 文件上跑过 018-035 migration 留下的表。
    测试 fresh warm db 没有这个表 — 在 warm sqlite3 conn 上 apply 018-035 migration 建表后 seed。
    """
    from backend.repository.db import apply_migrations as _apply
    warm = sqlite3.connect(warm_path)
    try:
        _apply(warm)  # 在 warm 上跑 018-035 migration 建 knowledge_items + ALTER 列
        cols = [r[1] for r in warm.execute("PRAGMA table_info(knowledge_items)").fetchall()]
        defaults = {
            "source": "bookmark", "source_url": "", "domain": "", "topic": "",
            "type": "", "difficulty": "", "tags": "[]", "concepts": "[]",
            "mastery": 0, "compiled": 0,
            "ingested_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "folder": "", "cve_ids": "[]", "attack_techniques": "[]",
            "compliance_refs": "[]", "threat_actors": "[]", "products": "[]",
            "lifecycle": "kl:raw", "news_type": "", "tech_stack": "[]",
            "attention_score": 0, "body": "",
        }
        for it in items:
            row = {**defaults, **it}
            placeholders = ",".join("?" * len(cols))
            values = tuple(row.get(c) for c in cols)
            cols_quoted = ",".join(f'"{c}"' for c in cols)
            warm.execute(
                f'INSERT OR REPLACE INTO knowledge_items ({cols_quoted}) VALUES ({placeholders})',
                values,
            )
        warm.commit()
    finally:
        warm.close()


def test_dry_run_counts_only(warm_attached) -> None:
    """dry-run 排除 kl:deduped → candidates = 3 (ki1/ki2/ki4)."""
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=False)
    assert r.items_candidates == 3
    assert r.items_applied == 0
    assert r.items_skipped == 0
    assert "ki1" in r.sample_ids
    assert "ki3" not in r.sample_ids  # kl:deduped 排除


def test_apply_inserts_legacy_status(warm_attached) -> None:
    """C13 5 态机: ki1/ki2/ki4 全部落 status='legacy' (T18 旧版 kl:publish→published 已废弃).

    wiki_root 默认位置没命中 fixture 的 ki* md 文件 → body 全空 → 走 quarantined
    (不入 v1_knowledge), 所以 v1_knowledge 表空, items_quarantined=3.
    """
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=True)
    # 3 candidates - 0 deduped = 3; warm body 全空 + wiki_root 默认无 fixture → 全 quarantined
    assert r.items_candidates == 3
    assert r.items_quarantined == 3
    assert r.items_applied == 0
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    rows = conn.execute(
        "SELECT id, status, kind FROM v1_knowledge ORDER BY id"
    ).fetchall()
    # C13 v1 守卫: 全部 quarantined, 0 条入 v1_knowledge
    assert len(rows) == 0
    # 但 mapping 表应有 3 条 quarantined
    map_count = conn.execute(
        "SELECT COUNT(*) FROM v1_legacy_mapping WHERE legacy_id IN ('ki1','ki2','ki4') "
        "AND legacy_source = 'warm.knowledge_items'"
    ).fetchone()[0]
    assert map_count == 3


def test_idempotent_apply_skips_existing(warm_attached) -> None:
    """重复 apply (同 batch_id) → v1 走 mapping existing → 第二次全 skipped (非 quarantined).

    C13 v1 幂等性: 第二次同 batch_id 跑, warm path 走 _insert_mapping_row 前先
    SELECT v1_legacy_mapping.legacy_id → 已存在 → 计数 result.skipped, 不再
    走 quarantined 路径. 验证: 第一次 3 quarantined, 第二次 3 skipped, mapping 表 3 行.
    """
    svc = LegacyItemsMigrateService()
    r1 = svc.migrate_legacy_items(apply=True, batch_id="dup-test")
    r2 = svc.migrate_legacy_items(apply=True, batch_id="dup-test")
    # 第一次: 走 quarantined (wiki_body 没命中 + header_only < 200)
    assert r1.items_quarantined == 3
    # 第二次: 走 skipped (mapping UNIQUE 命中, v1 内部 SELECT 拦截)
    assert r2.items_quarantined == 0
    assert r2.items_skipped == 3
    # mapping 表: 3 行 quarantined (来自第一次)
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    n = conn.execute(
        "SELECT COUNT(*) FROM v1_legacy_mapping "
        "WHERE legacy_id IN ('ki1','ki2','ki4') AND legacy_source = 'warm.knowledge_items'"
    ).fetchone()[0]
    assert n == 3
    # v1_knowledge 表: quarantined 不入, 0 行
    n2 = conn.execute("SELECT COUNT(*) FROM v1_knowledge").fetchone()[0]
    assert n2 == 0


# ---------------------------------------------------------------------------
# API 端到端 (FastAPI TestClient + 独立 tmp_path)
# ---------------------------------------------------------------------------
def test_legacy_items_migrate_api_dry_run_endpoint(warm_attached) -> None:
    """POST /api/dsh/legacy/items/migrate/run?apply=false → dry-run counts (3 排除 deduped)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.legacy_items_migrate_api import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post("/api/dsh/legacy/items/migrate/run?apply=false")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "dry-run"
    assert body["result"]["items_candidates"] == 3
    assert "ki1" in body["result"]["sample_ids"]


def test_legacy_items_migrate_api_status_endpoint(warm_attached) -> None:
    """GET /api/dsh/legacy/items/migrate/status → warm_db_candidates."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.legacy_items_migrate_api import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/dsh/legacy/items/migrate/status")
    assert r.status_code == 200
    assert r.json()["warm_db_candidates"] == 3


def test_legacy_items_migrate_no_warm_db_graceful(tmp_path, monkeypatch) -> None:
    """无 WARM_DB 文件 → service 返 0 candidates + 优雅不抛."""
    from backend.config import config
    from backend.repository import db as dbm
    # 改指向不存在的 warm 路径 (确保 init_db 跳过 ATTACH)
    empty_warm = tmp_path / "no-warm.db"
    monkeypatch.setattr(config, "warm_db_path", empty_warm)
    monkeypatch.setenv("HOTSPOT_WARM_DB_PATH", str(empty_warm))
    if empty_warm.exists():
        empty_warm.unlink()
    dbm.close_db()
    dbm.init_db()
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=True)
    assert r.items_candidates == 0
    assert r.items_applied == 0
    assert isinstance(r.errors, list)
