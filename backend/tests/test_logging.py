"""日志系统单元测试

验证：
  - setup() 不会抛错并能创建日志文件
  - JSON Lines 格式 + 必含字段 record.extra.trace_id / record.message / level
  - v0.7 Batch 1 (PRD §6.1): 切到 loguru 内置 serialize=True, 输出顶层
    "record.extra.trace_id" 而非历史 "trace_id" 字段; 读取方式 ``jq .record.extra.x``.
"""
import json
from pathlib import Path

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
    # serialize=True 形态: message 在 record.message
    assert any(item.get("record", {}).get("message") == "hello world"
               for item in parsed)


def test_logging_required_fields(tmp_path: Path):
    log_file = tmp_path / "fields.log"
    setup(log_file=str(log_file), also_stderr=False)
    # v0.7 Batch 1: bind 模式让 trace_id 进 record.extra 顶层
    logger.bind(trace_id="abc-123").info("fields-check")
    logger.complete()
    content = log_file.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in content.strip().split("\n") if line]
    matched = [item for item in lines
               if item.get("record", {}).get("message") == "fields-check"]
    assert matched, "expected at least one line with record.message=fields-check"
    item = matched[-1]
    rec = item["record"]
    # 必含字段
    for key in ("time", "level", "extra", "message"):
        assert key in rec, f"missing required record field: {key}"
    assert rec["extra"]["trace_id"] == "abc-123"
    assert rec["level"]["name"] == "INFO"


def test_logging_rotation_uses_max_bytes(tmp_path: Path):
    """验证 setup 接受 max_bytes 参数（实际轮转需要写入 50MB，不在此测试触发）。"""
    log_file = tmp_path / "rotation.log"
    setup(log_file=str(log_file), max_bytes=1024, backup_count=2, also_stderr=False)
    logger.info("rotation param check")
    logger.complete()
    assert log_file.exists()
