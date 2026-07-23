"""v1.7 Phase 2 — Annotation (笔记) 服务。

业务编排层: 校验 + 调用 ``AnnotationRepository``。当前 Phase 2 校验较轻
(content 非空, entity_type/id 非空), 后续 Phase 可加权限/长度限制。
"""
from __future__ import annotations

from typing import Optional

from backend.repository.annotations_repo import AnnotationRepository


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
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
) -> dict:
    """创建一条笔记。"""
    _validate(entity_type, entity_id, content)
    return AnnotationRepository().add(
        entity_type.strip(),
        entity_id.strip(),
        content,
        range_start,
        range_end,
    )


def list_annotations(entity_type: str, entity_id: str) -> list[dict]:
    """列出某对象的全部笔记。"""
    if not entity_type or not entity_id:
        return []
    return AnnotationRepository().list(entity_type, entity_id)


def get_annotation(annotation_id: str) -> Optional[dict]:
    return AnnotationRepository().get(annotation_id)


def update_annotation(
    annotation_id: str,
    content: Optional[str] = None,
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
) -> Optional[dict]:
    """更新笔记。content 若提供则不能为空。"""
    if content is not None and not content.strip():
        raise ValueError("content 不能为空")
    return AnnotationRepository().update(
        annotation_id, content, range_start, range_end
    )


def delete_annotation(annotation_id: str) -> int:
    return AnnotationRepository().delete(annotation_id)


__all__ = [
    "create_annotation",
    "list_annotations",
    "get_annotation",
    "update_annotation",
    "delete_annotation",
]
