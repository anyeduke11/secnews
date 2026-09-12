import { useState, useCallback, useRef } from 'react';
import { getJSON, postJSON, apiFetch } from '../lib/api';

/**
 * v1.7 Phase 2 — 笔记 CRUD Hook
 *
 * 对接后端:
 *  - GET    /api/annotations?entity_type=&entity_id=   列表
 *  - POST   /api/annotations                           新建
 *  - GET    /api/annotations/{id}                      查看
 *  - PUT    /api/annotations/{id}                      更新
 *  - DELETE /api/annotations/{id}                      删除
 *
 * 按 entity (entity_type + entity_id) 加载笔记列表;
 * 提供 add / update / remove 操作, 操作后自动重载列表.
 *
 * 端点为单一 hook 专用 → 常量化于此, 走 lib/api 统一封装。
 */

const ANNOTATIONS_URL = '/api/annotations';

export interface Annotation {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  range_start: number | null;
  range_end: number | null;
  created_at: string;
  updated_at: string;
}

export interface UseAnnotationsReturn {
  items: Annotation[];
  loading: boolean;
  error: string | null;
  load: (entityType: string, entityId: string) => Promise<void>;
  add: (
    entityType: string,
    entityId: string,
    content: string,
    rangeStart?: number,
    rangeEnd?: number
  ) => Promise<Annotation>;
  update: (
    annotationId: string,
    content: string,
    rangeStart?: number,
    rangeEnd?: number
  ) => Promise<Annotation>;
  remove: (annotationId: string) => Promise<void>;
}

export function useAnnotations(): UseAnnotationsReturn {
  const [items, setItems] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentEntityRef = useRef<{ type: string; id: string } | null>(null);

  const load = useCallback(async (entityType: string, entityId: string) => {
    currentEntityRef.current = { type: entityType, id: entityId };
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
      const data = await getJSON<{ items?: Annotation[] }>(`${ANNOTATIONS_URL}?${params}`);
      // 仅当仍为当前 entity 时才更新 (避免竞态)
      if (
        currentEntityRef.current?.type === entityType &&
        currentEntityRef.current?.id === entityId
      ) {
        setItems(data.items || []);
      }
    } catch (e: any) {
      setError(e?.message || '笔记加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const reload = useCallback(async () => {
    const cur = currentEntityRef.current;
    if (cur) await load(cur.type, cur.id);
  }, [load]);

  const add = useCallback(
    async (
      entityType: string,
      entityId: string,
      content: string,
      rangeStart?: number,
      rangeEnd?: number
    ): Promise<Annotation> => {
      const data = await postJSON<{ item: Annotation }>(ANNOTATIONS_URL, {
        entity_type: entityType,
        entity_id: entityId,
        content,
        range_start: rangeStart ?? null,
        range_end: rangeEnd ?? null,
      });
      const item = data.item;
      await reload();
      return item;
    },
    [reload]
  );

  const update = useCallback(
    async (
      annotationId: string,
      content: string,
      rangeStart?: number,
      rangeEnd?: number
    ): Promise<Annotation> => {
      const body: Record<string, unknown> = { content };
      if (rangeStart !== undefined) body.range_start = rangeStart;
      if (rangeEnd !== undefined) body.range_end = rangeEnd;
      const data = await apiFetch<{ item: Annotation }>(
        `${ANNOTATIONS_URL}/${encodeURIComponent(annotationId)}`,
        { method: 'PUT', body: JSON.stringify(body) },
      );
      const item = data.item;
      await reload();
      return item;
    },
    [reload]
  );

  const remove = useCallback(
    async (annotationId: string): Promise<void> => {
      await apiFetch<void>(`${ANNOTATIONS_URL}/${encodeURIComponent(annotationId)}`, {
        method: 'DELETE',
      });
      await reload();
    },
    [reload]
  );

  return { items, loading, error, load, add, update, remove };
}
