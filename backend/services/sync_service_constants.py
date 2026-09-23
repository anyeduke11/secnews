"""P1.2: sync 模块共享常量 (供 sync_service.py 与 sync_fernet_mixin.py 使用)。"""
from __future__ import annotations

from datetime import datetime, timezone

# bundle schema 版本
BUNDLE_VERSION = "1.0"

# secrets 的元数据字段 (用于 3-way merge 比对, 不含加密密文)
SECRET_MERGE_FIELDS = (
    "name", "model", "base_url", "updated_at",
)

# settings 跨端同步白名单 (2026-09-22 P3, settings-refactor Task 16): 仅用户
# 偏好/配置 namespace 进 bundle。密钥 (webhook.secret 已迁 vault) / 运行状态
# (state.*) / 服务端锁 永不跨端。与 settings_service._ALLOWED_PREFIXES (写入
# 契约) 语义对齐但更窄: state.*/feature.*/secrets.* 不跨端, 两处勿混用。
SETTINGS_SYNC_PREFIXES = (
    "collection.", "llm.", "interest.", "quality.",
)


def settings_sync_allowed(key: str) -> bool:
    return key.startswith(SETTINGS_SYNC_PREFIXES)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_device_id() -> str:
    import uuid
    return str(uuid.uuid4())


__all__ = [
    "BUNDLE_VERSION",
    "SECRET_MERGE_FIELDS",
    "SETTINGS_SYNC_PREFIXES",
    "new_device_id",
    "now_iso",
    "settings_sync_allowed",
]