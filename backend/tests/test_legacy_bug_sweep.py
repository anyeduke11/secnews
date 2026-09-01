"""存量 bug 清扫 (fix/legacy-bugs-sweep) 回归测试.

锁定 5 处 schema/注册漂移修复:
- D1: encryption_keys _row() "role" in row 恒 False → role 永远读成 admin
- D2: hotspots.region INSERT 漏列 → region 恒 NULL, 地区筛选链静默失效
- D3: sync_history.table_conflicts 有列有读端但写端漏传 → 冲突明细恒 NULL
- D4: cg_services.discovery_source 写端写入但 _row_to_service 丢弃
- D5: llm_secrets.create() 无法指定 owner_role → API 创建恒 admin-owned
"""
from __future__ import annotations

import json

import pytest

from backend.repository.db import get_connection

# ── D1: encryption_keys.role 读出 ───────────────────────────────────


def test_d1_row_reads_role_from_db(temp_db):
    """DB 里 role='user' 时 _row() 必须读出 'user' (修复前恒 'admin')."""
    from backend.repository.db import get_connection
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository, _row

    ek = EncryptionKeyRepository()
    ek.setup_default(master_key="test-master-key-12345678", role="admin")
    # 手动把 role 改成 user 模拟 user 级密钥行
    conn = get_connection()
    conn.execute("UPDATE encryption_keys SET role = 'user'")
    row = conn.execute("SELECT * FROM encryption_keys LIMIT 1").fetchone()
    parsed = _row(row)
    assert parsed.role == "user"


def test_d6_setup_returns_last_rotated_at(temp_db):
    """setup_default/setup_user_key 返回值应含 last_rotated_at (此前为 None)."""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository

    ek = EncryptionKeyRepository()
    row = ek.setup_default(master_key="test-master-key-12345678", role="admin")
    assert row.last_rotated_at is not None


# ── D2: hotspots.region 写入链 ──────────────────────────────────────


def test_d2_region_roundtrip_via_upsert(temp_db):
    """upsert_many 写入 region → query 读出 region (修复前 INSERT 漏列恒 NULL)."""
    from datetime import datetime, timezone

    from backend.domain.models import Category, HotspotItem
    from backend.repository.hotspot_repo import HotspotRepository

    now = datetime.now(timezone.utc)
    item = HotspotItem(
        id="h-region-1",
        title="标讯条目",
        summary="",
        source="bid-src",
        url="https://example.com/bid/1",
        category=Category.BID,
        published_at=now,
        score=10,
        fetched_at=now,
        ingested_at=now,
        region="华东",
    )
    repo = HotspotRepository()
    repo.upsert_many([item])

    got = repo.get_by_id("h-region-1")
    assert got is not None
    assert got.region == "华东"


def test_d2_region_filter_finds_rows(temp_db):
    """region=? 筛选在写入链修复后应能命中."""
    from datetime import datetime, timedelta, timezone

    from backend.domain.models import Category, HotspotItem
    from backend.repository.hotspot_repo import HotspotRepository

    now = datetime.now(timezone.utc)
    items = [
        HotspotItem(
            id=f"h-{i}",
            title=f"标讯 {i}",
            summary="",
            source="bid-src",
            url=f"https://example.com/bid/{i}",
            category=Category.BID,
            published_at=now - timedelta(hours=i),
            score=10,
            fetched_at=now,
            ingested_at=now,
            region="华北" if i % 2 == 0 else "华南",
        )
        for i in range(4)
    ]
    repo = HotspotRepository()
    repo.upsert_many(items)

    found = repo.query(Category.BID, region="华北")
    assert len(found) == 2


# ── D3: sync_history.table_conflicts 写入 ───────────────────────────


def test_d3_table_conflicts_roundtrip(temp_db):
    """write(table_conflicts=...) → list_recent 读出 JSON (修复前恒 NULL)."""
    from backend.repository.db import get_connection
    from backend.repository.sync_history_repo import SyncHistoryRepository

    # config_id FK → 先建一条 sync_config (按 014_sync 真实 schema)
    get_connection().execute(
        "INSERT INTO sync_configs (id, name, created_at, updated_at) "
        "VALUES (1, 'test-cfg', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')"
    )
    repo = SyncHistoryRepository()
    conflicts = {"todos": 2, "favorites": 1}
    repo.write(
        config_id=1,
        direction="pull",
        status="success",
        conflict_count=3,
        started_at="2026-09-01T00:00:00+00:00",
        finished_at="2026-09-01T00:01:00+00:00",
        table_conflicts=json.dumps(conflicts),
    )
    rows = repo.list_recent(1)
    assert rows[0]["table_conflicts"] is not None
    assert json.loads(rows[0]["table_conflicts"]) == conflicts


# ── D4: cg_services.discovery_source 读出 ───────────────────────────


def test_d4_discovery_source_roundtrip(temp_db):
    """INSERT 写 'auto' → 读端应返回 discovery_source (修复前丢弃)."""
    from backend.repository.codegarden_service_repo import CodegardenServiceRepository

    repo = CodegardenServiceRepository()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO cg_services (
            id, project_id, name, namespace, type, runtime, status,
            discovery_source, created_at
        ) VALUES ('svc-1', NULL, 'api', NULL, 'http', 'docker', 'running',
                  'auto', '2026-09-01T00:00:00+00:00')
        """
    )
    got = repo.get("svc-1")
    assert got is not None
    assert got["discovery_source"] == "auto"


# ── D5: create_secret owner_role 透传 ───────────────────────────────


def test_d5_create_secret_with_owner_role_user(temp_db):
    """repo.create(owner_role='user') → 读端 owner_role='user' + 可见性正确."""
    from backend.crypto import derive_fernet_key
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository

    ek = EncryptionKeyRepository()
    row = ek.setup_default(master_key="test-master-key-12345678", role="admin")
    fernet_key = derive_fernet_key(
        "test-master-key-12345678", row.salt, row.iterations
    )

    sr = SecretRepository()
    item = sr.create(
        name="user-secret",
        model="llama3",
        base_url="http://localhost:11434",
        api_key="dummy-key",
        fernet_key=fernet_key,
        encryption_key_id=row.id,
        provider="ollama",
        owner_role="user",
    )
    assert item.owner_role == "user"

    # user 角色可见, admin 角色也可见 (rank 高)
    got_user = sr.get(item.id, actor_role="user")
    assert got_user is not None
    got_admin = sr.get(item.id, actor_role="admin")
    assert got_admin is not None


def test_d5_create_secret_rejects_bad_role(temp_db):
    """owner_role 非法值应拒绝."""
    from backend.crypto import derive_fernet_key
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository

    ek = EncryptionKeyRepository()
    row = ek.setup_default(master_key="test-master-key-12345678", role="admin")
    fernet_key = derive_fernet_key(
        "test-master-key-12345678", row.salt, row.iterations
    )
    sr = SecretRepository()
    with pytest.raises(Exception):
        sr.create(
            name="bad",
            model="m",
            base_url="https://x.example",
            api_key="k",
            fernet_key=fernet_key,
            encryption_key_id=row.id,
            owner_role="superuser",
        )
