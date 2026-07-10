"""Phase 42 SyncService 测试 (3-way merge + bundle 构建 + encrypt/decrypt round-trip)。

覆盖:
- build_bundle 结构
- three_way_merge:
  - base==local, remote 变 → 接受 remote
  - base==remote, local 变 → 接受 local
  - 双方都变且不一致 → 冲突, last-write-wins
  - 记录级对齐 (按 primary key)
- settings merge: blocklist 过滤
- encrypt/decrypt_bundle round-trip
- should_run_catchup 时区判断
"""
from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterator
from zoneinfo import ZoneInfo

import pytest

from backend.repository.db import get_connection
from backend.scheduler.jobs import should_run_catchup
from backend.services.sync_service import (
    BUNDLE_VERSION,
    SETTINGS_BLOCKLIST,
    MergeResult,
    SyncService,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def db(tmp_path, monkeypatch) -> Iterator[None]:
    """建临时 DB + 跑迁移 (001-014); 所有读写真实连接都走 patched _get_conn (单例)。"""
    db_file = tmp_path / "test_sync.db"
    # 创建 schema
    setup_conn = sqlite3.connect(str(db_file))
    schema_dir = "backend/repository/migrations"
    for sql_file in (
        "001_init.sql", "002_quality.sql", "003_github_category.sql",
        "004_custom_sources.sql", "005_source_stats.sql", "006_favorites.sql",
        "007_ingested_at.sql", "008_bid_status.sql", "009_tech_category.sql",
        "010_history_batches.sql", "011_todos.sql", "012_skills.sql",
        "013_secrets.sql", "014_sync.sql",
    ):
        with open(f"{schema_dir}/{sql_file}", "r", encoding="utf-8") as f:
            setup_conn.executescript(f.read())
    setup_conn.commit()
    setup_conn.close()

    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    # 用单例连接, 避免多 connection 争锁
    shared_conn = sqlite3.connect(str(db_file), check_same_thread=False, timeout=30.0)
    shared_conn.row_factory = sqlite3.Row
    shared_conn.execute("PRAGMA journal_mode=WAL")
    shared_conn.execute("PRAGMA foreign_keys=ON")
    shared_conn.execute("PRAGMA busy_timeout=30000")

    def _get_conn():
        return shared_conn

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass
    yield
    shared_conn.close()


def _setup_master_key():
    """初始化主密钥 — secrets 服务需要。"""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.crypto import make_verify_blob, generate_salt, DEFAULT_ITERATIONS
    repo = EncryptionKeyRepository()
    if repo.is_setup():
        return
    repo.setup_default(master_key="test-master-key-strong-1234")


# ---------------------------------------------------------------------------
# three_way_merge 单元测试
# ---------------------------------------------------------------------------
def test_merge_remote_only_change():
    """base==local, remote 变 → 接受 remote。"""
    svc = SyncService()
    base = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "old", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    local = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "old", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    remote = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t1",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "new-from-remote", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    result = svc.three_way_merge(base, local, remote)
    assert result.conflict_count == 0
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "new-from-remote" in titles


def test_merge_local_only_change():
    """base==remote, local 变 → 接受 local。"""
    svc = SyncService()
    base = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "old", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    local = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t1",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "new-from-local", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    remote = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t0",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "old", "favorited_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    result = svc.three_way_merge(base, local, remote)
    assert result.conflict_count == 0
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "new-from-local" in titles


def test_merge_both_changed_conflict():
    """双方都变且不一致 → 冲突, last-write-wins (updated_at 较新者胜出)。"""
    svc = SyncService()
    base = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "old",
                                    "favorited_at": "t0", "updated_at": "t0"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    local = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t1",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "local-version",
                                    "favorited_at": "t0", "updated_at": "t1"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    remote = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t2",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "remote-version",
                                    "favorited_at": "t0", "updated_at": "t2"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [],
                    "settings": {}},
    }
    result = svc.three_way_merge(base, local, remote)
    assert result.conflict_count == 1
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "remote-version" in titles  # remote 更新, 胜出


