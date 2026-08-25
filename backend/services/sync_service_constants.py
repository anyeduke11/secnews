"""P1.2: sync 模块共享常量 (供 sync_service.py 与 sync_fernet_mixin.py 使用)。"""
from __future__ import annotations

from datetime import datetime, timezone

# bundle schema 版本
BUNDLE_VERSION = "1.0"

# secrets 的元数据字段 (用于 3-way merge 比对, 不含加密密文)
SECRET_MERGE_FIELDS = (
    "name", "model", "base_url", "updated_at",
)

# settings 黑名单: 永不跨端同步的 key
# - session / runtime flags / 服务端临时状态
SETTINGS_BLOCKLIST = {
    "scheduler.last_run",
    "collector.last_run",
    "trend.last_rebuild",
    "sync_runtime_lock",  # sync 自己的运行锁
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_device_id() -> str:
    import uuid
    return str(uuid.uuid4())


__all__ = [
    "BUNDLE_VERSION",
    "SECRET_MERGE_FIELDS",
    "SETTINGS_BLOCKLIST",
    "new_device_id",
    "now_iso",
]