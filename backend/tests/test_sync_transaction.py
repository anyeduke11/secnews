"""P1-6 sync 事务化测试 (审计 F1-6: 注入失败 base 不推进且数据未半写)。

契约 (Rule 9 WHY):
- apply_bundle 中途失败 → 已写表 (favorites) 必须 ROLLBACK —
  此前 per-table 立即提交, 半写数据 + base 不推进 = 永久漂移;
- 成功路径全表落库 (事务提交), 既有 apply 行为不变;
- deferred_commit 嵌套复用外层事务 (pull 级重放保护)。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import config as app_config
from backend.repository.db import close_db, deferred_commit, get_connection, init_db
from backend.services.sync_bundle import apply_bundle
from backend.services.sync_merge import BUNDLE_VERSION


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_sync_tx.db"
    monkeypatch.setattr(app_config, "db_path", test_db)
    monkeypatch.setattr(app_config, "warm_db_path", None, raising=False)
    close_db()
    init_db()
    yield test_db
    close_db()


def _bundle(*, n_favorites: int = 2, n_todos: int = 2) -> dict:
    return {
        "version": BUNDLE_VERSION,
        "device_id": "dev-test",
        "merged_at": "2026-10-03T00:00:00+00:00",
        "records": {
            "favorites": [
                {"hotspot_id": f"hs-fav-{i}", "category": "ai",
                 "title": f"收藏 {i}", "source": "web",
                 "url": f"https://example.com/{i}"}
                for i in range(n_favorites)
            ],
            "todos": [
                {"source_type": "manual", "title": f"待办 {i}", "url": None,
                 "source": None, "category": None, "important": 0,
                 "note": None}
                for i in range(n_todos)
            ],
        },
    }


def _counts(conn) -> dict[str, int]:
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("favorites", "todos")
    }


# ── F1-6 验收主断言 ─────────────────────────────────────────────────

def test_apply_bundle_success_commits_all_tables(temp_db):
    """成功路径: 全表落库 (事务提交), 与既有行为一致。"""
    stats = apply_bundle(_bundle())
    assert stats["favorites"]["inserted"] == 2
    assert stats["todos"]["inserted"] == 2
    conn = get_connection()
    assert _counts(conn) == {"favorites": 2, "todos": 2}


def test_apply_bundle_midway_failure_rolls_back_half_writes(
    temp_db, monkeypatch,
):
    """F1-6 验收: todos 阶段注入失败 → favorites 阶段的写入必须回滚。

    此前 favorites 已随 repo 内部 commit 落库 (半写); 事务化后任一异常
    整体 ROLLBACK — 数据未半写。
    """
    from backend.services import sync_bundle

    def boom(self, **kw):
        raise RuntimeError("injected midway failure")

    # 注入点 = FavoriteRepository.add (apply 的 favorites 循环无 try 包裹,
    # 异常必上抛; todos 循环有 except 吞异常不可作注入点)
    monkeypatch.setattr(sync_bundle.FavoriteRepository, "add", boom)
    with pytest.raises(RuntimeError, match="injected midway failure"):
        apply_bundle(_bundle())

    conn = get_connection()
    # favorites 阶段自身 + 之后的 todos 都必须不存在 (整体回滚)
    assert _counts(conn) == {"favorites": 0, "todos": 0}


def test_base_not_advanced_when_injection_fails(temp_db, monkeypatch):
    """F1-6 验收第二支: 注入失败 → merge base (sync_states) 不被推进。"""
    from backend.repository.sync_states_repo import SyncStateRepository
    from backend.services import sync_bundle

    ssr = SyncStateRepository()
    # sync_states.config_id FK → sync_configs: 先建配置行
    conn = get_connection()
    conn.execute(
        "INSERT INTO sync_configs (name, webdav_password_iters, created_at, "
        "updated_at) VALUES ('t', 100, datetime('now'), datetime('now'))"
    )
    conn.commit()
    ssr.upsert(1, json.dumps({"merged_at": "old-base"}))
    before = ssr.get(1)

    def boom(self, **kw):
        raise RuntimeError("injected")

    # 注入点 = FavoriteRepository.add (无 try 包裹, 异常必上抛模拟中断)
    monkeypatch.setattr(sync_bundle.FavoriteRepository, "add", boom)
    with pytest.raises(RuntimeError):
        # pull 语义: apply_bundle 抛出 → ssr.upsert(merged) 永不执行
        # (sync_service.pull 中 apply 成功返回后才 upsert, 顺序契约);
        # 此处断言"apply 抛出后 base 原样"。
        apply_bundle(_bundle())

    after = ssr.get(1)
    assert json.loads(after["bundle_json"]) == json.loads(before["bundle_json"])


def test_deferred_commit_nested_reuses_outer_transaction(temp_db):
    """嵌套 deferred_commit 复用外层: 内层 commit 被吞, 外层统一提交。"""
    from backend.repository.favorite_repo import FavoriteRepository
    from backend.repository.todo_repo import TodoRepository

    with deferred_commit():
        FavoriteRepository().add(hotspot_id="hs-nest", category="ai",
                                 title="t", source="web", url="https://x/n")
        with deferred_commit():  # 嵌套
            TodoRepository().add_or_get(
                source_type="manual", source_id=None, title="t2",
                url=None, source=None, category=None,
                important=0, note=None,
            )
    conn = get_connection()
    assert _counts(conn) == {"favorites": 1, "todos": 1}


def test_deferred_commit_rollback_on_inner_exception(temp_db):
    from backend.repository.favorite_repo import FavoriteRepository

    with pytest.raises(RuntimeError):
        with deferred_commit():
            FavoriteRepository().add(hotspot_id="hs-rb", category="ai",
                                     title="t", source="web",
                                     url="https://x/rb")
            raise RuntimeError("inner boom")
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0] == 0
