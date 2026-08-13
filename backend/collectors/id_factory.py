"""可读 ID 工厂 — 生成 {source}:{subtype}:{native_id} 格式的可读 ID。

Phase 11: 新 collector 使用 readable_id 作为 HotspotItem.id；
旧 collector 的 sha256 hash ID 保留为 hotspot_id 字段。
"""

from __future__ import annotations

import re

__all__ = ["make_readable_id"]


def _sanitize(text: str) -> str:
    """清理字符串中的特殊字符。

    - 转小写
    - 空白字符（空格、制表符、换行等）替换为连字符
    - 只保留字母、数字、连字符、下划线、点
    """
    text = text.lower().strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-_.]", "", text)
    return text.strip("-")


def make_readable_id(source: str, subtype: str, native_id: str) -> str:
    """生成可读 ID: {source}:{subtype}:{native_id}

    - source: 源名称（小写，如 "hn", "reddit"）
    - subtype: 子类型（如 "item", "comment", "post"）
    - native_id: 源原生 ID（如 HN 的 story ID）
    - 返回: "hn:item:12345678"

    Raises:
        ValueError: 当 source / subtype / native_id 为空或 None 时
    """
    if not source or not subtype or not native_id:
        raise ValueError(
            f"source, subtype, native_id 不能为空: "
            f"source={source!r}, subtype={subtype!r}, native_id={native_id!r}"
        )

    src = _sanitize(source)
    sub = _sanitize(subtype)
    nid = _sanitize(native_id)

    if not src or not sub or not nid:
        raise ValueError(
            f"source, subtype, native_id 清理后不能为空: "
            f"source={source!r}, subtype={subtype!r}, native_id={native_id!r}"
        )

    return f"{src}:{sub}:{nid}"