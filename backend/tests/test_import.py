"""legacy ``cache_data.json`` 导入工具 单元测试

每个测试：
  1. 把 ``backend/cache_data.json`` 复制到 ``tmp_path`` 隔离的副本
  2. monkeypatch ``config.db_path`` 到 ``tmp_path/test.db``
  3. 调用 ``import_from_cache_json``，DB 写入到 tmp_path，备份文件
     也写到 tmp_path（避免在 ``backend/`` 累积 .bak 噪音）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.tools.import_cache import import_from_cache_json


# 仓库根目录下的真实 cache_data.json
# this file is in backend/tests/ → parents[0]=tests, parents[1]=backend, parents[2]=project_root
# cache_data.json lives in backend/
REAL_CACHE = Path(__file__).resolve().parents[1] / "cache_data.json"


def pytest_collection_modifyitems(config, items):
    """如果真实 cache_data.json 不存在，跳过 test_import 全部测试。"""
    if not REAL_CACHE.exists():
        skip_marker = pytest.mark.skip(
            reason=f"legacy cache_data.json not present at {REAL_CACHE}"
        )
        for item in items:
            if "test_import" in str(item.fspath):
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_import(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把 cache_data.json 复制到 tmp_path，DB 也指向 tmp_path。"""
    # 1. 隔离 DB
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()

    # 2. 复制源文件到 tmp_path（如果源文件存在）
    if REAL_CACHE.exists():
        local_cache = tmp_path / "cache_data.json"
        shutil.copy2(REAL_CACHE, local_cache)
    else:
        # 源文件不存在时，构造一个空的占位 JSON，使 import 不报错
        local_cache = tmp_path / "cache_data.json"
        local_cache.write_text(
            '{"timestamp": 0, "payload": {"items": []}}', encoding="utf-8"
        )

    yield local_cache, test_db
    db.close_db()


# ---------------------------------------------------------------------------
# 1. 备份
# ---------------------------------------------------------------------------
def test_import_creates_backup(isolated_import):
    """导入后应在源文件同目录生成 ``.bak.<timestamp>`` 备份。"""
    cache_path, _test_db = isolated_import
    result = import_from_cache_json(cache_path)
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    # 备份文件名形如 cache_data.bak.YYYYMMDDHHMMSS.json
    assert backup_path.stem.startswith("cache_data.bak.")
    assert backup_path.suffix == ".json"


# ---------------------------------------------------------------------------
# 2. 所有行 is_fallback=True
# ---------------------------------------------------------------------------
def test_import_marks_all_as_fallback(isolated_import):
    cache_path, _test_db = isolated_import
    result = import_from_cache_json(cache_path)
    assert result["imported_count"] > 0, "should have imported real data"

    repo = HotspotRepository()
    from backend.domain.enums import TimeRange
    items, _ = repo.query(None, time_range=TimeRange.D30, limit=200)

    # 至少要导入了一些行
    assert len(items) > 0
    for it in items:
        assert it.is_fallback is True, f"item {it.id} should be is_fallback=True"


# ---------------------------------------------------------------------------
# 3. quality_flags 包含 "legacy_import"
# ---------------------------------------------------------------------------
def test_import_legacy_quality_flags(isolated_import):
    cache_path, _test_db = isolated_import
    import_from_cache_json(cache_path)

    from backend.domain.enums import TimeRange
    items, _ = HotspotRepository().query(None, time_range=TimeRange.D30, limit=200)
    assert len(items) > 0
    for it in items:
        assert "legacy_import" in it.quality_flags, (
            f"item {it.id} should have 'legacy_import' in quality_flags; "
            f"got {it.quality_flags}"
        )


# ---------------------------------------------------------------------------
# 4. 幂等
# ---------------------------------------------------------------------------
def test_import_idempotent(isolated_import):
    """连续运行 2 次：imported_count 一致，DB 行数不变。"""
    cache_path, test_db = isolated_import

    first = import_from_cache_json(cache_path)
    # 第一次写入后的行数
    conn = db.get_connection()
    rows_after_first = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]

    second = import_from_cache_json(cache_path)
    rows_after_second = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]

    # imported_count 在两次调用之间应一致（两次都是从同一文件解析同一份原始数据）
    assert first["imported_count"] == second["imported_count"]
    assert first["imported_count"] > 0
    # 行数不变（upsert 是 ON CONFLICT DO UPDATE）
    assert rows_after_first == rows_after_second
