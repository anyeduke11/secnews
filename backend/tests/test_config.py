"""配置中心单元测试

验证：
  - 默认值正确
  - HOTSPOT_ 前缀环境变量可覆盖
  - 关键字段类型与 quality_* 默认值
"""
import os

import pytest

from backend.config import Settings, config


def test_default_values():
    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.cache_ttl_seconds == 300
    assert s.cache_maxsize == 64
    assert s.collect_interval_seconds == 300
    assert s.log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("HOTSPOT_PORT", "9999")
    monkeypatch.setenv("HOTSPOT_HOST", "127.0.0.1")
    s = Settings()
    assert s.port == 9999
    assert s.host == "127.0.0.1"


def test_quality_defaults():
    s = Settings()
    assert s.quality_strict_mode is False
    assert s.quality_min_score == 30
    assert s.quality_url_check_enabled is True
    assert s.quality_url_check_sample_rate == 0.1
    assert s.quality_url_check_timeout == 8


def test_paths_are_paths():
    s = Settings()
    # log_dir / db_path / backup_dir 应是 Path
    from pathlib import Path
    assert isinstance(s.log_dir, Path)
    assert isinstance(s.db_path, Path)
    assert isinstance(s.backup_dir, Path)


def test_global_singleton_present():
    assert config is not None
    assert config.port >= 0
