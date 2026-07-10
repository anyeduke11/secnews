"""SettingsRepository 单元测试

每个测试使用 tmp_path 隔离的临时 SQLite，并通过 monkeypatch
重定向 ``config.db_path``，避免污染真实 ``backend/hotspot.db``。
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.settings_repo import SettingsRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db) -> SettingsRepository:
    return SettingsRepository()


# ---------------------------------------------------------------------------
# get / set
# ---------------------------------------------------------------------------
def test_set_and_get_string(repo):
    repo.set("theme", "dark")
    assert repo.get("theme") == "dark"


def test_set_and_get_int(repo):
    """set("ttl", 600) → get 返回 int 600。"""
    repo.set("ttl", 600)
    val = repo.get("ttl")
    assert val == 600
    assert isinstance(val, int)


def test_set_and_get_dict(repo):
    payload = {"mode": "off", "host": "127.0.0.1", "port": 8080}
    repo.set("proxy", payload)
    assert repo.get("proxy") == payload


def test_get_with_default(repo):
    """get 不存在的 key 应返回 default。"""
    assert repo.get("nonexistent", "x") == "x"
    # 没传 default 时返回 None
    assert repo.get("nope") is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
def test_delete_returns_true_then_false(repo):
    """delete 已存在 key → True；再次 delete → False。"""
    repo.set("a", 1)
    assert repo.delete("a") is True
    assert repo.delete("a") is False
    # delete 不存在的 key 也是 False
    assert repo.delete("never-set") is False


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------
def test_list_all_returns_dict(repo):
    """list_all 应返回所有 (key, deserialised) 对。

    Phase 3.5 后，002_quality.sql 也会 seed 若干 ``quality.*`` key；
    我们只校验业务 key 存在 + 质量 key 也存在。
    """
    repo.set("a", 1)
    repo.set("b", "two")
    repo.set("c", {"nested": True})
    out = repo.list_all()
    # 业务 key 全部就位
    for k, v in (("a", 1), ("b", "two"), ("c", {"nested": True})):
        assert out[k] == v
    # Phase 3.5 seed
    assert "quality.strict_mode" in out
    assert "quality.category_keywords.ai" in out


def test_list_all_contains_phase35_defaults(repo):
    """Phase 3.5 迁移后，list_all 至少包含 6 个 quality.* key。"""
    out = repo.list_all()
    quality_keys = [k for k in out if k.startswith("quality.")]
    assert len(quality_keys) >= 6
