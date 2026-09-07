"""C13 legacy_promote_due + legacy_migrate_resume job 测试 (job 56 + 57).

端到端: temp_db 隔离 + warm fixture + 走 v1 service 落 awaiting_review 后
直接调 job 函数验证 promote 触发 + 中断 resume 行为.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.repository.db import apply_migrations as _apply
from backend.repository.db import get_connection


@pytest.fixture
def c13_iso_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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


def _write_wiki_md(items_dir: Path, old_id: str, body: str) -> None:
    """写 llm-wiki-2.0/items/knowledge_{id}.md frontmatter + body."""
    fm_id = old_id.upper()
    items_dir.mkdir(parents=True, exist_ok=True)
    p = items_dir / f"knowledge_{old_id}.md"
    p.write_text(
        f"---\nid: {fm_id}\ntitle: T\n---\n{body}\n",
        encoding="utf-8",
    )


def test_legacy_promote_due_job_no_candidates(c13_iso_env) -> None:
    """job 56 启动 → 0 candidates → 返 0 promoted."""
    from backend.scheduler.jobs.legacy_promote import legacy_promote_due_job
    r = legacy_promote_due_job()
    assert r["candidates"] == 0
    assert r["promoted"] == 0
    assert r["errors"] == []


def test_legacy_promote_due_job_promotes_one(c13_iso_env) -> None:
    """job 56 启动 → 1 awaiting_review + body≥200 + wiki 命中 → promote 1 条."""
    _init_warm_db(c13_iso_env["warm_path"], [
        {"id": "p1", "title": "Promote1", "lifecycle": "kl:publish", "body": ""},
    ])
    items_dir = c13_iso_env["wiki_root"] / "items"
    _write_wiki_md(items_dir, "p1", "x" * 500)  # 真 body ≥ 200B
    from backend.repository import db as dbm
    dbm.close_db()
    dbm.init_db()

    # 1) 先 run_warm apply → 1 awaiting_review
    from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
    svc = LegacyMigrateServiceV1(wiki_root=c13_iso_env["wiki_root"])
    run = svc.migrate_warm(apply=True, batch_id="b-promote")
    assert run.awaiting_review == 1

    # 2) 触发 job 56 → promote
    from backend.scheduler.jobs.legacy_promote import legacy_promote_due_job
    r = legacy_promote_due_job()
    assert r["candidates"] == 1
    assert r["promoted"] == 1

    # 3) v1_knowledge status='published', promote_log 1 行
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM v1_knowledge WHERE status = 'published'").fetchone()[0]
    assert n == 1
    log_n = conn.execute("SELECT COUNT(*) FROM v1_legacy_promote_log").fetchone()[0]
    assert log_n == 1


def test_legacy_migrate_resume_job_no_failed(c13_iso_env) -> None:
    """job 57 启动 → 0 failed + 0 awaiting_review → 返 0."""
    from backend.scheduler.jobs.legacy_promote import legacy_migrate_resume_job
    r = legacy_migrate_resume_job()
    assert r["failed_count"] == 0
    assert r["promoted_this_run"] == 0


def test_legacy_migrate_resume_job_returns_failed_rows(c13_iso_env) -> None:
    """job 57 启动 → 1 failed 返 1 + 触发 promote 收口 (无 awaiting → 0 promote)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO v1_legacy_mapping "
        "(legacy_source, legacy_id, legacy_revision, new_id, new_revision, "
        " content_hash, status, error, batch_id, migrated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("warm.knowledge_items", "failed1", None, "FAIL0000000000000000000000000", 1,
         "h" * 64, "failed", "test_error", "b-fail", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    from backend.scheduler.jobs.legacy_promote import legacy_migrate_resume_job
    r = legacy_migrate_resume_job()
    assert r["failed_count"] == 1
    assert r["failed_recent"][0]["legacy_id"] == "failed1"
    assert r["failed_recent"][0]["error"] == "test_error"
    assert r["promoted_this_run"] == 0
