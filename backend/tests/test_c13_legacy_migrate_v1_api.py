"""C13 LegacyMigrateServiceV1 API 测试 (5 端点, FastAPI TestClient).

端到端: temp_db 隔离 + warm fixture (同 c13_iso_env 模式) + 5 端点覆盖.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.legacy_migrate_v1_api import router
from backend.repository.db import apply_migrations as _apply
from backend.repository.db import get_connection


@pytest.fixture
def c13_iso_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """C13 隔离环境: db_path + warm_db_path + wiki_root + seed_path 全独立.

    必须 monkeypatch.setattr config.* (autouse _isolate_temp_dbs 会覆盖 env-set).
    """
    from backend.config import config
    from backend.repository import db as dbm

    db_path = tmp_path / "hot.db"
    warm_path = tmp_path / "warm.db"
    wiki_root = tmp_path / "wiki"
    seed_dir = tmp_path / "dev_seed"
    log_dir = tmp_path / "log"
    backup_dir = tmp_path / "backup"
    data_dir = tmp_path / "data"
    for p in (db_path, warm_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.touch()
    for d in (wiki_root, seed_dir, log_dir, backup_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "db_path", db_path)
    monkeypatch.setattr(config, "warm_db_path", warm_path)
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "cold.db")
    monkeypatch.setattr(config, "cold_db_key", "")
    monkeypatch.setenv("HOTSPOT_DB_PATH", str(db_path))
    monkeypatch.setenv("HOTSPOT_WARM_DB_PATH", str(warm_path))
    monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(wiki_root))
    monkeypatch.setenv("HOTSPOT_DEV_SEED_DIR", str(seed_dir))
    monkeypatch.setenv("HOTSPOT_LOG_DIR", str(log_dir))
    monkeypatch.setenv("HOTSPOT_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("HOTSPOT_DATA_DIR", str(data_dir))
    (wiki_root / "items").mkdir(parents=True, exist_ok=True)
    dbm.close_db()
    dbm.init_db()
    return {
        "db_path": db_path, "warm_path": warm_path, "wiki_root": wiki_root,
        "seed_dir": seed_dir,
    }


def _init_warm_db(warm_path: Path, rows: list[dict]) -> None:
    """建 warm.knowledge_items 表 + seed 数据."""
    warm = sqlite3.connect(str(warm_path))
    try:
        _apply(warm)
        cols = [r[1] for r in warm.execute("PRAGMA table_info(knowledge_items)").fetchall()]
        defaults = {
            "source": "bookmark", "source_url": "", "domain": "security", "topic": "",
            "type": "advisory", "difficulty": "intro", "tags": "[]", "concepts": "[]",
            "mastery": 0, "compiled": 1,
            "ingested_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "folder": "", "cve_ids": "[]", "attack_techniques": "[]",
            "compliance_refs": "[]", "threat_actors": "[]", "products": "[]",
            "lifecycle": "kl:publish", "news_type": "", "tech_stack": "[]",
            "attention_score": 0, "body": "",
        }
        for r in rows:
            row = {**defaults, **r}
            placeholders = ",".join("?" * len(cols))
            cols_quoted = ",".join(f'"{c}"' for c in cols)
            warm.execute(
                f"INSERT OR REPLACE INTO knowledge_items ({cols_quoted}) VALUES ({placeholders})",
                tuple(row.get(c) for c in cols),
            )
        warm.commit()
    finally:
        warm.close()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_run_warm_dry_run_endpoint(c13_iso_env) -> None:
    """POST /run?source=warm&apply=false → 返 candidates + sample_ids (不落库)."""
    _init_warm_db(c13_iso_env["warm_path"], [
        {"id": "w1", "title": "W1"}, {"id": "w2", "title": "W2"},
        {"id": "w3", "title": "W3", "lifecycle": "kl:deduped"},  # 排除
    ])
    # ATTACH warm 重建 (因 get_connection 缓存)
    from backend.repository import db as dbm
    dbm.close_db()
    dbm.init_db()
    c = _client()
    r = c.post("/api/dsh/legacy/migrate/v1/run?source=warm&apply=false")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "dry-run"
    assert body["source"] == "warm"
    assert body["result"]["candidates"] == 2  # w1 + w2 (w3 deduped 排除)
    assert body["result"]["applied"] == 0
    assert "w1" in body["result"]["sample_ids"]
    assert "w3" not in body["result"]["sample_ids"]


def test_status_endpoint_returns_mapping_breakdown(c13_iso_env) -> None:
    """GET /status → 走 v1_legacy_mapping 真实查询返 breakdown."""
    # 直接写 mapping 测试 (绕 run)
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_legacy_mapping "
        "(legacy_source, legacy_id, legacy_revision, new_id, new_revision, "
        " content_hash, status, batch_id, migrated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("warm.knowledge_items", "w1", None, "NEW00000000000000000000000000", 1,
         "h" * 64, "quarantined", "b-test", "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO v1_legacy_mapping "
        "(legacy_source, legacy_id, legacy_revision, new_id, new_revision, "
        " content_hash, status, batch_id, migrated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("warm.knowledge_items", "w2", None, "NEW00000000000000000000000001", 1,
         "h" * 64, "applied", "b-test", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    c = _client()
    r = c.get("/api/dsh/legacy/migrate/v1/status?batch_id=b-test")
    assert r.status_code == 200
    body = r.json()
    assert body["mapping_total"] == 2
    assert body["breakdown"]["warm.knowledge_items"]["quarantined"] == 1
    assert body["breakdown"]["warm.knowledge_items"]["applied"] == 1


def test_mapping_query_endpoint(c13_iso_env) -> None:
    """GET /mapping?legacy_id=... → 返单行 mapping 详情."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_legacy_mapping "
        "(legacy_source, legacy_id, legacy_revision, new_id, new_revision, "
        " content_hash, status, batch_id, migrated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("warm.knowledge_items", "findme", None, "NEW00000000000000000000000099", 1,
         "h" * 64, "applied", "b-q", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    c = _client()
    r = c.get("/api/dsh/legacy/migrate/v1/mapping?legacy_id=findme")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["legacy_id"] == "findme"
    assert rows[0]["status"] == "applied"


def test_promote_endpoint_no_candidates(c13_iso_env) -> None:
    """POST /promote → 没候选返 0 promoted (无 awaiting_review + body≥200)."""
    c = _client()
    r = c.post("/api/dsh/legacy/migrate/v1/promote")
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["candidates"] == 0
    assert body["result"]["promoted"] == 0


def test_promote_log_endpoint(c13_iso_env) -> None:
    """GET /promote/log → 返 promote 日志 (空表返 [])."""
    c = _client()
    r = c.get("/api/dsh/legacy/migrate/v1/promote/log")
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []


def test_run_warm_apply_writes_mapping(c13_iso_env) -> None:
    """POST /run?source=warm&apply=true → 真落 v1_legacy_mapping (quarantined 路径)."""
    _init_warm_db(c13_iso_env["warm_path"], [
        {"id": "apply1", "title": "Apply1"},  # body 空 + wiki 没命中 → quarantined
    ])
    from backend.repository import db as dbm
    dbm.close_db()
    dbm.init_db()
    c = _client()
    r = c.post("/api/dsh/legacy/migrate/v1/run?source=warm&apply=true&batch_id=b-apply")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "apply"
    assert body["result"]["quarantined"] == 1
    # mapping 表应 1 行 quarantined
    conn = get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM v1_legacy_mapping WHERE legacy_id = 'apply1'",
    ).fetchone()[0]
    assert n == 1