def test_merge_addition_on_both_sides():
    """两边各自加新记录 → 都保留。"""
    svc = SyncService()
    base = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
        "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                    "secrets": [], "settings": {}},
    }
    local = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t1",
        "records": {"favorites": [{"hotspot_id": "h1", "title": "L"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [], "settings": {}},
    }
    remote = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t1",
        "records": {"favorites": [{"hotspot_id": "h2", "title": "R"}],
                    "todos": [], "skills": [], "custom_sources": [], "secrets": [], "settings": {}},
    }
    result = svc.three_way_merge(base, local, remote)
    titles = sorted(f["title"] for f in result.merged_bundle["records"]["favorites"])
    assert titles == ["L", "R"]


def test_merge_settings_blocklist_filtered():
    """SETTINGS_BLOCKLIST 里的 key 不进入 merged。"""
    svc = SyncService()
    base = {"version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
            "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                        "secrets": [], "settings": {}}}
    local = {"version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t1",
             "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                         "secrets": [],
                         "settings": {"keep": "x", "scheduler.last_run": "should-not-sync"}}}
    remote = {"version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t1",
              "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                          "secrets": [], "settings": {}}}
    result = svc.three_way_merge(base, local, remote)
    assert "keep" in result.merged_bundle["records"]["settings"]
    assert "scheduler.last_run" not in result.merged_bundle["records"]["settings"]


def test_merge_settings_conflict_counted():
    """settings 字段冲突计入 conflict_count。"""
    svc = SyncService()
    base = {"version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t0",
            "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                        "secrets": [], "settings": {"k": "v0"}}}
    local = {"version": BUNDLE_VERSION, "device_id": "a", "merged_at": "t1",
             "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                         "secrets": [], "settings": {"k": "v-local"}}}
    remote = {"version": BUNDLE_VERSION, "device_id": "b", "merged_at": "t1",
              "records": {"favorites": [], "todos": [], "skills": [], "custom_sources": [],
                          "secrets": [], "settings": {"k": "v-remote"}}}
    result = svc.three_way_merge(base, local, remote)
    assert result.table_conflicts["settings"] == 1


# ---------------------------------------------------------------------------
# bundle 构建 / 加密 round-trip
# ---------------------------------------------------------------------------
def test_build_bundle_structure(db):
    """build_bundle 至少包含 6 个 records 字段 + version + device_id + merged_at。"""
    _setup_master_key()
    svc = SyncService()
    bundle = svc.build_bundle()
    assert bundle["version"] == BUNDLE_VERSION
    assert "device_id" in bundle
    assert "merged_at" in bundle
    records = bundle["records"]
    for key in ("favorites", "todos", "skills", "custom_sources", "settings", "secrets"):
        assert key in records


def test_encrypt_decrypt_bundle_roundtrip(db):
    """encrypt → decrypt round-trip 应得到原 bundle。"""
    _setup_master_key()
    svc = SyncService()
    bundle = svc.build_bundle()
    payload = svc.encrypt_bundle(bundle, "test-master-key-strong-1234")
    assert isinstance(payload, bytes)
    envelope = json.loads(payload.decode("utf-8"))
    assert envelope["encryption_kind"] == "sync-bundle"
    assert envelope["encryption"]["algorithm"] == "Fernet"
    out = svc.decrypt_bundle(payload, "test-master-key-strong-1234")
    assert out["version"] == bundle["version"]
    assert out["device_id"] == bundle["device_id"]


def test_decrypt_wrong_master_key(db):
    _setup_master_key()
    svc = SyncService()
    bundle = svc.build_bundle()
    payload = svc.encrypt_bundle(bundle, "test-master-key-strong-1234")
    with pytest.raises(Exception) as ei:
        svc.decrypt_bundle(payload, "wrong-master-key-12345")
    assert "主密钥" in str(ei.value) or "decrypt" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# should_run_catchup
# ---------------------------------------------------------------------------
def test_should_run_catchup_not_monday():
    """非周一 → False"""
    # 周三
    wed = datetime(2026, 7, 8, 12, 0, tzinfo=SHANGHAI)
    assert should_run_catchup(None, wed) is False


def test_should_run_catchup_monday_before_cutoff():
    """周一但 10:30 前 → False"""
    mon_morning = datetime(2026, 7, 6, 9, 0, tzinfo=SHANGHAI)
    assert should_run_catchup(None, mon_morning) is False


def test_should_run_catchup_monday_after_cutoff_never_synced():
    """周一 10:30 后, 从未同步 → True"""
    mon = datetime(2026, 7, 6, 11, 0, tzinfo=SHANGHAI)
    assert should_run_catchup(None, mon) is True


def test_should_run_catchup_monday_after_cutoff_already_synced_today():
    """周一 10:30 后, 本周一 00:00 之后已同步 → False"""
    mon = datetime(2026, 7, 6, 11, 0, tzinfo=SHANGHAI)
    # 假设 10:45 同步过 (在 cutoff 之后, 在 monday 00:00 之后)
    last_sync = "2026-07-06T10:45:00+08:00"
    assert should_run_catchup(last_sync, mon) is False


def test_should_run_catchup_monday_after_cutoff_last_sync_last_week():
    """周一 10:30 后, 上周同步过 → True (catch-up)"""
    mon = datetime(2026, 7, 6, 11, 0, tzinfo=SHANGHAI)
    # 上周五同步过
    last_sync = "2026-07-03T15:00:00+08:00"
    assert should_run_catchup(last_sync, mon) is True


# ---------------------------------------------------------------------------
# repos 基本 CRUD
# ---------------------------------------------------------------------------
def test_sync_config_upsert_get(db):
    from backend.repository.sync_configs_repo import SyncConfigRepository
    repo = SyncConfigRepository()
    cfg = repo.upsert(
        webdav_url="https://dav.jianguoyun.com/dav",
        webdav_username="u@x.com",
        webdav_password_encrypted=b"cipher",
        webdav_password_salt=b"salt12345678abc",
        device_id="dev-1",
    )
    assert cfg.id is not None
    assert cfg.webdav_url == "https://dav.jianguoyun.com/dav"
    assert cfg.device_id == "dev-1"
    # 再 upsert 不会创建第二行
    cfg2 = repo.upsert(
        webdav_url="https://other.example/dav",
        webdav_username="u2@x.com",
    )
    assert cfg2.id == cfg.id
    assert cfg2.webdav_url == "https://other.example/dav"  # 改了
    # password 保留
    assert cfg2.webdav_password_encrypted == b"cipher"


def test_sync_history_write_list(db):
    from backend.repository.sync_history_repo import SyncHistoryRepository
    from backend.repository.sync_configs_repo import SyncConfigRepository
    cfg = SyncConfigRepository().upsert()
    hr = SyncHistoryRepository()
    hr.write(
        config_id=cfg.id, direction="push", status="success",
        records_count=10, started_at="t0", finished_at="t1",
    )
    hr.write(
        config_id=cfg.id, direction="pull", status="error",
        error_message="boom", started_at="t2", finished_at="t3",
    )
    items = hr.list_recent(cfg.id)
    assert len(items) == 2
    assert items[0]["direction"] == "pull"  # 较新在前
    assert items[1]["direction"] == "push"


def test_sync_state_upsert_get_clear(db):
    from backend.repository.sync_states_repo import SyncStateRepository
    from backend.repository.sync_configs_repo import SyncConfigRepository
    cfg = SyncConfigRepository().upsert()
    sr = SyncStateRepository()
    assert sr.get(cfg.id) is None
    sr.upsert(cfg.id, '{"x": 1}')
    state = sr.get(cfg.id)
    assert state is not None
    assert json.loads(state["bundle_json"]) == {"x": 1}
    # ON CONFLICT 覆盖
    sr.upsert(cfg.id, '{"x": 2}')
    assert json.loads(sr.get(cfg.id)["bundle_json"]) == {"x": 2}
    # clear
    assert sr.clear(cfg.id) is True
    assert sr.get(cfg.id) is None
