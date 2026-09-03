"""可读 ID 工厂 — 生成 {source}:{subtype}:{native_id} 格式的可读 ID。

Phase 11: 新 collector 使用 readable_id 作为 HotspotItem.id；
旧 collector 的 sha256 hash ID 保留为 hotspot_id 字段。

P1.5 (v0.7.x): 新增 ``make_readable_id_safe`` — 空 native_id 时
返回 ``None`` 而非抛异常, 让调用方在 _build_items 处显式处理
(此前 ValueError 被外层 try/except 静默吞掉, 同源撞库风险)。
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["make_readable_id", "make_readable_id_safe"]


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


def make_readable_id_safe(
    source: str, subtype: str, native_id: str | None
) -> str | None:
    """P1.5: 安全的可读 ID 构造 — 空 native_id / 清理后为空 → 返回 None。

    此前 ``make_readable_id`` 抛 ``ValueError`` 被 _build_items 外层
    try/except 静默吞掉, 整批 item 被丢且 result.error_msg 只显示
    "fetch failed" 通用错误, 同源撞库风险被遮蔽。

    新行为: 返回 None 让调用方显式 skip 单条 item + 记入 source 级
    "empty_native_id" 计数, 不再静默丢整批。

    Returns:
        可读 ID, 或 None (native_id 无效)。
    """
    if not native_id:
        return None
    try:
        return make_readable_id(source, subtype, str(native_id))
    except ValueError:
        # 清理后为空 (eg native_id 是 "  ...  ") → 视为无效
        return None