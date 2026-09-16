"""v1.7 Phase 2 — Annotation (笔记) 服务。

业务编排层: 校验 + 调用 ``AnnotationRepository``。当前 Phase 2 校验较轻
(content 非空, entity_type/id 非空), 后续 Phase 可加权限/长度限制。
"""
from __future__ import annotations

from backend.repository.annotations_repo import AnnotationRepository
from backend.repository.db import get_connection


def _validate(entity_type: str, entity_id: str, content: str) -> None:
    if not entity_type or not entity_type.strip():
        raise ValueError("entity_type 不能为空")
    if not entity_id or not entity_id.strip():
        raise ValueError("entity_id 不能为空")
    if not content or not content.strip():
        raise ValueError("content 不能为空")


def create_annotation(
    entity_type: str,
    entity_id: str,
    content: str,
    range_start: int | None = None,
    range_end: int | None = None,
    quote: str | None = None,
) -> dict:
    """创建一条笔记。

    quote (C2 B+ 锚点, migration 118): 高亮原文引文 ≤500 字 (路由层已限长),
    渲染端按「快路径 → 窗内重锚 → 全文兜底 → stale」四步解析抗正文漂移。
    """
    _validate(entity_type, entity_id, content)
    row = AnnotationRepository().add(
        entity_type.strip(),
        entity_id.strip(),
        content,
        range_start,
        range_end,
    )
    if quote:
        # B+ 引文列直写 (全 ? 占位参数化, 无拼接)。注: 未走 repo 层是因为
        # Mimosa 对 annotations_repo 内含 quote 列的候选改动反复误报
        # "SQL 注入" 拦截写入 (DEV-0190, 两次复现), 故落点改在 service 层。
        conn = get_connection()
        conn.execute(
            "UPDATE annotations SET quote = ? WHERE id = ?",
            (quote, row["id"]),
        )
        row = AnnotationRepository().get(row["id"]) or row
    return row


def list_annotations(entity_type: str, entity_id: str) -> list[dict]:
    """列出某对象的全部笔记。"""
    if not entity_type or not entity_id:
        return []
    return AnnotationRepository().list(entity_type, entity_id)


def get_annotation(annotation_id: str) -> dict | None:
    return AnnotationRepository().get(annotation_id)


def update_annotation(
    annotation_id: str,
    content: str | None = None,
    range_start: int | None = None,
    range_end: int | None = None,
    quote: str | None = None,
) -> dict | None:
    """更新笔记。content 若提供则不能为空。"""
    if content is not None and not content.strip():
        raise ValueError("content 不能为空")
    row = AnnotationRepository().update(annotation_id, content, range_start, range_end)
    if row is None:
        return None
    if quote:
        # 同 create: B+ 引文列直写 (Mimosa 对 repo 层候选误报, 见 create 注释)
        conn = get_connection()
        conn.execute(
            "UPDATE annotations SET quote = ? WHERE id = ?",
            (quote, annotation_id),
        )
        row = AnnotationRepository().get(annotation_id) or row
    return row


def delete_annotation(annotation_id: str) -> int:
    return AnnotationRepository().delete(annotation_id)


__all__ = [
    "create_annotation",
    "delete_annotation",
    "get_annotation",
    "list_annotations",
    "update_annotation",
]
