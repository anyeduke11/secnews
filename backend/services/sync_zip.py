"""Phase 49 跨端同步: 同步包打包/解包 (zip 容器)。

设计要点
--------

- **格式**: 单一 zip 容器,内含 2 个文件:
  - ``envelope.json`` — 加密的 sync bundle envelope (Fernet 密文), 与原 json 内容兼容
  - ``manifest.json`` — 同步元数据 (时间/device/conflict/records/algorithm),明文,
    用户在远端文件管理器 / 离线审计时也能看到同步概况

- **命名**: ``配置文件-YYYY-MM-DD.zip``(中文名 + 日期), 覆盖式(同一天多次同步只
  保留最新一份;跨天会生成新 zip,远程可保留多份历史)。

- **安全**: ``envelope.json`` 仍走 Fernet 加密, master_key 不出现在 manifest 中。

- **zip 编码**: ZIP_DEFLATED, level=6(平衡压缩率与时间)。小文件(< 1MB)
  几乎不压缩, 主要为结构清晰。
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

# zip 内文件名常量
ENVELOPE_FILENAME = "envelope.json"
MANIFEST_FILENAME = "manifest.json"


def _today_str() -> str:
    """返回 YYYY-MM-DD (UTC)。同步包命名固定 UTC,避免跨时区歧义。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def make_zip_remote_path(base_dir: str) -> str:
    """根据基础目录生成今日同步包路径: ``base_dir/配置文件-YYYY-MM-DD.zip``。

    例: ``/hotspot`` → ``/hotspot/配置文件-2026-07-10.zip``

    重复调用同一天返回相同路径(覆盖式)。
    """
    base = (base_dir or "").rstrip("/")
    if not base or base == "/":
        return f"/配置文件-{_today_str()}.zip"
    return f"{base}/配置文件-{_today_str()}.zip"


def build_sync_zip(
    *, envelope_bytes: bytes, device_id: str, merged_at: str,
    direction: str, records_count: int, conflict_count: int,
    encryption: dict, version: str = "1.0",
) -> bytes:
    """打包 sync zip。返回 zip 字节流。

    ``envelope_bytes``: 完整的 Fernet 密文 envelope (json 序列化后的 utf-8 bytes)
    ``device_id``: 生成端 ID
    ``merged_at``: ISO 时间戳 (来自 bundle)
    ``direction``: ``push`` / ``pull`` / ``bidirectional``
    ``records_count``: bundle 内 records 总数
    ``conflict_count``: 3-way merge 冲突数 (push=0)
    ``encryption``: 算法描述 (algorithm / kdf / iterations / salt_b64)
    """
    manifest = {
        "version": version,
        "device_id": device_id,
        "merged_at": merged_at,
        "packaged_at": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "records_count": records_count,
        "conflict_count": conflict_count,
        "encryption": encryption,
        "contents": [ENVELOPE_FILENAME, MANIFEST_FILENAME],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(ENVELOPE_FILENAME, envelope_bytes)
        zf.writestr(MANIFEST_FILENAME, manifest_bytes)
    return buf.getvalue()


def extract_sync_zip(zip_bytes: bytes) -> tuple[bytes, dict]:
    """解包 sync zip。返回 ``(envelope_bytes, manifest)``。

    异常:
    - 不是合法 zip → ``ValueError``
    - 缺 envelope.json / manifest.json → ``ValueError``
    - manifest.json 格式错 → ``ValueError``
    """
    buf = io.BytesIO(zip_bytes)
    try:
        with zipfile.ZipFile(buf, mode="r") as zf:
            names = zf.namelist()
            if ENVELOPE_FILENAME not in names:
                raise ValueError(f"zip 缺少 {ENVELOPE_FILENAME}: 含 {names}")
            if MANIFEST_FILENAME not in names:
                raise ValueError(f"zip 缺少 {MANIFEST_FILENAME}: 含 {names}")
            envelope_bytes = zf.read(ENVELOPE_FILENAME)
            manifest_bytes = zf.read(MANIFEST_FILENAME)
    except zipfile.BadZipFile as e:
        raise ValueError(f"不是合法 zip 文件: {e}") from e

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"manifest.json 解析失败: {e}") from e
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json 必须为 dict")
    return envelope_bytes, manifest


__all__ = [
    "ENVELOPE_FILENAME",
    "MANIFEST_FILENAME",
    "make_zip_remote_path",
    "build_sync_zip",
    "extract_sync_zip",
]
