"""日志系统单元测试

验证：
  - setup() 不会抛错并能创建日志文件
  - JSON Lines 格式 + 必含字段 ts/level/module/msg/trace_id
"""
import json
from pathlib import Path

import pytest
from loguru import logger

from backend.logging_config import setup


def test_logging_creates_log_file(tmp_path: Path):
    log_file = tmp_path / "app.log"
    setup(log_file=str(log_file), also_stderr=False)
    logger.info("test message")
    logger.complete()
    assert log_file.exists()


def test_logging_json_format(tmp_path: Path):
    log_file = tmp_path / "test_json.log"
    setup(log_file=str(log_file), also_stderr=False)
    logger.info("hello world")
    logger.complete()
    content = log_file.read_text(encoding="utf-8")
    lines = [line for line in content.strip().split("\n") if line]
    assert lines, "log file should have at least one line"
    parsed = [json.loads(line) for line in lines]
    assert any(item.get("msg") == "hello world" for item in parsed)


def test_logging_required_fields(tmp_path: Path):
    log_file = tmp_path / "fields.log"
    setup(log_file=str(log_file), also_stderr=False)
    # 注意：loguru 把 "extra" 当作普通 kwarg 时会嵌套到 record["extra"]["extra"]，
    # 直接传 trace_id=... 是最稳的做法。
    logger.info("fields-check", trace_id="abc-123")
    logger.complete()
    content = log_file.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in content.strip().split("\n") if line]
    matched = [item for item in lines if item.get("msg") == "fields-check"]
    assert matched, "expected at least one line with msg=fields-check"
    item = matched[-1]
    # 必含字段
    for key in ("ts", "level", "module", "msg", "trace_id"):
        assert key in item, f"missing required field: {key}"
    assert item["trace_id"] == "abc-123"
    assert item["level"] == "INFO"


def test_logging_rotation_uses_max_bytes(tmp_path: Path):
    """验证 setup 接受 max_bytes 参数（实际轮转需要写入 50MB，不在此测试触发）。"""
    log_file = tmp_path / "rotation.log"
    setup(log_file=str(log_file), max_bytes=1024, backup_count=2, also_stderr=False)
    logger.info("rotation param check")
    logger.complete()
    assert log_file.exists()
