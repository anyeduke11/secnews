"""结构化日志配置（loguru + JSON Lines）

使用：
    from backend.logging_config import setup
    setup()  # 在应用启动最早处调用一次
    from loguru import logger
    logger.info("hello", extra={"trace_id": "abc"})

v0.7 Observability Batch 1 (docs/Observability_PRD_v1.0.md §6.1):
    历史 (logging_config.py:19-25) 的手写 JSON 模板只挑 5 个固定字段,
    log_event 传入的 method/path/status/duration_ms 全部不进文件。
    修法: 切到 loguru 内置 ``serialize=True``, 走 loguru 自己的 JSON
    序列化器, 全部 record["extra"] 字段都会落到 "record.extra" 子对象
    下; 与历史顶层 5 字段契约相比, 多了一层 "record" / "text" 包装。
    读取方式: ``jq '.record.extra.method'`` / ``jq '.record.extra.status'``。
    patcher 仍注入 trace_id/event 默认空串, 方便下游查询。
"""
import sys
from pathlib import Path

from loguru import logger as _default_logger

# 顶层 JSON 模板 (保留作为配置参考 / 旧契约回退)
_JSON_LINE_FORMAT = (
    '{{"ts": "{time:YYYY-MM-DDTHH:mm:ss.SSS!UTC}Z", '
    '"level": "{level.name}", '
    '"module": "{name}", '
    '"msg": "{message}", '
    '"trace_id": "{extra[trace_id]}", '
    '"event": "{extra[event]}"}}\n'
)
_PLAIN_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}\n"
)


def _ensure_trace_id_default(record) -> None:
    """patcher：保证 record['extra']['trace_id'/'event'] 一定存在（默认空串）。

    v0.7 Batch 1: event 也注入默认空串, 让模板渲染不抛 KeyError,
    与 trace_id 行为一致。
    """
    extra = record.get("extra", {})
    if "trace_id" not in extra:
        extra["trace_id"] = ""
    if "event" not in extra:
        extra["event"] = ""


def setup(
    log_file: str | None = None,
    level: str | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
    serialize: bool = True,
    also_stderr: bool = True,
) -> None:
    """初始化全局日志配置。

    Args:
        log_file: 日志文件路径，None 则使用 config.log_dir/app.log
        level: 日志级别（DEBUG/INFO/WARNING/ERROR），None 则使用 config.log_level
        max_bytes: 单个日志文件最大字节数，None 则使用 config.log_max_bytes
        backup_count: 保留的历史日志文件数，None 则使用 config.log_backup_count
        serialize: 是否输出 JSON Lines 格式（默认 True）
        also_stderr: 是否同时输出到 stderr（开发体验）
    """
    # v1.8: 未显式传参时消费 config 的 log_* 配置（env 可覆盖）
    # 延迟导入避免 config ↔ logging_config 潜在循环依赖
    from backend.config import config as _cfg

    if level is None:
        level = _cfg.log_level
    if max_bytes is None:
        max_bytes = _cfg.log_max_bytes
    if backup_count is None:
        backup_count = _cfg.log_backup_count

    # 解析日志文件路径
    log_path = Path(_cfg.log_dir) / "app.log" if log_file is None else Path(log_file)

    # 确保日志目录存在
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler
    _default_logger.remove()

    # 安装 patcher：保证 trace_id 字段一定存在
    _default_logger.configure(patcher=_ensure_trace_id_default)

    # 文件 handler（带轮转）
    if serialize:
        # v0.7 Batch 1 (PRD §6.1): 切到 loguru 内置 serialize=True,
        # 全部 record["extra"] 进 "record.extra" 子对象。
        # 读法: jq '.record.extra.method' / '.record.extra.status'。
        _default_logger.add(
            str(log_path),
            level=level,
            rotation=max_bytes,
            retention=backup_count,
            encoding="utf-8",
            enqueue=True,
            serialize=True,
        )
    else:
        _default_logger.add(
            str(log_path),
            level=level,
            rotation=max_bytes,
            retention=backup_count,
            encoding="utf-8",
            enqueue=True,
            format=_PLAIN_FORMAT,
        )

    # stderr handler（开发用，固定为可读格式）
    if also_stderr:
        _default_logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        )

    _default_logger.info("logging initialized", trace_id="")


__all__ = ["logger", "setup"]


# 重新导出 logger 便于统一引用
logger = _default_logger
