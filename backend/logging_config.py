"""结构化日志配置（loguru + JSON Lines）

使用：
    from backend.logging_config import setup
    setup()  # 在应用启动最早处调用一次
    from loguru import logger
    logger.info("hello", extra={"trace_id": "abc"})
"""
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger as _default_logger

# 默认日志目录
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = BASE_DIR / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "app.log"


# JSON Lines 格式模板：ts / level / module / msg / trace_id
# 注意：loguru 会先把模板里的 {xxx} 占位符替换成实际值，
# 然后再对结果调用 .format_map(record) 二次格式化。
# 因此 JSON 字面量中的 { 和 } 必须转义为 {{ 和 }}，否则会被当成
# 占位符去 record 里查找 "ts" 之类的 key，导致 KeyError。
_JSON_LINE_FORMAT = (
    '{{"ts": "{time:YYYY-MM-DDTHH:mm:ss.SSS!UTC}Z", '
    '"level": "{level.name}", '
    '"module": "{name}", '
    '"msg": "{message}", '
    '"trace_id": "{extra[trace_id]}"}}\n'
)
_PLAIN_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}\n"
)


def _ensure_trace_id_default(record) -> None:
    """patcher：保证 record['extra']['trace_id'] 一定存在。"""
    extra = record.get("extra", {})
    if "trace_id" not in extra:
        extra["trace_id"] = ""


def setup(
    log_file: Optional[str] = None,
    level: str = "INFO",
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 5,
    serialize: bool = True,
    also_stderr: bool = True,
) -> None:
    """初始化全局日志配置。

    Args:
        log_file: 日志文件路径，None 则使用 backend/logs/app.log
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        max_bytes: 单个日志文件最大字节数（默认 50MB）
        backup_count: 保留的历史日志文件数
        serialize: 是否输出 JSON Lines 格式（默认 True）
        also_stderr: 是否同时输出到 stderr（开发体验）
    """
    # 解析日志文件路径
    if log_file is None:
        log_path = DEFAULT_LOG_FILE
    else:
        log_path = Path(log_file)

    # 确保日志目录存在
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler
    _default_logger.remove()

    # 安装 patcher：保证 trace_id 字段一定存在
    _default_logger.configure(patcher=_ensure_trace_id_default)

    # 文件 handler（带轮转）
    file_format = _JSON_LINE_FORMAT if serialize else _PLAIN_FORMAT
    _default_logger.add(
        str(log_path),
        level=level,
        rotation=max_bytes,
        retention=backup_count,
        encoding="utf-8",
        enqueue=True,
        format=file_format,
    )

    # stderr handler（开发用，固定为可读格式）
    if also_stderr:
        _default_logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        )

    _default_logger.info("logging initialized", trace_id="")


__all__ = ["setup", "logger"]


# 重新导出 logger 便于统一引用
logger = _default_logger
